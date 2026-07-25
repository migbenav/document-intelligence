"""Unit tests for the Knowledge Model Pydantic models.

Verifies serialization, validation, and edge cases for all models
defined in app.models.knowledge_model.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.knowledge_model import (
    AnalysisSession,
    ExtractionMetadata,
    KnowledgeElement,
    KnowledgeModel,
    Relation,
    SourceRef,
    TypeSuggestion,
)


# --- Fixtures ---


@pytest.fixture
def sample_source_ref() -> SourceRef:
    return SourceRef(
        document_id="doc-001",
        chunk_id="chunk-001",
        page=3,
        section="# Introduction",
        evidence="The system shall process documents automatically.",
    )


@pytest.fixture
def sample_relation() -> Relation:
    return Relation(
        target_id="elem-002",
        type="constrains",
        description="Limits processing speed",
    )


@pytest.fixture
def sample_element(sample_source_ref: SourceRef, sample_relation: Relation) -> KnowledgeElement:
    return KnowledgeElement(
        id="elem-001",
        type="proposito",
        name="System Purpose",
        content="The system processes documents automatically.",
        source_ref=sample_source_ref,
        relations=[sample_relation],
        verified=True,
    )


@pytest.fixture
def sample_metadata() -> ExtractionMetadata:
    return ExtractionMetadata(
        prompt_version="extraction-v1",
        model_id="gemini/gemini-2.5-flash-preview-05-20",
        temperature=0.1,
        element_count=5,
        relationship_count=3,
        verification_rate=0.8,
        extracted_at=datetime(2026, 7, 24, 15, 30, 0, tzinfo=timezone.utc),
    )


# --- SourceRef Tests ---


class TestSourceRef:
    def test_serialization_with_all_fields(self, sample_source_ref: SourceRef):
        data = sample_source_ref.model_dump()
        assert data["document_id"] == "doc-001"
        assert data["chunk_id"] == "chunk-001"
        assert data["page"] == 3
        assert data["section"] == "# Introduction"
        assert data["evidence"] == "The system shall process documents automatically."

    def test_page_and_section_optional(self):
        ref = SourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="Some evidence text",
        )
        assert ref.page is None
        assert ref.section is None

    def test_evidence_required(self):
        with pytest.raises(ValidationError):
            SourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
            )

    def test_json_round_trip(self, sample_source_ref: SourceRef):
        json_str = sample_source_ref.model_dump_json()
        restored = SourceRef.model_validate_json(json_str)
        assert restored == sample_source_ref


# --- Relation Tests ---


class TestRelation:
    def test_valid_relation_types(self):
        for rel_type in ["constrains", "participates_in", "depends_on", "contradicts"]:
            relation = Relation(target_id="elem-002", type=rel_type)
            assert relation.type == rel_type

    def test_invalid_relation_type_rejected(self):
        with pytest.raises(ValidationError):
            Relation(target_id="elem-002", type="invalid_type")

    def test_description_optional(self):
        relation = Relation(target_id="elem-002", type="depends_on")
        assert relation.description is None

    def test_serialization(self, sample_relation: Relation):
        data = sample_relation.model_dump()
        assert data["target_id"] == "elem-002"
        assert data["type"] == "constrains"
        assert data["description"] == "Limits processing speed"


# --- KnowledgeElement Tests ---


class TestKnowledgeElement:
    def test_valid_element_types(self, sample_source_ref: SourceRef):
        for elem_type in ["proposito", "concepto", "actor", "regla", "proceso", "restriccion"]:
            elem = KnowledgeElement(
                id="elem-001",
                type=elem_type,
                name="Test",
                content="Content",
                source_ref=sample_source_ref,
            )
            assert elem.type == elem_type

    def test_invalid_element_type_rejected(self, sample_source_ref: SourceRef):
        with pytest.raises(ValidationError):
            KnowledgeElement(
                id="elem-001",
                type="invalid_type",
                name="Test",
                content="Content",
                source_ref=sample_source_ref,
            )

    def test_relations_default_empty(self, sample_source_ref: SourceRef):
        elem = KnowledgeElement(
            id="elem-001",
            type="concepto",
            name="Test Concept",
            content="A test concept",
            source_ref=sample_source_ref,
        )
        assert elem.relations == []

    def test_verified_defaults_false(self, sample_source_ref: SourceRef):
        elem = KnowledgeElement(
            id="elem-001",
            type="actor",
            name="User",
            content="System user",
            source_ref=sample_source_ref,
        )
        assert elem.verified is False

    def test_full_serialization(self, sample_element: KnowledgeElement):
        data = sample_element.model_dump()
        assert data["id"] == "elem-001"
        assert data["type"] == "proposito"
        assert data["verified"] is True
        assert len(data["relations"]) == 1
        assert data["source_ref"]["evidence"] == "The system shall process documents automatically."

    def test_json_round_trip(self, sample_element: KnowledgeElement):
        json_str = sample_element.model_dump_json()
        restored = KnowledgeElement.model_validate_json(json_str)
        assert restored == sample_element


# --- ExtractionMetadata Tests ---


class TestExtractionMetadata:
    def test_serialization(self, sample_metadata: ExtractionMetadata):
        data = sample_metadata.model_dump()
        assert data["prompt_version"] == "extraction-v1"
        assert data["model_id"] == "gemini/gemini-2.5-flash-preview-05-20"
        assert data["temperature"] == 0.1
        assert data["element_count"] == 5
        assert data["relationship_count"] == 3
        assert data["verification_rate"] == 0.8

    def test_extracted_at_serialization(self, sample_metadata: ExtractionMetadata):
        data = sample_metadata.model_dump(mode="json")
        # datetime should serialize to ISO format string in JSON mode
        assert "2026-07-24" in data["extracted_at"]

    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            ExtractionMetadata(
                prompt_version="v1",
                model_id="model",
                # missing temperature and other fields
            )


# --- KnowledgeModel Tests ---


class TestKnowledgeModel:
    def test_full_model_serialization(
        self, sample_element: KnowledgeElement, sample_metadata: ExtractionMetadata
    ):
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[sample_element],
            extraction_metadata=sample_metadata,
        )
        data = km.model_dump()
        assert data["document_id"] == "doc-001"
        assert data["document_type"] == "prd"
        assert len(data["elements"]) == 1
        assert data["extraction_metadata"]["prompt_version"] == "extraction-v1"

    def test_empty_elements_list(self, sample_metadata: ExtractionMetadata):
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="generic",
            elements=[],
            extraction_metadata=sample_metadata,
        )
        assert km.elements == []

    def test_json_round_trip(
        self, sample_element: KnowledgeElement, sample_metadata: ExtractionMetadata
    ):
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="technical_spec",
            elements=[sample_element],
            extraction_metadata=sample_metadata,
        )
        json_str = km.model_dump_json()
        restored = KnowledgeModel.model_validate_json(json_str)
        assert restored == km


# --- AnalysisSession Tests ---


class TestAnalysisSession:
    def test_full_session_serialization(self):
        session = AnalysisSession(
            id="session-001",
            document_id="doc-001",
            status="awaiting_confirmation",
            suggested_type="prd",
            suggested_type_justification="Document contains user stories and acceptance criteria.",
            confirmed_type=None,
            error_message=None,
            created_at=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 24, 10, 5, 0, tzinfo=timezone.utc),
        )
        data = session.model_dump()
        assert data["id"] == "session-001"
        assert data["status"] == "awaiting_confirmation"
        assert data["suggested_type"] == "prd"
        assert data["confirmed_type"] is None

    def test_optional_fields_default_none(self):
        session = AnalysisSession(
            id="session-002",
            document_id="doc-002",
            status="inferring_type",
            created_at=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert session.suggested_type is None
        assert session.suggested_type_justification is None
        assert session.confirmed_type is None
        assert session.error_message is None

    def test_failed_session_with_error(self):
        session = AnalysisSession(
            id="session-003",
            document_id="doc-003",
            status="failed",
            error_message="LLM response could not be parsed.",
            created_at=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 24, 10, 1, 0, tzinfo=timezone.utc),
        )
        assert session.status == "failed"
        assert session.error_message == "LLM response could not be parsed."

    def test_json_round_trip(self):
        session = AnalysisSession(
            id="session-001",
            document_id="doc-001",
            status="completed",
            suggested_type="prd",
            suggested_type_justification="Contains PRD sections.",
            confirmed_type="prd",
            created_at=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 24, 11, 0, 0, tzinfo=timezone.utc),
        )
        json_str = session.model_dump_json()
        restored = AnalysisSession.model_validate_json(json_str)
        assert restored == session


# --- TypeSuggestion Tests ---


class TestTypeSuggestion:
    def test_high_confidence_type_set(self):
        suggestion = TypeSuggestion(
            document_type="prd",
            suggested_type="prd",
            justification="Document contains user stories, acceptance criteria, and product requirements.",
        )
        assert suggestion.document_type == "prd"
        assert suggestion.suggested_type == "prd"

    def test_low_confidence_document_type_none(self):
        """When confidence is low, document_type is None and suggested_type is 'generic' (Req 3.3)."""
        suggestion = TypeSuggestion(
            document_type=None,
            suggested_type="generic",
            justification="Could not classify with sufficient confidence.",
        )
        assert suggestion.document_type is None
        assert suggestion.suggested_type == "generic"

    def test_unset_document_type_defaults_none(self):
        """TypeSuggestion supports omitting document_type entirely (defaults to None)."""
        suggestion = TypeSuggestion(
            suggested_type="generic",
            justification="Ambiguous document structure.",
        )
        assert suggestion.document_type is None

    def test_serialization_with_none_type(self):
        suggestion = TypeSuggestion(
            document_type=None,
            suggested_type="generic",
            justification="Low confidence classification.",
        )
        data = suggestion.model_dump()
        assert data["document_type"] is None
        assert data["suggested_type"] == "generic"
        assert data["justification"] == "Low confidence classification."

    def test_json_round_trip(self):
        suggestion = TypeSuggestion(
            document_type="technical_spec",
            suggested_type="technical_spec",
            justification="Contains API specifications and architecture diagrams.",
        )
        json_str = suggestion.model_dump_json()
        restored = TypeSuggestion.model_validate_json(json_str)
        assert restored == suggestion

    def test_justification_required(self):
        with pytest.raises(ValidationError):
            TypeSuggestion(
                suggested_type="generic",
                # missing justification
            )
