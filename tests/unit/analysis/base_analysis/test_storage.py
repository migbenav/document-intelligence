"""Unit tests for BaseAnalysisStorage.

Verifies get_card, upsert_card, and mark_outdated operations against
a mocked Supabase client with method-chaining pattern.

Requirements: Req 4 (criteria 1, 3), Req 6 (criterion 1)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.analysis.base_analysis.storage import BaseAnalysisStorage
from app.models.document_card import (
    DocumentCard,
    DocumentCardStatistics,
    DocumentClassification,
    FileMetadata,
    OrganizationType,
)

pytestmark = pytest.mark.asyncio


# --- Fixtures ---


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with method-chaining support."""
    client = MagicMock()
    return client


@pytest.fixture
def storage(mock_supabase) -> BaseAnalysisStorage:
    return BaseAnalysisStorage(mock_supabase)


@pytest.fixture
def sample_row() -> dict:
    """A typical row dict as returned by Supabase query."""
    return {
        "id": "card-001",
        "document_id": "doc-001",
        "title": "Reglamento de Propiedad Horizontal",
        "summary": "Este documento establece normas de convivencia.",
        "classification": "normative",
        "organization_type": "numbered_articles",
        "statistics": {
            "total_chunks": 45,
            "sections_detected": 12,
            "hierarchy_levels": 3,
            "has_existing_index": True,
        },
        "file_metadata": {
            "size_bytes": 234500,
            "format": "pdf",
            "language": "es",
            "last_modified": "2026-07-20T14:30:00Z",
        },
        "status": "completed",
        "outdated": False,
        "model_id": "groq/llama-3.3-70b-versatile",
        "prompt_version": "base-analysis-v1",
        "created_at": "2026-07-26T10:30:00+00:00",
        "updated_at": "2026-07-26T10:30:04+00:00",
    }


@pytest.fixture
def sample_card() -> DocumentCard:
    """A DocumentCard instance for upsert tests."""
    return DocumentCard(
        id="card-001",
        document_id="doc-001",
        title="Reglamento de Propiedad Horizontal",
        summary="Este documento establece normas de convivencia.",
        classification=DocumentClassification.NORMATIVE,
        organization_type=OrganizationType.NUMBERED_ARTICLES,
        statistics=DocumentCardStatistics(
            total_chunks=45,
            sections_detected=12,
            hierarchy_levels=3,
            has_existing_index=True,
        ),
        file_metadata=FileMetadata(
            size_bytes=234500,
            format="pdf",
            language="es",
            last_modified=datetime(2026, 7, 20, 14, 30, 0, tzinfo=timezone.utc),
        ),
        status="completed",
        outdated=False,
        model_id="groq/llama-3.3-70b-versatile",
        prompt_version="base-analysis-v1",
        created_at=datetime(2026, 7, 26, 10, 30, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 26, 10, 30, 4, tzinfo=timezone.utc),
    )


# --- get_card Tests ---


class TestGetCard:
    async def test_returns_card_when_exists(self, storage, mock_supabase, sample_row):
        """get_card returns a DocumentCard when data exists for the document."""
        # Setup chained mock: table().select().eq().execute()
        mock_result = MagicMock()
        mock_result.data = [sample_row]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_result
        )

        card = await storage.get_card("doc-001")

        assert card is not None
        assert card.document_id == "doc-001"
        assert card.title == "Reglamento de Propiedad Horizontal"
        assert card.summary == "Este documento establece normas de convivencia."
        assert card.classification == DocumentClassification.NORMATIVE
        assert card.organization_type == OrganizationType.NUMBERED_ARTICLES
        assert card.statistics.total_chunks == 45
        assert card.file_metadata.size_bytes == 234500
        assert card.status == "completed"
        assert card.outdated is False

        # Verify correct Supabase calls
        mock_supabase.table.assert_called_with("document_cards")
        mock_supabase.table.return_value.select.assert_called_with("*")
        mock_supabase.table.return_value.select.return_value.eq.assert_called_with(
            "document_id", "doc-001"
        )

    async def test_returns_none_when_not_exists(self, storage, mock_supabase):
        """get_card returns None when no card exists for the document."""
        mock_result = MagicMock()
        mock_result.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_result
        )

        card = await storage.get_card("doc-nonexistent")

        assert card is None


# --- upsert_card Tests ---


class TestUpsertCard:
    async def test_upsert_inserts_new_card(self, storage, mock_supabase, sample_card):
        """upsert_card calls Supabase upsert with correct record and conflict key."""
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = (
            MagicMock()
        )

        await storage.upsert_card(sample_card)

        # Verify table and upsert were called
        mock_supabase.table.assert_called_with("document_cards")
        upsert_call = mock_supabase.table.return_value.upsert
        upsert_call.assert_called_once()

        # Verify the record passed to upsert
        record = upsert_call.call_args[0][0]
        assert record["document_id"] == "doc-001"
        assert record["title"] == "Reglamento de Propiedad Horizontal"
        assert record["summary"] == "Este documento establece normas de convivencia."
        assert record["classification"] == "normative"
        assert record["organization_type"] == "numbered_articles"
        assert record["status"] == "completed"
        assert record["model_id"] == "groq/llama-3.3-70b-versatile"
        assert record["prompt_version"] == "base-analysis-v1"
        assert "updated_at" in record

        # Verify on_conflict parameter
        assert upsert_call.call_args[1]["on_conflict"] == "document_id"

    async def test_upsert_updates_existing_card(self, storage, mock_supabase, sample_card):
        """upsert_card can update an existing card (same method, Supabase handles conflict)."""
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = (
            MagicMock()
        )

        # Modify the card to simulate an update
        updated_card = sample_card.model_copy(
            update={"summary": "Updated summary for the document."}
        )

        await storage.upsert_card(updated_card)

        record = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert record["summary"] == "Updated summary for the document."
        assert record["document_id"] == "doc-001"

    async def test_upsert_resets_outdated_to_false(self, storage, mock_supabase):
        """upsert_card always sets outdated=False regardless of card's outdated value."""
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = (
            MagicMock()
        )

        # Create a card that is marked as outdated
        outdated_card = DocumentCard(
            id="card-010",
            document_id="doc-010",
            title="Outdated Document",
            summary="Old summary",
            classification=DocumentClassification.GUIDE,
            organization_type=OrganizationType.HEADED_SECTIONS,
            statistics=DocumentCardStatistics(
                total_chunks=20,
                sections_detected=5,
                hierarchy_levels=2,
                has_existing_index=False,
            ),
            file_metadata=FileMetadata(size_bytes=50000, format="markdown"),
            status="completed",
            outdated=True,  # Card is outdated
            model_id="groq/llama-3.3-70b-versatile",
            prompt_version="base-analysis-v1",
            created_at=datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc),
        )

        await storage.upsert_card(outdated_card)

        record = mock_supabase.table.return_value.upsert.call_args[0][0]
        # Outdated must always be reset to False on upsert
        assert record["outdated"] is False


# --- mark_outdated Tests ---


class TestMarkOutdated:
    async def test_mark_outdated_sets_true(self, storage, mock_supabase):
        """mark_outdated sets outdated=True and updates updated_at timestamp."""
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock()
        )

        await storage.mark_outdated("doc-001")

        # Verify table called correctly
        mock_supabase.table.assert_called_with("document_cards")

        # Verify update payload
        update_call = mock_supabase.table.return_value.update
        update_call.assert_called_once()
        update_payload = update_call.call_args[0][0]
        assert update_payload["outdated"] is True
        assert "updated_at" in update_payload

        # Verify eq filter
        mock_supabase.table.return_value.update.return_value.eq.assert_called_with(
            "document_id", "doc-001"
        )
