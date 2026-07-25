"""Pydantic v2 models for the Document Quality Analysis feature.

These models define the finding types (Inconsistency, MissingElement, Suggestion),
evidence traceability (FindingSourceRef), analysis metadata, and the composite
QualityAnalysisResult returned by the quality analysis pipeline.

Validates: Requirements 1.2, 2.2, 3.1, 3.2, 4.2, 7.1, 7.3, 7.5
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FindingSourceRef(BaseModel):
    """Evidence reference tracing a quality finding back to the original document.

    Follows the same structure as Knowledge Model SourceRef with the addition of
    evidence_verified for Trust by Evidence (ADR-004, Req 7.5).
    """

    document_id: str = Field(description="Document this evidence was found in")
    chunk_id: str = Field(description="IR chunk containing the evidence")
    page: int | None = Field(default=None, description="Page number (present for PDF documents)")
    section: str | None = Field(
        default=None, description="Section heading (present for Markdown documents)"
    )
    evidence: str = Field(
        max_length=500,
        description="Verbatim text span from the source document (max 500 characters)",
    )
    evidence_verified: bool = Field(
        default=False,
        description="Whether evidence was verified against the source document via text-matching",
    )


class Inconsistency(BaseModel):
    """A contradiction or ambiguity finding detected in the document.

    Unifies both contradiction and ambiguity subtypes under a single model
    with a type discriminator (Req 1.2, 2.2).
    """

    id: str = Field(description="Unique identifier for this finding")
    type: Literal["contradiction", "ambiguity"] = Field(
        description="Finding subtype: contradiction or ambiguity"
    )
    description: str = Field(
        max_length=500,
        description="Description of the inconsistency (max 500 characters)",
    )
    severity: Literal["high", "medium", "low"] = Field(
        description="Severity level of the finding"
    )
    affected_element_ids: list[str] = Field(
        description="Knowledge Model element IDs involved in this finding"
    )
    source_refs: list[FindingSourceRef] = Field(
        description="Evidence references; at least 1 for ambiguities, at least 2 for contradictions"
    )
    involves_unverified_elements: bool = Field(
        default=False,
        description="True when any involved KM element has verified=false (Req 8.4)",
    )
    all_evidence_unverified: bool = Field(
        default=False,
        description="True when all source_refs have evidence_verified=false (Req 7.7)",
    )
    from_explicit_relationship: bool = Field(
        default=False,
        description="True for contradictions detected from explicit contradicts relationships (Req 1.3)",
    )


class MissingElement(BaseModel):
    """A finding indicating missing or partial document content relative to the type schema.

    Does not require source_ref since the element is absent by definition (Req 7.4).
    """

    id: str = Field(description="Unique identifier for this finding")
    classification: Literal["missing", "partial"] = Field(
        description="Whether the element is entirely absent or only partially covered"
    )
    expected_element: str = Field(
        description="Element name expected by the document type schema"
    )
    description: str = Field(
        description="Description of what is expected or what additional content is needed"
    )
    severity: Literal["high", "medium", "low"] = Field(
        description="Severity level based on element importance to the document type"
    )
    schema_reference: str = Field(
        description="Document type schema that defines this expectation (e.g., 'prd', 'technical_spec')"
    )


class Suggestion(BaseModel):
    """An actionable improvement recommendation derived from quality findings.

    Each suggestion describes a concrete action to improve the document (Req 4.2, 4.3).
    """

    id: str = Field(description="Unique identifier for this suggestion")
    description: str = Field(
        max_length=300,
        description="Clear description of the recommended improvement (max 300 characters)",
    )
    category: Literal["structure", "clarity", "completeness", "consistency"] = Field(
        description="Category of the suggestion"
    )
    priority: Literal["high", "medium", "low"] = Field(
        description="Priority level based on related finding severity"
    )
    related_finding_ids: list[str] = Field(
        default_factory=list,
        description="Optional references to finding IDs that motivated this suggestion",
    )
    source_refs: list[FindingSourceRef] = Field(
        default_factory=list,
        description="Evidence references to the context that triggered the suggestion (Req 7.6)",
    )
    all_evidence_unverified: bool = Field(
        default=False,
        description="True when all source_refs have evidence_verified=false (Req 7.7)",
    )


class QualityAnalysisMetadata(BaseModel):
    """Metadata for reproducibility and auditing of quality analysis runs (Req 9.3)."""

    prompt_versions: dict[str, str] = Field(
        description="Prompt version identifiers per analysis type (e.g., {'contradiction_detection': 'contradiction-v1'})"
    )
    model_id: str = Field(description="LLM model identifier used for analysis")
    temperature: float = Field(description="Temperature parameter used for generation")
    document_type: str = Field(
        description="Document type the analysis was evaluated against"
    )
    started_at: datetime = Field(description="Analysis start timestamp (ISO 8601)")
    completed_at: datetime = Field(description="Analysis completion timestamp (ISO 8601)")
    finding_counts: dict[str, int] = Field(
        description="Finding counts per category (contradictions, ambiguities, missing_elements, suggestions)"
    )


class QualityAnalysisResult(BaseModel):
    """Complete quality analysis output for a document.

    This is the top-level model serialized to JSONB in the database and
    returned by the GET /quality-analysis endpoint.
    """

    document_id: str = Field(description="Document this analysis belongs to")
    status: Literal["analyzing", "completed", "failed"] = Field(
        description="Quality analysis state"
    )
    inconsistencies: list[Inconsistency] = Field(
        default_factory=list,
        description="Detected contradictions and ambiguities",
    )
    missing_elements: list[MissingElement] = Field(
        default_factory=list,
        description="Missing or partial elements per document type schema",
    )
    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description="Actionable improvement suggestions",
    )
    metadata: QualityAnalysisMetadata | None = Field(
        default=None,
        description="Analysis metadata (present when status is completed)",
    )
    error_message: str | None = Field(
        default=None,
        description="Error details when status is failed",
    )
    error_phase: str | None = Field(
        default=None,
        description="Pipeline phase where the failure occurred",
    )
