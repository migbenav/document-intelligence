"""Pydantic v2 models for On-Demand Analysis results.

These models define the structured outputs for the four document-level analyses
(Build Index, Section Relations, Questions Answered, Conclusions) and the
persisted AnalysisRecord. See ADR-007 Nivel 2 and PRD v2 capability C3.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class AnalysisType(str, Enum):
    """The four on-demand analysis types available after the base card."""

    BUILD_INDEX = "build_index"
    SECTION_RELATIONS = "section_relations"
    QUESTIONS_ANSWERED = "questions_answered"
    CONCLUSIONS = "conclusions"


class AnalysisStatus(str, Enum):
    """Lifecycle status of a specific analysis for a document."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OUTDATED = "outdated"
    FAILED = "failed"


# --- Source Reference (shared across all results) ---


class SourceRef(BaseModel):
    """Reference to the document text that supports a result element.

    Provides evidence traceability per ADR-004: every result is traceable
    back to specific chunks in the document's intermediate representation.
    """

    chunk_ids: list[str] = Field(description="IR chunk IDs that support this element")
    text_excerpt: str = Field(
        description="Relevant text passage from the document (max 500 characters)",
    )
    section: Optional[str] = Field(
        default=None,
        description="Section name where the referenced text appears",
    )

    @field_validator("text_excerpt", mode="before")
    @classmethod
    def truncate_text_excerpt(cls, v: str) -> str:
        """Truncate text_excerpt to 500 chars if LLM exceeds the limit."""
        if isinstance(v, str) and len(v) > 500:
            return v[:497] + "..."
        return v


# --- Build Index Result (C3.1) ---


class StructureNode(BaseModel):
    """A node in the document structure tree produced by Build Index.

    Each node represents a section or subsection, preserving the document's
    original ordering with a maximum depth of 6 levels.
    """

    id: str = Field(description="Unique identifier for this node")
    title: str = Field(description="Section heading or inferred label")
    level: int = Field(
        ge=1,
        le=6,
        description="Hierarchy depth (1=top-level, max 6)",
    )
    role: Optional[str] = Field(
        default=None,
        description=(
            "Functional role of this section: defines, classifies, establishes, "
            "regulates, recommends, lists, restricts, describes, enables, "
            "controls, delegates — or null if undetermined"
        ),
    )
    functional_group: Optional[str] = Field(
        default=None,
        description=(
            "Functional grouping this node belongs to (v2). Multiple sections "
            "serving the same function share a functional_group label."
        ),
    )
    original_headings: list[str] = Field(
        default_factory=list,
        description=(
            "Original document headings that were merged into this functional node (v2). "
            "Empty for v1 results or when the node maps 1:1 to a heading."
        ),
    )
    question_answered: Optional[str] = Field(
        default=None,
        description=(
            "The question this section answers in the cascade pattern "
            "(e.g., 'How are purchases requested?')"
        ),
    )
    source_ref: Optional["SourceRef"] = Field(
        default=None,
        description="Reference to the source text supporting this node",
    )
    children: list["StructureNode"] = Field(
        default_factory=list,
        description="Child nodes (subsections) in document order",
    )

    _VALID_ROLES = {
        # v1 roles
        "defines", "classifies", "establishes", "regulates",
        "recommends", "lists", "restricts", "describes",
        # v2 roles
        "enables", "controls", "delegates",
    }

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        """Accept known role values; pass through unknown ones for forward compat."""
        # None is valid (undetermined role)
        if v is None:
            return v
        # Normalize to lowercase for consistency
        if isinstance(v, str):
            return v.lower()
        return v


class IndexResult(BaseModel):
    """Result of the Build Index analysis — a hierarchical structure tree."""

    tree: list[StructureNode] = Field(
        description="Top-level nodes of the document structure tree"
    )
    document_purpose: Optional[str] = Field(
        default=None,
        description=(
            "One-sentence summary of the document's overall purpose (v2). "
            "None for v1 results."
        ),
    )


# --- Section Relations Result (C3.2) ---


class SectionRelation(BaseModel):
    """A directed relationship between two document sections."""

    source_section: str = Field(
        description="Title or node ID of the originating section"
    )
    target_section: str = Field(
        description="Title or node ID of the related section"
    )
    type: Literal[
        "constrains", "depends_on", "complements", "contradicts",
        "enables", "restricts", "requires", "implements",
    ] = Field(
        description="Relationship type from the controlled vocabulary"
    )
    description: str = Field(
        description="One-sentence explanation of the relationship (in ui_language)"
    )
    domain: str | None = Field(
        default=None,
        description="Domain/topic this relationship belongs to (e.g., 'parking', 'elevators')",
    )
    source_ref: Optional["SourceRef"] = Field(
        default=None,
        description="Reference to the source text evidencing this relationship",
    )


class RelationsResult(BaseModel):
    """Result of the Section Relations analysis — a list of inter-section relationships."""

    relations: list[SectionRelation] = Field(
        description="Significant relationships between document sections"
    )


# --- Questions Answered Result (C3.3) ---


class AnsweredQuestion(BaseModel):
    """A question that the document addresses, at document or section level."""

    question: str = Field(
        description="Well-formed question in ui_language specific to the content"
    )
    level: Literal["document", "section"] = Field(
        description="Whether this is a document-level or section-level question"
    )
    section_title: Optional[str] = Field(
        default=None,
        description="Which section answers this question (None for document-level)",
    )
    source_ref: Optional["SourceRef"] = Field(
        default=None,
        description="Reference to the section/chunk that addresses this question",
    )


class QuestionsResult(BaseModel):
    """Result of the Questions Answered analysis — a cascade of questions."""

    document_questions: list[AnsweredQuestion] = Field(
        description="3-5 global purpose questions about the document's overall scope"
    )
    section_questions: list[AnsweredQuestion] = Field(
        description="1-2 questions per major section about what each section contributes"
    )
    coherence_note: str | None = Field(
        default=None,
        description="Note explaining why the document lacks a coherent logical chain, if applicable",
    )


# --- Conclusions & Recommendations Result (C3.4) ---


class Observation(BaseModel):
    """A structural observation about the document's organization."""

    category: Literal[
        "coherence",
        "reordering",
        "duplication",
        "orphan",
        "missing",
        "purpose_mismatch",
        "misplaced_content",
        "title_mismatch",
        "sequence_issue",
        "contradiction",
    ] = Field(description="Observation category")
    description: str = Field(
        description="Explanation of the observation (in ui_language)"
    )
    suggestion: str = Field(
        description=(
            "Structural recommendation in document_language "
            "(move, split, merge, add, remove section — NOT content text suggestions)"
        ),
    )
    section_ref: Optional[str] = Field(
        default=None,
        description="Which section(s) the observation refers to",
    )
    domain: Optional[str] = Field(
        default=None,
        description="The domain/topic this observation belongs to (e.g., 'parking', 'elevators')",
    )
    source_ref: Optional["SourceRef"] = Field(
        default=None,
        description="Reference to the source text supporting this observation",
    )


class ConclusionsResult(BaseModel):
    """Result of the Conclusions & Recommendations analysis — structural observations."""

    observations: list[Observation] = Field(
        description="3-15 structural observations prioritized by impact"
    )
    domains_identified: list[str] = Field(
        default_factory=list,
        description="Independent domains/topics identified in the document (e.g., 'parking', 'elevators', 'common areas')",
    )


# --- Persisted Record ---


class AnalysisRecord(BaseModel):
    """A persisted analysis result record stored in the analysis_results table.

    One record per (document_id, analysis_type) combination. The result field
    contains the JSON-serialized typed result (IndexResult, RelationsResult,
    QuestionsResult, or ConclusionsResult).
    """

    id: str = Field(description="UUID primary key")
    document_id: str = Field(description="FK to documents table")
    analysis_type: AnalysisType = Field(description="Which analysis this record is for")
    status: AnalysisStatus = Field(description="Current lifecycle status")
    result: Optional[dict] = Field(
        default=None,
        description="JSON-serialized analysis result (type depends on analysis_type)",
    )
    model_id: Optional[str] = Field(
        default=None,
        description="LLM model identifier that produced this result",
    )
    requested_model: Optional[str] = Field(
        default=None,
        description="Model originally requested by the user (may differ from model_id if fallback was used)",
    )
    fallback_used: bool = Field(
        default=False,
        description="Whether a fallback model was used instead of the requested model",
    )
    prompt_version: Optional[str] = Field(
        default=None,
        description="Prompt version used for the LLM call",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if status is 'failed'",
    )
    created_at: datetime = Field(description="Timestamp when the record was created")
    updated_at: datetime = Field(description="Timestamp of the last update")
