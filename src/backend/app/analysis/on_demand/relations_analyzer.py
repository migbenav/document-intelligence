"""RelationsAnalyzer — Section Relations analysis (v2 — Functional Connections).

Produces a list of significant functional relationships between document sections
via a single LLM call with the full document content. Relationships use the v2
vocabulary: enables, restricts, requires, implements, contradicts.

If a prior IndexResult is available, the prompt includes a functional structure
summary so the LLM can reference functional group names in source_section and
target_section fields. Otherwise, sections are referenced by title.

Requirements covered: Req 4 (criteria 1-6)
"""

import asyncio
import json
import logging
import re

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.on_demand.analyzer_response import AnalyzerResponse
from app.analysis.on_demand.models import IndexResult, RelationsResult, StructureNode
from app.analysis.on_demand.prompts.section_relations_v2 import (
    PROMPT_TEMPLATE,
    PROMPT_VERSION,
    build_structure_context,
)
from app.analysis.on_demand.text_preparation import prepare_document_text
from app.models.document import IntermediateRepresentation

logger = logging.getLogger(__name__)

# Timeout for a single LLM call (Decision 6 from design.md)
_LLM_TIMEOUT_SECONDS = 90


class RelationsAnalysisError(Exception):
    """Raised when the relations analysis fails (parse error, validation error, etc.)."""

    pass


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _collect_nodes(nodes: list[StructureNode]) -> list[tuple[str, str]]:
    """Recursively collect (id, title) pairs from a structure tree."""
    result: list[tuple[str, str]] = []
    for node in nodes:
        result.append((node.id, node.title))
        if node.children:
            result.extend(_collect_nodes(node.children))
    return result


def _build_structure_tree_section(index_result: IndexResult) -> str:
    """Build the STRUCTURE TREE NODES section to insert into the prompt.

    Format:
        --- STRUCTURE TREE NODES ---
        - node_id: "title"
        - node_id: "title"
        ...
    """
    nodes = _collect_nodes(index_result.tree)
    lines = ["--- STRUCTURE TREE NODES ---"]
    for node_id, title in nodes:
        lines.append(f'- {node_id}: "{title}"')
    return "\n".join(lines)


class RelationsAnalyzer:
    """Analyzer that identifies relationships between document sections.

    Uses the full document IR in a single LLM call to produce a RelationsResult
    containing a list of SectionRelation objects. When index_result is provided,
    the prompt includes structure tree node IDs for precise references.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    @property
    def prompt_version(self) -> str:
        """Return the prompt version used by this analyzer."""
        return PROMPT_VERSION

    async def analyze(
        self,
        ir: IntermediateRepresentation,
        language: str,
        classification: str = "generic",
        model_override: str | None = None,
        auto_fallback: bool = True,
        index_result: IndexResult | None = None,
    ) -> AnalyzerResponse:
        """Analyze document and produce inter-section relationships.

        Args:
            ir: The document's intermediate representation with ordered chunks.
            language: The response language for the LLM output (e.g., "es", "en").
            classification: Document classification (e.g., "normative", "procedure").
                Defaults to "generic". Used in v2 prompts (tasks 5-8).
            model_override: Optional model identifier to override the default.
            auto_fallback: Whether to allow automatic fallback on transient errors.
            index_result: If provided, structure tree node IDs are included in the
                prompt so the LLM can reference them in source_section/target_section.

        Returns:
            An AnalyzerResponse wrapping the RelationsResult with model metadata.

        Raises:
            RelationsAnalysisError: On JSON parse failure or validation error.
            asyncio.TimeoutError: If the LLM call exceeds 30 seconds.
            LLMTransientError: If the LLM call fails with a transient error.
            LLMAuthenticationError: If the LLM credentials are invalid.
        """
        # 1. Build full document text from IR chunks with section markers
        document_text = prepare_document_text(ir)

        # 2. Build structure context from index_result (empty string if None)
        structure_context = build_structure_context(index_result)

        # 3. Format the prompt with classification, response language, structure
        #    context, and document content
        prompt = PROMPT_TEMPLATE.format(
            classification=classification,
            response_language=language,
            structure_context=structure_context,
            document_text=document_text,
        )

        # 4. Call LLM with timeout
        logger.info(
            "Starting Section Relations analysis",
            extra={
                "document_id": ir.document_id,
                "language": language,
                "classification": classification,
                "has_index": index_result is not None,
            },
        )

        response: LLMResponse = await asyncio.wait_for(
            self._llm_client.call(
                prompt,
                model_tier="primary",
                temperature=0.1,
                model_override=model_override,
                auto_fallback=auto_fallback,
            ),
            timeout=_LLM_TIMEOUT_SECONDS,
        )

        # 5. Parse JSON response and validate as RelationsResult
        raw_json = _extract_json(response.content)

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse LLM response as JSON",
                extra={
                    "document_id": ir.document_id,
                    "error": str(e),
                    "raw_content_preview": response.content[:200],
                },
            )
            raise RelationsAnalysisError(
                f"LLM response is not valid JSON: {e}"
            ) from e

        try:
            result = RelationsResult.model_validate(data)
        except Exception as e:
            logger.error(
                "Failed to validate LLM response against RelationsResult schema",
                extra={
                    "document_id": ir.document_id,
                    "error": str(e),
                },
            )
            raise RelationsAnalysisError(
                f"LLM response does not match RelationsResult schema: {e}"
            ) from e

        logger.info(
            "Section Relations analysis completed",
            extra={
                "document_id": ir.document_id,
                "model_id": response.model_id,
                "relation_count": len(result.relations),
            },
        )

        # 6. Determine the requested model for fallback detection
        if model_override is not None and model_override != "default":
            requested_model = model_override
        else:
            requested_model = self._llm_client.primary_model

        # Detect whether fallback was used
        fallback_used = response.model_id != requested_model

        return AnalyzerResponse(
            result=result,
            model_id=response.model_id,
            prompt_version=PROMPT_VERSION,
            fallback_used=fallback_used,
        )
