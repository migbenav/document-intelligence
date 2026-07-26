"""Suggestion generator for quality analysis.

Generates actionable improvement suggestions from quality findings
(contradictions, ambiguities, missing elements) using the LLM with
Knowledge Model and IR context.

Requirements covered: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.6
"""

import json
import logging
import uuid
from typing import Any

from pydantic import ValidationError

from app.analysis.llm_client import LLMClient
from app.analysis.prompts import suggestion_generation_v1
from app.models.document import IntermediateRepresentation
from app.models.knowledge_model import KnowledgeModel
from app.models.quality_analysis import (
    FindingSourceRef,
    Inconsistency,
    MissingElement,
    Suggestion,
)

logger = logging.getLogger(__name__)

# Maximum number of suggestions per analysis run (Req 4.6)
MAX_SUGGESTIONS = 20

# Priority ordering for truncation: low < medium < high (truncate lowest first)
_PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2}

# ISO language code to full language name mapping
LANGUAGE_MAP: dict[str, str] = {
    "es": "Spanish",
    "en": "English",
}


class SuggestionGenerator:
    """Generates actionable improvement suggestions from findings.

    Uses the LLM to produce suggestions based on quality findings,
    KM context, and original document text. Enforces:
    - Max 20 suggestions per run (Req 4.6)
    - At least 1 suggestion per high-severity finding (Req 4.4)
    - Each suggestion has at least 1 source_ref (Req 7.6)
    - Empty suggestions for zero findings + no structural improvements (Req 4.5)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize with an LLM client for suggestion generation.

        Args:
            llm_client: The LLM client for calling the model.
        """
        self._llm_client = llm_client

    async def generate(
        self,
        inconsistencies: list[Inconsistency],
        missing_elements: list[MissingElement],
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
        document_language: str = "es",
    ) -> list[Suggestion]:
        """Generate suggestions based on findings.

        Builds a prompt with all findings + KM context + IR text,
        calls the LLM, parses the response, and applies post-processing
        to enforce constraints.

        Args:
            inconsistencies: Detected contradictions and ambiguities.
            missing_elements: Missing or partial elements from completeness evaluation.
            knowledge_model: The Knowledge Model providing document context.
            ir: The Intermediate Representation with original document text.
            document_language: ISO language code ('es' or 'en') for the document's
                language. Suggestions will be generated in this language.
                Defaults to 'es'.

        Returns:
            A list of Suggestion objects, at most 20, with guaranteed
            high-severity coverage and source_refs.

        Raises:
            ValueError: If the LLM response fails Pydantic validation.
        """
        # Build inputs for prompt
        findings_json = self._build_findings_json(inconsistencies, missing_elements)
        elements_json = self._build_elements_json(knowledge_model)
        ir_text = self._build_ir_text(ir)

        # If zero findings and we pass through empty findings
        has_findings = len(inconsistencies) > 0 or len(missing_elements) > 0

        # Resolve response language from document_language code
        response_language = LANGUAGE_MAP.get(document_language, "Spanish")

        # Build prompt
        prompt = suggestion_generation_v1.build(findings_json, elements_json, ir_text, response_language=response_language)

        # Call LLM (primary model, temperature 0.1)
        response = await self._llm_client.call(
            prompt, model_tier="primary", temperature=0.1
        )

        # Parse response against Pydantic model
        suggestions = self._parse_response(response.content, ir)

        # If zero findings and LLM returns no suggestions: return empty (Req 4.5)
        if not has_findings and len(suggestions) == 0:
            return []

        # Post-processing: ensure each suggestion has at least 1 source_ref (Req 7.6)
        suggestions = self._ensure_source_refs(suggestions, ir)

        # Post-processing: ensure at least 1 suggestion per high-severity finding (Req 4.4)
        suggestions = self._ensure_high_severity_coverage(
            suggestions, inconsistencies, missing_elements, ir
        )

        # Post-processing: enforce max 20 suggestions, truncate lowest priority (Req 4.6)
        suggestions = self._enforce_max_suggestions(suggestions)

        return suggestions

    def _build_findings_json(
        self,
        inconsistencies: list[Inconsistency],
        missing_elements: list[MissingElement],
    ) -> str:
        """Serialize findings to JSON for the prompt.

        Only includes finding data — no user metadata (Req 9.2).
        """
        findings: list[dict[str, Any]] = []

        for inc in inconsistencies:
            findings.append(
                {
                    "id": inc.id,
                    "type": inc.type,
                    "description": inc.description,
                    "severity": inc.severity,
                    "affected_element_ids": inc.affected_element_ids,
                }
            )

        for me in missing_elements:
            findings.append(
                {
                    "id": me.id,
                    "classification": me.classification,
                    "expected_element": me.expected_element,
                    "description": me.description,
                    "severity": me.severity,
                    "schema_reference": me.schema_reference,
                }
            )

        return json.dumps(findings, ensure_ascii=False)

    def _build_elements_json(self, knowledge_model: KnowledgeModel) -> str:
        """Serialize KM elements to JSON for the prompt.

        Only includes element data — no user metadata (Req 9.2).
        """
        elements = []
        for elem in knowledge_model.elements:
            elements.append(
                {
                    "id": elem.id,
                    "type": elem.type,
                    "name": elem.name,
                    "content": elem.content,
                }
            )
        return json.dumps(elements, ensure_ascii=False)

    def _build_ir_text(self, ir: IntermediateRepresentation) -> str:
        """Build IR text from chunks for the prompt.

        Includes chunk_id context so the LLM can reference them in source_refs.
        """
        parts = []
        for chunk in ir.chunks:
            section = chunk.structural_context.get("section", "")
            page = chunk.structural_context.get("page", "")
            context_label = f"[chunk:{chunk.chunk_id}]"
            if section:
                context_label += f" [section:{section}]"
            if page:
                context_label += f" [page:{page}]"
            parts.append(f"{context_label}\n{chunk.text}")
        return "\n\n".join(parts)

    def _parse_response(
        self, content: str, ir: IntermediateRepresentation
    ) -> list[Suggestion]:
        """Parse LLM response JSON into Suggestion models.

        Args:
            content: Raw LLM response text (expected JSON).
            ir: The IR for constructing source_refs with document_id.

        Returns:
            A list of parsed Suggestion objects.

        Raises:
            ValueError: If JSON parsing or Pydantic validation fails.
        """
        # Strip markdown code fences if present
        clean_content = content.strip()
        if clean_content.startswith("```"):
            # Remove opening fence (potentially ```json)
            first_newline = clean_content.index("\n")
            clean_content = clean_content[first_newline + 1 :]
            # Remove closing fence
            if clean_content.endswith("```"):
                clean_content = clean_content[:-3].strip()

        try:
            data = json.loads(clean_content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Suggestion generation LLM response is not valid JSON: {e}"
            ) from e

        if not isinstance(data, dict) or "suggestions" not in data:
            raise ValueError(
                "Suggestion generation LLM response missing 'suggestions' key"
            )

        suggestions: list[Suggestion] = []
        for item in data["suggestions"]:
            try:
                # Build source_refs with document_id from the IR
                source_refs = []
                for ref_data in item.get("source_refs", []):
                    source_refs.append(
                        FindingSourceRef(
                            document_id=ir.document_id,
                            chunk_id=ref_data.get("chunk_id", ""),
                            page=ref_data.get("page"),
                            section=ref_data.get("section"),
                            evidence=ref_data.get("evidence", ""),
                            evidence_verified=False,
                        )
                    )

                suggestion = Suggestion(
                    id=item.get("id", f"sug-{uuid.uuid4().hex[:8]}"),
                    description=item.get("description", ""),
                    category=item.get("category", "structure"),
                    priority=item.get("priority", "medium"),
                    related_finding_ids=item.get("related_finding_ids", []),
                    source_refs=source_refs,
                    all_evidence_unverified=False,
                )
                suggestions.append(suggestion)
            except ValidationError as e:
                raise ValueError(
                    f"Suggestion generation: invalid suggestion data: {e}"
                ) from e

        return suggestions

    def _ensure_source_refs(
        self, suggestions: list[Suggestion], ir: IntermediateRepresentation
    ) -> list[Suggestion]:
        """Ensure each suggestion has at least 1 source_ref (Req 7.6).

        If a suggestion has no source_refs, add a fallback using the first IR chunk.
        """
        if not ir.chunks:
            return suggestions

        fallback_chunk = ir.chunks[0]
        fallback_ref = FindingSourceRef(
            document_id=ir.document_id,
            chunk_id=fallback_chunk.chunk_id,
            page=fallback_chunk.structural_context.get("page"),
            section=fallback_chunk.structural_context.get("section"),
            evidence=fallback_chunk.text[:500] if fallback_chunk.text else "",
            evidence_verified=False,
        )

        result = []
        for suggestion in suggestions:
            if not suggestion.source_refs:
                # Create a copy with the fallback source_ref
                suggestion = suggestion.model_copy(
                    update={"source_refs": [fallback_ref]}
                )
            result.append(suggestion)
        return result

    def _ensure_high_severity_coverage(
        self,
        suggestions: list[Suggestion],
        inconsistencies: list[Inconsistency],
        missing_elements: list[MissingElement],
        ir: IntermediateRepresentation,
    ) -> list[Suggestion]:
        """Ensure at least 1 suggestion per high-severity finding (Req 4.4).

        If a high-severity finding has no associated suggestion,
        generate a placeholder suggestion for it.
        """
        # Collect high-severity finding IDs
        high_severity_finding_ids: set[str] = set()
        for inc in inconsistencies:
            if inc.severity == "high":
                high_severity_finding_ids.add(inc.id)
        for me in missing_elements:
            if me.severity == "high":
                high_severity_finding_ids.add(me.id)

        if not high_severity_finding_ids:
            return suggestions

        # Check which high-severity findings already have suggestions
        covered_ids: set[str] = set()
        for suggestion in suggestions:
            for fid in suggestion.related_finding_ids:
                if fid in high_severity_finding_ids:
                    covered_ids.add(fid)

        # Generate placeholder suggestions for uncovered high-severity findings
        uncovered_ids = high_severity_finding_ids - covered_ids
        if not uncovered_ids:
            return suggestions

        # Build lookup for finding descriptions
        finding_descriptions: dict[str, str] = {}
        finding_categories: dict[str, str] = {}
        for inc in inconsistencies:
            if inc.id in uncovered_ids:
                finding_descriptions[inc.id] = inc.description
                finding_categories[inc.id] = (
                    "consistency" if inc.type == "contradiction" else "clarity"
                )
        for me in missing_elements:
            if me.id in uncovered_ids:
                finding_descriptions[me.id] = me.description
                finding_categories[me.id] = "completeness"

        # Create fallback source_ref
        fallback_ref = self._create_fallback_source_ref(ir)

        for finding_id in uncovered_ids:
            desc = finding_descriptions.get(finding_id, "Address this high-severity finding")
            category = finding_categories.get(finding_id, "structure")
            # Truncate description to 300 chars and make actionable
            action_desc = f"Address: {desc}"[:300]

            placeholder = Suggestion(
                id=f"sug-{uuid.uuid4().hex[:8]}",
                description=action_desc,
                category=category,
                priority="high",
                related_finding_ids=[finding_id],
                source_refs=[fallback_ref] if fallback_ref else [],
                all_evidence_unverified=False,
            )
            suggestions.append(placeholder)

        return suggestions

    def _enforce_max_suggestions(
        self, suggestions: list[Suggestion]
    ) -> list[Suggestion]:
        """Enforce max 20 suggestions, truncating lowest priority first (Req 4.6).

        Priority ordering: low < medium < high. When over the limit,
        remove lowest-priority suggestions first.
        """
        if len(suggestions) <= MAX_SUGGESTIONS:
            return suggestions

        # Sort by priority descending (high first), then preserve order for same priority
        suggestions_sorted = sorted(
            suggestions,
            key=lambda s: _PRIORITY_ORDER.get(s.priority, 0),
            reverse=True,
        )

        return suggestions_sorted[:MAX_SUGGESTIONS]

    def _create_fallback_source_ref(
        self, ir: IntermediateRepresentation
    ) -> FindingSourceRef | None:
        """Create a fallback source_ref from the first IR chunk."""
        if not ir.chunks:
            return None

        chunk = ir.chunks[0]
        return FindingSourceRef(
            document_id=ir.document_id,
            chunk_id=chunk.chunk_id,
            page=chunk.structural_context.get("page"),
            section=chunk.structural_context.get("section"),
            evidence=chunk.text[:500] if chunk.text else "",
            evidence_verified=False,
        )
