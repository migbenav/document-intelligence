"""Pydantic v2 models for the Knowledge Model and analysis engine.

These models define the Knowledge Model structure, analysis session response shapes,
and type inference results used across the analysis pipeline.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """Traces a knowledge element back to its source in the original document."""

    document_id: str = Field(description="Document this element was extracted from")
    chunk_id: str = Field(description="IR chunk containing the evidence")
    page: int | None = Field(default=None, description="Page number (present for PDF documents)")
    section: str | None = Field(
        default=None, description="Section heading (present for Markdown documents)"
    )
    evidence: str = Field(description="Verbatim text span from the source document")


class Relation(BaseModel):
    """A directed relationship between two knowledge elements."""

    target_id: str = Field(description="ID of the target element in this relationship")
    type: Literal["constrains", "participates_in", "depends_on", "contradicts"] = Field(
        description="Relationship type from the fixed vocabulary"
    )
    description: str | None = Field(
        default=None, description="Optional brief description of the relationship"
    )


class KnowledgeElement(BaseModel):
    """A single unit of structured knowledge extracted from a document."""

    id: str = Field(description="Unique identifier for this element")
    type: Literal[
        "proposito", "concepto", "actor", "regla", "proceso", "restriccion"
    ] = Field(description="Element type from the fixed taxonomy")
    name: str = Field(description="Short name or label for this element")
    content: str = Field(description="Description or content of the element")
    source_ref: SourceRef = Field(description="Evidence reference to the source document")
    relations: list[Relation] = Field(
        default_factory=list, description="Relationships to other elements"
    )
    verified: bool = Field(
        default=False, description="Whether evidence was verified against the source"
    )


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process for reproducibility and auditing."""

    prompt_version: str = Field(description="Version of the prompt template used")
    model_id: str = Field(description="LLM model identifier that produced the result")
    temperature: float = Field(description="Temperature parameter used for generation")
    element_count: int = Field(description="Total number of elements extracted")
    relationship_count: int = Field(description="Total number of relationships identified")
    verification_rate: float = Field(
        description="Percentage of elements with verified evidence (0.0–1.0)"
    )
    extracted_at: datetime = Field(description="Timestamp when extraction was performed")


class KnowledgeModel(BaseModel):
    """The complete structured knowledge representation of a document."""

    document_id: str = Field(description="Document this Knowledge Model belongs to")
    document_type: str = Field(description="Confirmed document type used for extraction")
    elements: list[KnowledgeElement] = Field(description="Extracted knowledge elements")
    extraction_metadata: ExtractionMetadata = Field(
        description="Metadata about the extraction process"
    )


class AnalysisSession(BaseModel):
    """Response model for analysis session status."""

    id: str = Field(description="Unique session identifier")
    document_id: str = Field(description="Associated document identifier")
    status: str = Field(
        description="Session status: inferring_type | awaiting_confirmation | extracting | verifying | completed | failed"
    )
    suggested_type: str | None = Field(
        default=None, description="Inferred document type suggestion"
    )
    suggested_type_justification: str | None = Field(
        default=None, description="Justification for the type suggestion"
    )
    confirmed_type: str | None = Field(
        default=None, description="User-confirmed document type"
    )
    error_message: str | None = Field(
        default=None, description="Error details when status is failed"
    )
    created_at: datetime = Field(description="Session creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class TypeSuggestion(BaseModel):
    """Result of document type inference.

    When confidence is sufficient, document_type is set to the detected type.
    When confidence is low, document_type is None and suggested_type is "generic".
    suggested_type is always populated with the recommendation for the user.
    """

    document_type: str | None = Field(
        default=None,
        description="Detected document type, or None when confidence is low",
    )
    suggested_type: str = Field(
        description="Always populated with the recommendation (same as document_type when set, 'generic' when not)"
    )
    justification: str = Field(
        description="Brief justification for why this type was suggested"
    )
