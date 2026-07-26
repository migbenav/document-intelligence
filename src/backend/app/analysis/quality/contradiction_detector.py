"""Contradiction detection module for the quality analysis pipeline.

Identifies contradictions from two sources:
1. Explicit `contradicts` relationships in the Knowledge Model (structural, no LLM).
2. LLM-based semantic analysis for deeper contradiction detection.

On LLM failure, returns only the structural contradictions (Req 1.6).

Requirements covered: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.2, 8.4, 8.5
"""

import json
import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.analysis.llm_client import LLMClient, LLMTransientError
from app.analysis.prompts import contradiction_detection_v1
from app.models.document import IntermediateRepresentation
from app.models.knowledge_model import KnowledgeModel
from app.models.quality_analysis import FindingSourceRef, Inconsistency

logger = logging.getLogger(__name__)


# --- Pydantic model for LLM response parsing ---


class LLMContradictionSourceRef(BaseModel):
    """A source reference from the LLM contradiction detection response."""

    chunk_id: str
    page: int | None = None
    section: str | None = None
    evidence: str = Field(max_length=500)


class LLMContradictionFinding(BaseModel):
    """A single contradiction finding from the LLM response."""

    type: str  # Should always be "contradiction"
    description: str = Field(max_length=500)
    severity: str  # "high", "medium", or "low"
    affected_element_ids: list[str]
    source_refs: list[LLMContradictionSourceRef]


class LLMContradictionResponse(BaseModel):
    """Expected structure of the LLM contradiction detection response."""

    findings: list[LLMContradictionFinding]


LANGUAGE_MAP: dict[str, str] = {
    "es": "Spanish",
    "en": "English",
}


class ContradictionDetector:
    """Detects contradictions from structural relationships and LLM analysis.

    Step 1: Collects explicit `contradicts` relationships from KM as confirmed findings.
    Step 2: Calls LLM to detect additional semantic contradictions.

    On LLM failure, returns only the explicit-relationship contradictions (Req 1.6).
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize with an LLMClient instance.

        Args:
            llm_client: The LLM communication layer for semantic analysis.
        """
        self._llm_client = llm_client

    async def detect(
        self,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
        language: str = "es",
    ) -> list[Inconsistency]:
        """Detect contradictions in the Knowledge Model.

        Step 1: Collect explicit `contradicts` relationships as confirmed findings.
        Step 2: Call LLM to detect additional semantic contradictions.

        On LLM failure, returns only the explicit-relationship contradictions (Req 1.6).

        Args:
            knowledge_model: The completed Knowledge Model to analyze.
            ir: The intermediate representation with document text chunks.
            language: ISO language code ('es' or 'en') for LLM response language.

        Returns:
            A list of Inconsistency findings of type "contradiction".

        Raises:
            ValueError: When LLM response fails Pydantic validation (Req 10.2, 10.3).
        """
        # Step 1: Collect explicit contradicts relationships
        structural_contradictions = self._collect_structural_contradictions(
            knowledge_model
        )

        # Step 2: LLM-based deeper analysis
        try:
            llm_contradictions = await self._detect_llm_contradictions(
                knowledge_model, ir, language=language
            )
        except ValueError:
            # Parse failure: raise to caller (Req 10.2, 10.3)
            raise
        except Exception as e:
            # On LLM failure: return only structural contradictions (Req 1.6)
            logger.warning(
                "LLM contradiction detection failed, returning only structural contradictions",
                extra={"error": str(e), "structural_count": len(structural_contradictions)},
            )
            return structural_contradictions

        return structural_contradictions + llm_contradictions

    def _collect_structural_contradictions(
        self, knowledge_model: KnowledgeModel
    ) -> list[Inconsistency]:
        """Collect contradictions from explicit `contradicts` relationships in the KM.

        Each `contradicts` relationship generates a confirmed Inconsistency finding
        with `from_explicit_relationship = True`.

        Args:
            knowledge_model: The Knowledge Model containing elements with relationships.

        Returns:
            List of confirmed contradiction findings from explicit relationships.
        """
        contradictions: list[Inconsistency] = []
        # Build element lookup for quick access
        element_by_id = {elem.id: elem for elem in knowledge_model.elements}

        # Track processed pairs to avoid duplicates (A contradicts B = B contradicts A)
        processed_pairs: set[tuple[str, str]] = set()

        for element in knowledge_model.elements:
            for relation in element.relations:
                if relation.type != "contradicts":
                    continue

                # Normalize pair to avoid duplicates
                pair = tuple(sorted([element.id, relation.target_id]))
                if pair in processed_pairs:
                    continue
                processed_pairs.add(pair)

                target = element_by_id.get(relation.target_id)
                if target is None:
                    continue

                # Build source_refs from both elements
                source_refs = [
                    FindingSourceRef(
                        document_id=element.source_ref.document_id,
                        chunk_id=element.source_ref.chunk_id,
                        page=element.source_ref.page,
                        section=element.source_ref.section,
                        evidence=element.source_ref.evidence[:500],
                        evidence_verified=False,
                    ),
                    FindingSourceRef(
                        document_id=target.source_ref.document_id,
                        chunk_id=target.source_ref.chunk_id,
                        page=target.source_ref.page,
                        section=target.source_ref.section,
                        evidence=target.source_ref.evidence[:500],
                        evidence_verified=False,
                    ),
                ]

                # Determine severity based on criteria
                severity = self._determine_structural_severity(
                    element, target, relation.description
                )

                # Build description
                description = relation.description or (
                    f"Element '{element.name}' contradicts element '{target.name}'."
                )
                description = description[:500]

                # Check if any involved element is unverified
                involves_unverified = not element.verified or not target.verified

                contradictions.append(
                    Inconsistency(
                        id=f"contra-struct-{uuid.uuid4().hex[:8]}",
                        type="contradiction",
                        description=description,
                        severity=severity,
                        affected_element_ids=[element.id, relation.target_id],
                        source_refs=source_refs,
                        involves_unverified_elements=involves_unverified,
                        all_evidence_unverified=False,
                        from_explicit_relationship=True,
                    )
                )

        return contradictions

    def _determine_structural_severity(
        self, source_element: Any, target_element: Any, description: str | None
    ) -> str:
        """Determine severity for a structural contradiction.

        Severity criteria (Req 1.2):
        - high: mutually exclusive facts about the same subject
        - medium: incompatible intent or constraints
        - low: minor wording tensions

        For structural (explicit) contradictions, we default to "high" since
        they were explicitly marked as contradictions in the KM, implying
        direct factual conflict.
        """
        # Explicit contradictions are typically significant — default high
        return "high"

    async def _detect_llm_contradictions(
        self,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
        language: str = "es",
    ) -> list[Inconsistency]:
        """Use LLM to detect additional semantic contradictions.

        Args:
            knowledge_model: The Knowledge Model to analyze.
            ir: The intermediate representation with text chunks.
            language: ISO language code ('es' or 'en') for LLM response language.

        Returns:
            List of LLM-detected contradiction findings.

        Raises:
            ValueError: When LLM response fails Pydantic validation.
            LLMTransientError: When LLM call fails with transient error.
        """
        # Skip LLM if KM is empty
        if not knowledge_model.elements:
            return []

        # Build prompt inputs (data minimization - Req 9.2)
        elements_json = json.dumps(
            [
                {
                    "id": elem.id,
                    "type": elem.type,
                    "name": elem.name,
                    "content": elem.content,
                    "source_ref": {
                        "chunk_id": elem.source_ref.chunk_id,
                        "page": elem.source_ref.page,
                        "section": elem.source_ref.section,
                    },
                }
                for elem in knowledge_model.elements
            ],
            ensure_ascii=False,
        )

        relationships_json = json.dumps(
            [
                {
                    "source_id": elem.id,
                    "target_id": rel.target_id,
                    "type": rel.type,
                    "description": rel.description,
                }
                for elem in knowledge_model.elements
                for rel in elem.relations
            ],
            ensure_ascii=False,
        )

        ir_text = "\n\n".join(
            f"[chunk_id={chunk.chunk_id}] {chunk.text}"
            for chunk in ir.chunks
        )

        # Build prompt using the versioned template
        prompt = contradiction_detection_v1.build(
            elements_json=elements_json,
            relationships_json=relationships_json,
            ir_text=ir_text,
        )

        # Prepend language instruction to the prompt
        response_language = LANGUAGE_MAP.get(language, "Spanish")
        prompt = f"Respond in {response_language}.\n{prompt}"

        # Call LLM (primary model, temperature 0.1)
        response = await self._llm_client.call(
            prompt, model_tier="primary", temperature=0.1
        )

        # Parse LLM response against Pydantic model
        try:
            parsed = LLMContradictionResponse.model_validate_json(response.content)
        except (ValidationError, ValueError) as e:
            raise ValueError(
                f"LLM contradiction detection response failed Pydantic validation: {e}"
            ) from e

        # Convert parsed findings to Inconsistency models
        return self._convert_llm_findings(
            parsed.findings, knowledge_model, ir
        )

    def _convert_llm_findings(
        self,
        findings: list[LLMContradictionFinding],
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
    ) -> list[Inconsistency]:
        """Convert parsed LLM findings to Inconsistency models.

        Sets `involves_unverified_elements` when any affected element has verified=False.

        Args:
            findings: Parsed LLM contradiction findings.
            knowledge_model: The KM for element verification status lookup.
            ir: The IR for document_id.

        Returns:
            List of Inconsistency models from LLM findings.
        """
        element_by_id = {elem.id: elem for elem in knowledge_model.elements}
        inconsistencies: list[Inconsistency] = []

        for finding in findings:
            # Validate severity
            severity = finding.severity if finding.severity in ("high", "medium", "low") else "medium"

            # Build source_refs
            source_refs = [
                FindingSourceRef(
                    document_id=ir.document_id,
                    chunk_id=ref.chunk_id,
                    page=ref.page,
                    section=ref.section,
                    evidence=ref.evidence[:500],
                    evidence_verified=False,
                )
                for ref in finding.source_refs
            ]

            # Check if any affected element is unverified (Req 8.4)
            involves_unverified = any(
                element_by_id.get(eid) is not None
                and not element_by_id[eid].verified
                for eid in finding.affected_element_ids
            )

            inconsistencies.append(
                Inconsistency(
                    id=f"contra-llm-{uuid.uuid4().hex[:8]}",
                    type="contradiction",
                    description=finding.description[:500],
                    severity=severity,
                    affected_element_ids=finding.affected_element_ids,
                    source_refs=source_refs,
                    involves_unverified_elements=involves_unverified,
                    all_evidence_unverified=False,
                    from_explicit_relationship=False,
                )
            )

        return inconsistencies
