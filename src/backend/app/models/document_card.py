"""Pydantic v2 models for the Document Card produced by the base analysis.

These models define the structured summary (document card) that combines
local processing results with a single LLM call to classify and summarize
a document. See ADR-007 Nivel 1 and PRD v2 capability C2.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class OrganizationType(str, Enum):
    """How the document is structurally organized.

    Determined during local processing by pattern matching on the IR chunks.
    Priority order for detection: numbered_articles > headed_sections >
    hierarchical_numbering > free_form.
    """

    NUMBERED_ARTICLES = "numbered_articles"
    HEADED_SECTIONS = "headed_sections"
    HIERARCHICAL_NUMBERING = "hierarchical_numbering"
    FREE_FORM = "free_form"


class DocumentClassification(str, Enum):
    """Functional category of the document, determined by the LLM.

    Used to determine which on-demand analyses are relevant for the document.
    """

    NORMATIVE = "normative"
    GUIDE = "guide"
    MANUAL = "manual"
    PROCEDURE = "procedure"
    TECHNICAL = "technical"
    NARRATIVE = "narrative"
    OTHER = "other"


class DocumentCardStatistics(BaseModel):
    """Structural statistics computed during local processing."""

    total_chunks: int = Field(description="Total number of chunks in the IR")
    sections_detected: int = Field(
        description="Count of unique sections detected (distinct structural_context.section values)"
    )
    hierarchy_levels: int = Field(
        description="Maximum hierarchy level found (from structural_context.level, default 1)"
    )
    has_existing_index: bool = Field(
        description="Whether a table of contents was detected in the first 20% of the document"
    )


class FileMetadata(BaseModel):
    """File-level metadata extracted from the IR metadata during local processing."""

    size_bytes: int = Field(description="Size of the uploaded file in bytes")
    format: str = Field(description="Document format: markdown, plain_text, or pdf")
    language: str | None = Field(
        default=None, description="Detected language code: es, en, or unknown"
    )
    last_modified: datetime | None = Field(
        default=None, description="Last modification timestamp of the source file"
    )


class DocumentCard(BaseModel):
    """The structured summary produced by the base analysis.

    Combines local processing results (title, statistics, organization type,
    file metadata) with LLM-derived fields (summary, classification). When the
    LLM fails, summary and classification are null and status is 'partial'.

    One card per document (unique constraint on document_id).
    """

    id: str = Field(description="UUID primary key for the card record")
    document_id: str = Field(
        description="FK to documents table (unique — one card per document)"
    )
    title: str = Field(description="Document title extracted from first heading or filename")
    summary: str | None = Field(
        default=None,
        description="2-3 line summary from LLM. Null when status is partial.",
    )
    classification: DocumentClassification | None = Field(
        default=None,
        description="Document classification from LLM. Null when status is partial.",
    )
    organization_type: OrganizationType = Field(
        description="Structural organization type detected during local processing"
    )
    statistics: DocumentCardStatistics = Field(
        description="Structural statistics computed during local processing"
    )
    file_metadata: FileMetadata = Field(
        description="File-level metadata from the IR"
    )
    status: Literal["completed", "failed_llm", "partial"] = Field(
        description="Card status: completed (all fields), partial (LLM failed), failed_llm (retry also failed)"
    )
    outdated: bool = Field(
        default=False,
        description="True when the document has changed since last analysis (size_bytes differs)",
    )
    model_id: str | None = Field(
        default=None,
        description="LLM model identifier that produced the summary. Null if partial.",
    )
    prompt_version: str | None = Field(
        default=None,
        description="Prompt version used for the LLM call. Null if partial.",
    )
    created_at: datetime = Field(description="Timestamp when the card was first created")
    updated_at: datetime = Field(description="Timestamp of the last card update")
