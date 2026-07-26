"""Pydantic v2 models for the Natural Language Query feature.

These models define the request/response shapes for the query API endpoint,
the internal context construction types, and error response formats.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request body for the query endpoint."""

    question: str = Field(
        min_length=1, max_length=1000, description="Natural language question about the document"
    )


class QuerySourceRef(BaseModel):
    """A source reference linking a query response claim to the original document."""

    document_id: str = Field(description="Document this evidence was extracted from")
    chunk_id: str = Field(description="IR chunk containing the evidence")
    page: int | None = Field(default=None, description="Page number (present for PDF documents)")
    section: str | None = Field(
        default=None, description="Section heading (present for Markdown documents)"
    )
    evidence: str = Field(
        max_length=500, description="Verbatim text span from the source document"
    )
    evidence_verified: bool = Field(
        default=False,
        description="Whether evidence was verified against the source document IR",
    )


class QueryMetadata(BaseModel):
    """Auditing metadata for query reproducibility."""

    prompt_version: str = Field(description="Version of the prompt template used")
    model_id: str = Field(description="LLM model identifier that produced the response")
    temperature: float = Field(description="Temperature parameter used for generation")
    timestamp: datetime = Field(description="Timestamp of query execution in UTC")


class QueryResponse(BaseModel):
    """Complete response to a natural language query."""

    answer: str = Field(max_length=5000, description="Answer text generated from the Knowledge Model")
    answerable: bool = Field(
        description="True if answered from context, False if question cannot be answered"
    )
    source_refs: list[QuerySourceRef] = Field(
        default_factory=list,
        max_length=10,
        description="Evidence references linking claims to the original document",
    )
    all_evidence_unverified: bool = Field(
        default=False,
        description="True when all source_refs have evidence_verified=False",
    )
    metadata: QueryMetadata = Field(description="Auditing metadata for reproducibility")


class QueryErrorResponse(BaseModel):
    """Error response for query failures."""

    error: str = Field(
        description="Error code: query_failed, response_parse_error, km_not_completed, not_found"
    )
    message: str = Field(description="Human-readable error description")
    question: str | None = Field(
        default=None, description="Original question (included for parse errors)"
    )


class QueryContextElement(BaseModel):
    """A Knowledge Model element formatted for inclusion in the query context."""

    element_id: str = Field(description="Unique identifier for this element")
    type: str = Field(description="Element type from the KM taxonomy")
    name: str = Field(description="Short name or label for this element")
    content: str = Field(description="Description or content of the element")
    evidence: str = Field(description="Evidence text span from the source document")
    verified: bool = Field(description="Whether evidence was verified against the source")


class QueryContextRelation(BaseModel):
    """A relation entry included in the query context."""

    source_id: str = Field(description="ID of the source element in this relationship")
    target_id: str = Field(description="ID of the target element in this relationship")
    type: str = Field(description="Relationship type (constrains, participates_in, depends_on, contradicts)")
    description: str | None = Field(
        default=None, description="Optional brief description of the relationship"
    )


class QueryContext(BaseModel):
    """The assembled context for the LLM query prompt."""

    elements: list[QueryContextElement] = Field(
        default_factory=list, description="Selected KM elements for context"
    )
    relations: list[QueryContextRelation] = Field(
        default_factory=list, description="First-degree relations between context elements"
    )
    total_tokens: int = Field(description="Estimated token count of the assembled context")
    has_unverified_elements: bool = Field(
        description="Whether any element in the context has verified=False"
    )
