"""Ambiguity detection module for document quality analysis.

Identifies ambiguous, vague, or unclear statements in a document using
LLM-based analysis with Knowledge Model elements and IR text as context.

Requirements covered: 2.1, 2.2, 2.3, 2.4, 2.5, 8.2, 8.4
"""

import json
import logging

from pydantic import BaseModel, Field, ValidationError

from app.analysis.llm_client import LLMClient
from app.analysis.prompts import ambiguity_detection_v1
from app.models.document import IntermediateRepresentation
from app.models.knowledge_model import KnowledgeModel
from app.models.quality_analysis import FindingSourceRef, Inconsistency

logger = logging.getLogger(__name__)


# --- Internal Pydantic models for parsing LLM response ---


class _AmbiguitySourceRef(BaseModel):
    """Source reference as returned by the LLM in the ambiguity detection response."""

    chunk_id: str
    page: int | None = None
    section: str | None = None
    evidence: str = Field(max_length=500)


class _AmbiguityFinding(BaseModel):
    """A single ambiguity finding as returned by the LLM."""

    id: str
    category: str
    description: str = Field(max_length=500)
    severity: str
    affected_element_ids: list[str] = Field(default_factory=list)
    source_ref: _AmbiguitySourceRef


class _AmbiguityResponse(BaseModel):
    """Top-level LLM response model for ambiguity detection."""

    ambiguities: list[_AmbiguityFinding]


class AmbiguityDetectionError(Exception):
    """Raised when ambiguity detection fails (LLM error or parse failure)."""

    pass


class AmbiguityDetector:
    """Detects ambiguous/vague statements using LLM analysis.

    Uses Knowledge Model elements and IR text to identify:
    - Undefined terms
    - Vague quantifiers
    - Unclear pronoun antecedents
    - Unspecified conditions

    On LLM failure: raises AmbiguityDetectionError (no partial results per Req 2.5).
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize with an LLM client instance.

        Args:
            llm_client: The LLM client to use for ambiguity detection calls.
        """
        self._llm_client = llm_client

    async def detect(
        self,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
    ) -> list[Inconsistency]:
        """Detect ambiguities in the document.

        Builds a prompt with KM elements and IR text, calls the LLM,
        and parses the response into Inconsistency findings.

        Args:
            knowledge_model: The completed Knowledge Model for the document.
            ir: The intermediate representation with document text chunks.

        Returns:
            A list of Inconsistency findings with type="ambiguity".

        Raises:
            AmbiguityDetectionError: On LLM failure or response parse failure.
        """
        # Build prompt inputs (Req 9.2: only KM elements and IR text, no user metadata)
        elements_json = self._serialize_elements(knowledge_model)
        ir_text = self._serialize_ir_text(ir)

        # Build prompt using versioned template
        prompt = ambiguity_detection_v1.build(elements_json, ir_text)

        # Call LLM (primary model, temperature 0.1)
        try:
            response = await self._llm_client.call(
                prompt, model_tier="primary", temperature=0.1
            )
        except Exception as e:
            # On LLM failure: raise exception, no partial results (Req 2.5)
            raise AmbiguityDetectionError(
                f"LLM call failed during ambiguity detection: {e}"
            ) from e

        # Parse response against Pydantic model
        try:
            parsed = self._parse_response(response.content)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            raise AmbiguityDetectionError(
                f"Failed to parse LLM response for ambiguity detection: {e}"
            ) from e

        # Convert parsed findings to Inconsistency models
        return self._build_findings(parsed, knowledge_model, ir)

    def _serialize_elements(self, knowledge_model: KnowledgeModel) -> str:
        """Serialize KM elements to JSON for the prompt.

        Only includes element data relevant to ambiguity detection.
        No user metadata or session info (Req 9.2).
        """
        elements_data = []
        for elem in knowledge_model.elements:
            elements_data.append(
                {
                    "id": elem.id,
                    "type": elem.type,
                    "name": elem.name,
                    "content": elem.content,
                    "verified": elem.verified,
                }
            )
        return json.dumps(elements_data, ensure_ascii=False, indent=2)

    def _serialize_ir_text(self, ir: IntermediateRepresentation) -> str:
        """Serialize IR chunks to text for the prompt.

        Only includes document text and structural markers.
        No user metadata (Req 9.2).
        """
        chunks_text = []
        for chunk in ir.chunks:
            page = chunk.structural_context.get("page")
            section = chunk.structural_context.get("section")
            header = f"[chunk_id={chunk.chunk_id}"
            if page is not None:
                header += f", page={page}"
            if section is not None:
                header += f", section={section}"
            header += "]"
            chunks_text.append(f"{header}\n{chunk.text}")
        return "\n\n".join(chunks_text)

    def _parse_response(self, content: str) -> _AmbiguityResponse:
        """Parse the LLM response into the internal Pydantic model.

        Args:
            content: Raw LLM response content string.

        Returns:
            Parsed _AmbiguityResponse.

        Raises:
            ValidationError: If the response doesn't conform to the expected schema.
            ValueError: If JSON extraction fails.
            json.JSONDecodeError: If the content is not valid JSON.
        """
        # Strip potential markdown code block markers
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        return _AmbiguityResponse.model_validate(data)

    def _build_findings(
        self,
        parsed: _AmbiguityResponse,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
    ) -> list[Inconsistency]:
        """Convert parsed LLM findings into Inconsistency models.

        Sets involves_unverified_elements when any referenced KM element
        has verified=False (Req 8.4).
        """
        # Build a lookup of element IDs to their verified status
        element_verified_map: dict[str, bool] = {
            elem.id: elem.verified for elem in knowledge_model.elements
        }

        findings: list[Inconsistency] = []
        for idx, amb in enumerate(parsed.ambiguities):
            # Determine involves_unverified_elements (Req 8.4)
            involves_unverified = any(
                not element_verified_map.get(eid, True)
                for eid in amb.affected_element_ids
            )

            # Build source_ref
            source_ref = FindingSourceRef(
                document_id=ir.document_id,
                chunk_id=amb.source_ref.chunk_id,
                page=amb.source_ref.page,
                section=amb.source_ref.section,
                evidence=amb.source_ref.evidence,
                evidence_verified=False,  # Will be set by FindingVerifier later
            )

            finding = Inconsistency(
                id=amb.id,
                type="ambiguity",
                description=amb.description,
                severity=amb.severity,
                affected_element_ids=amb.affected_element_ids,
                source_refs=[source_ref],
                involves_unverified_elements=involves_unverified,
                all_evidence_unverified=False,
                from_explicit_relationship=False,
            )
            findings.append(finding)

        return findings
