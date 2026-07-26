"""Unit tests for the DocumentCard Pydantic v2 models.

Verifies serialization/deserialization round-trips, enum values,
nullable fields, and default values for the document card models.

Requirements: Req 4 (criterion 2)
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.document_card import (
    DocumentCard,
    DocumentCardStatistics,
    DocumentClassification,
    FileMetadata,
    OrganizationType,
)


# --- Fixtures ---


@pytest.fixture
def sample_statistics() -> DocumentCardStatistics:
    return DocumentCardStatistics(
        total_chunks=45,
        sections_detected=12,
        hierarchy_levels=3,
        has_existing_index=True,
    )


@pytest.fixture
def sample_file_metadata() -> FileMetadata:
    return FileMetadata(
        size_bytes=234500,
        format="pdf",
        language="es",
        last_modified=datetime(2026, 7, 20, 14, 30, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_completed_card(
    sample_statistics: DocumentCardStatistics,
    sample_file_metadata: FileMetadata,
) -> DocumentCard:
    return DocumentCard(
        id="card-001",
        document_id="doc-001",
        title="Reglamento de Propiedad Horizontal",
        summary="Este documento establece normas de convivencia.",
        classification=DocumentClassification.NORMATIVE,
        organization_type=OrganizationType.NUMBERED_ARTICLES,
        statistics=sample_statistics,
        file_metadata=sample_file_metadata,
        status="completed",
        outdated=False,
        model_id="groq/llama-3.3-70b-versatile",
        prompt_version="base-analysis-v1",
        created_at=datetime(2026, 7, 26, 10, 30, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 26, 10, 30, 4, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_partial_card(
    sample_statistics: DocumentCardStatistics,
    sample_file_metadata: FileMetadata,
) -> DocumentCard:
    return DocumentCard(
        id="card-002",
        document_id="doc-002",
        title="Manual de Usuario",
        summary=None,
        classification=None,
        organization_type=OrganizationType.HEADED_SECTIONS,
        statistics=sample_statistics,
        file_metadata=sample_file_metadata,
        status="partial",
        created_at=datetime(2026, 7, 26, 11, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 26, 11, 0, 0, tzinfo=timezone.utc),
    )


# --- OrganizationType Enum Tests ---


class TestOrganizationType:
    def test_enum_values_match_design(self):
        """Verify all organization type enum values match design specification."""
        assert OrganizationType.NUMBERED_ARTICLES.value == "numbered_articles"
        assert OrganizationType.HEADED_SECTIONS.value == "headed_sections"
        assert OrganizationType.HIERARCHICAL_NUMBERING.value == "hierarchical_numbering"
        assert OrganizationType.FREE_FORM.value == "free_form"

    def test_enum_has_exactly_four_values(self):
        assert len(OrganizationType) == 4

    def test_enum_is_str_subclass(self):
        """OrganizationType should serialize as its string value."""
        assert isinstance(OrganizationType.NUMBERED_ARTICLES, str)
        assert OrganizationType.FREE_FORM == "free_form"


# --- DocumentClassification Enum Tests ---


class TestDocumentClassification:
    def test_enum_values_match_design(self):
        """Verify all classification enum values match design specification."""
        assert DocumentClassification.NORMATIVE.value == "normative"
        assert DocumentClassification.GUIDE.value == "guide"
        assert DocumentClassification.MANUAL.value == "manual"
        assert DocumentClassification.PROCEDURE.value == "procedure"
        assert DocumentClassification.TECHNICAL.value == "technical"
        assert DocumentClassification.NARRATIVE.value == "narrative"
        assert DocumentClassification.OTHER.value == "other"

    def test_enum_has_exactly_seven_values(self):
        assert len(DocumentClassification) == 7

    def test_enum_is_str_subclass(self):
        """DocumentClassification should serialize as its string value."""
        assert isinstance(DocumentClassification.NORMATIVE, str)
        assert DocumentClassification.OTHER == "other"


# --- DocumentCardStatistics Tests ---


class TestDocumentCardStatistics:
    def test_serialization(self, sample_statistics: DocumentCardStatistics):
        data = sample_statistics.model_dump()
        assert data["total_chunks"] == 45
        assert data["sections_detected"] == 12
        assert data["hierarchy_levels"] == 3
        assert data["has_existing_index"] is True

    def test_json_round_trip(self, sample_statistics: DocumentCardStatistics):
        json_str = sample_statistics.model_dump_json()
        restored = DocumentCardStatistics.model_validate_json(json_str)
        assert restored == sample_statistics

    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            DocumentCardStatistics(
                total_chunks=10,
                sections_detected=2,
                # missing hierarchy_levels and has_existing_index
            )


# --- FileMetadata Tests ---


class TestFileMetadata:
    def test_serialization_with_all_fields(self, sample_file_metadata: FileMetadata):
        data = sample_file_metadata.model_dump()
        assert data["size_bytes"] == 234500
        assert data["format"] == "pdf"
        assert data["language"] == "es"
        assert data["last_modified"] is not None

    def test_language_and_last_modified_optional(self):
        metadata = FileMetadata(size_bytes=1000, format="markdown")
        assert metadata.language is None
        assert metadata.last_modified is None

    def test_json_round_trip(self, sample_file_metadata: FileMetadata):
        json_str = sample_file_metadata.model_dump_json()
        restored = FileMetadata.model_validate_json(json_str)
        assert restored == sample_file_metadata

    def test_size_bytes_and_format_required(self):
        with pytest.raises(ValidationError):
            FileMetadata(size_bytes=500)  # missing format


# --- DocumentCard Tests ---


class TestDocumentCard:
    def test_completed_card_serialization(self, sample_completed_card: DocumentCard):
        data = sample_completed_card.model_dump()
        assert data["id"] == "card-001"
        assert data["document_id"] == "doc-001"
        assert data["title"] == "Reglamento de Propiedad Horizontal"
        assert data["summary"] == "Este documento establece normas de convivencia."
        assert data["classification"] == DocumentClassification.NORMATIVE
        assert data["organization_type"] == OrganizationType.NUMBERED_ARTICLES
        assert data["status"] == "completed"
        assert data["outdated"] is False
        assert data["model_id"] == "groq/llama-3.3-70b-versatile"
        assert data["prompt_version"] == "base-analysis-v1"

    def test_json_round_trip_completed(self, sample_completed_card: DocumentCard):
        json_str = sample_completed_card.model_dump_json()
        restored = DocumentCard.model_validate_json(json_str)
        assert restored == sample_completed_card

    def test_json_round_trip_partial(self, sample_partial_card: DocumentCard):
        json_str = sample_partial_card.model_dump_json()
        restored = DocumentCard.model_validate_json(json_str)
        assert restored == sample_partial_card

    def test_nullable_fields_when_partial(self, sample_partial_card: DocumentCard):
        """summary and classification are null when status is partial."""
        assert sample_partial_card.summary is None
        assert sample_partial_card.classification is None
        data = sample_partial_card.model_dump()
        assert data["summary"] is None
        assert data["classification"] is None

    def test_outdated_defaults_to_false(
        self,
        sample_statistics: DocumentCardStatistics,
        sample_file_metadata: FileMetadata,
    ):
        """The outdated field should default to False when not explicitly set."""
        card = DocumentCard(
            id="card-003",
            document_id="doc-003",
            title="Test Document",
            organization_type=OrganizationType.FREE_FORM,
            statistics=sample_statistics,
            file_metadata=sample_file_metadata,
            status="partial",
            created_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert card.outdated is False

    def test_outdated_can_be_set_true(
        self,
        sample_statistics: DocumentCardStatistics,
        sample_file_metadata: FileMetadata,
    ):
        card = DocumentCard(
            id="card-004",
            document_id="doc-004",
            title="Outdated Document",
            organization_type=OrganizationType.HIERARCHICAL_NUMBERING,
            statistics=sample_statistics,
            file_metadata=sample_file_metadata,
            status="completed",
            outdated=True,
            summary="Summary text",
            classification=DocumentClassification.TECHNICAL,
            created_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert card.outdated is True

    def test_status_literal_completed(self, sample_completed_card: DocumentCard):
        assert sample_completed_card.status == "completed"

    def test_status_literal_partial(self, sample_partial_card: DocumentCard):
        assert sample_partial_card.status == "partial"

    def test_status_literal_failed_llm(
        self,
        sample_statistics: DocumentCardStatistics,
        sample_file_metadata: FileMetadata,
    ):
        card = DocumentCard(
            id="card-005",
            document_id="doc-005",
            title="Failed LLM Card",
            organization_type=OrganizationType.FREE_FORM,
            statistics=sample_statistics,
            file_metadata=sample_file_metadata,
            status="failed_llm",
            created_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert card.status == "failed_llm"

    def test_invalid_status_rejected(
        self,
        sample_statistics: DocumentCardStatistics,
        sample_file_metadata: FileMetadata,
    ):
        with pytest.raises(ValidationError):
            DocumentCard(
                id="card-006",
                document_id="doc-006",
                title="Bad Status",
                organization_type=OrganizationType.FREE_FORM,
                statistics=sample_statistics,
                file_metadata=sample_file_metadata,
                status="invalid_status",
                created_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            )

    def test_model_id_and_prompt_version_default_none(
        self,
        sample_statistics: DocumentCardStatistics,
        sample_file_metadata: FileMetadata,
    ):
        card = DocumentCard(
            id="card-007",
            document_id="doc-007",
            title="No LLM Fields",
            organization_type=OrganizationType.FREE_FORM,
            statistics=sample_statistics,
            file_metadata=sample_file_metadata,
            status="partial",
            created_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert card.model_id is None
        assert card.prompt_version is None

    def test_nested_statistics_in_card(self, sample_completed_card: DocumentCard):
        data = sample_completed_card.model_dump()
        stats = data["statistics"]
        assert stats["total_chunks"] == 45
        assert stats["sections_detected"] == 12
        assert stats["hierarchy_levels"] == 3
        assert stats["has_existing_index"] is True

    def test_nested_file_metadata_in_card(self, sample_completed_card: DocumentCard):
        data = sample_completed_card.model_dump()
        meta = data["file_metadata"]
        assert meta["size_bytes"] == 234500
        assert meta["format"] == "pdf"
        assert meta["language"] == "es"
