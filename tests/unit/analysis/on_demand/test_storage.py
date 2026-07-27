"""Unit tests for OnDemandAnalysisStorage.

Verifies get_result, save_result, get_all_statuses, and mark_all_outdated
operations against a mocked Supabase client with method-chaining pattern.

Requirements: Req 6 (criteria 3, 5, 6), Req 7 (criteria 6, 7)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
)
from app.analysis.on_demand.storage import OnDemandAnalysisStorage

pytestmark = pytest.mark.asyncio


# --- Fixtures ---


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with method-chaining support."""
    client = MagicMock()
    return client


@pytest.fixture
def storage(mock_supabase) -> OnDemandAnalysisStorage:
    return OnDemandAnalysisStorage(mock_supabase)


@pytest.fixture
def sample_row() -> dict:
    """A typical row dict as returned by Supabase query."""
    return {
        "id": "result-001",
        "document_id": "doc-001",
        "analysis_type": "build_index",
        "status": "completed",
        "result": {"tree": [{"id": "n1", "title": "Introduction", "level": 1, "children": []}]},
        "model_id": "gemini/gemini-2.5-flash",
        "prompt_version": "build-index-v1",
        "error_message": None,
        "created_at": "2026-07-26T15:00:00+00:00",
        "updated_at": "2026-07-26T15:00:12+00:00",
    }


@pytest.fixture
def sample_record() -> AnalysisRecord:
    """An AnalysisRecord instance for save_result tests."""
    return AnalysisRecord(
        id="result-001",
        document_id="doc-001",
        analysis_type=AnalysisType.BUILD_INDEX,
        status=AnalysisStatus.COMPLETED,
        result={"tree": [{"id": "n1", "title": "Introduction", "level": 1, "children": []}]},
        model_id="gemini/gemini-2.5-flash",
        prompt_version="build-index-v1",
        error_message=None,
        created_at=datetime(2026, 7, 26, 15, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 26, 15, 0, 12, tzinfo=timezone.utc),
    )


# --- get_result Tests ---


class TestGetResult:
    async def test_returns_record_when_exists(self, storage, mock_supabase, sample_row):
        """get_result returns an AnalysisRecord when data exists."""
        mock_result = MagicMock()
        mock_result.data = [sample_row]
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = mock_result

        record = await storage.get_result("doc-001", AnalysisType.BUILD_INDEX)

        assert record is not None
        assert record.document_id == "doc-001"
        assert record.analysis_type == AnalysisType.BUILD_INDEX
        assert record.status == AnalysisStatus.COMPLETED
        assert record.result == {"tree": [{"id": "n1", "title": "Introduction", "level": 1, "children": []}]}
        assert record.model_id == "gemini/gemini-2.5-flash"
        assert record.prompt_version == "build-index-v1"
        assert record.error_message is None

        # Verify correct Supabase calls
        mock_supabase.table.assert_called_with("analysis_results")
        mock_supabase.table.return_value.select.assert_called_with("*")

    async def test_returns_none_when_not_exists(self, storage, mock_supabase):
        """get_result returns None when no result exists for the document + type."""
        mock_result = MagicMock()
        mock_result.data = []
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = mock_result

        record = await storage.get_result("doc-nonexistent", AnalysisType.CONCLUSIONS)

        assert record is None


# --- save_result Tests ---


class TestSaveResult:
    async def test_upserts_new_record(self, storage, mock_supabase, sample_record):
        """save_result calls Supabase upsert with correct record and conflict key."""
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = (
            MagicMock()
        )

        await storage.save_result(sample_record)

        # Verify table and upsert were called
        mock_supabase.table.assert_called_with("analysis_results")
        upsert_call = mock_supabase.table.return_value.upsert
        upsert_call.assert_called_once()

        # Verify the record passed to upsert
        record = upsert_call.call_args[0][0]
        assert record["document_id"] == "doc-001"
        assert record["analysis_type"] == "build_index"
        assert record["status"] == "completed"
        assert record["result"] == {"tree": [{"id": "n1", "title": "Introduction", "level": 1, "children": []}]}
        assert record["model_id"] == "gemini/gemini-2.5-flash"
        assert record["prompt_version"] == "build-index-v1"
        assert record["error_message"] is None
        assert "updated_at" in record

        # Verify on_conflict parameter
        assert upsert_call.call_args[1]["on_conflict"] == "document_id,analysis_type"

    async def test_upserts_existing_record(self, storage, mock_supabase):
        """save_result can update an existing result (same method, Supabase handles conflict)."""
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = (
            MagicMock()
        )

        updated_record = AnalysisRecord(
            id="result-001",
            document_id="doc-001",
            analysis_type=AnalysisType.BUILD_INDEX,
            status=AnalysisStatus.COMPLETED,
            result={"tree": [{"id": "n1", "title": "Updated Title", "level": 1, "children": []}]},
            model_id="gemini/gemini-2.5-flash",
            prompt_version="build-index-v1",
            error_message=None,
            created_at=datetime(2026, 7, 26, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, 16, 0, 0, tzinfo=timezone.utc),
        )

        await storage.save_result(updated_record)

        record = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert record["result"] == {"tree": [{"id": "n1", "title": "Updated Title", "level": 1, "children": []}]}
        assert record["document_id"] == "doc-001"
        assert record["analysis_type"] == "build_index"


# --- get_all_statuses Tests ---


class TestGetAllStatuses:
    async def test_returns_all_types_with_existing_and_defaults(
        self, storage, mock_supabase
    ):
        """get_all_statuses returns all 4 types, filling missing ones with not_started."""
        mock_result = MagicMock()
        mock_result.data = [
            {
                "analysis_type": "build_index",
                "status": "completed",
                "updated_at": "2026-07-26T15:00:12+00:00",
            },
            {
                "analysis_type": "conclusions",
                "status": "outdated",
                "updated_at": "2026-07-26T14:00:00+00:00",
            },
        ]
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .execute.return_value
        ) = mock_result

        statuses = await storage.get_all_statuses("doc-001")

        # Should have all 4 types
        assert len(statuses) == 4
        assert statuses["build_index"] == {
            "status": "completed",
            "updated_at": "2026-07-26T15:00:12+00:00",
        }
        assert statuses["conclusions"] == {
            "status": "outdated",
            "updated_at": "2026-07-26T14:00:00+00:00",
        }
        # Missing types default to not_started
        assert statuses["section_relations"] == {
            "status": "not_started",
            "updated_at": None,
        }
        assert statuses["questions_answered"] == {
            "status": "not_started",
            "updated_at": None,
        }

        # Verify correct Supabase calls
        mock_supabase.table.assert_called_with("analysis_results")
        mock_supabase.table.return_value.select.assert_called_with(
            "analysis_type, status, updated_at"
        )

    async def test_returns_all_not_started_when_no_rows(self, storage, mock_supabase):
        """get_all_statuses returns all types as not_started when no rows exist."""
        mock_result = MagicMock()
        mock_result.data = []
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .execute.return_value
        ) = mock_result

        statuses = await storage.get_all_statuses("doc-no-results")

        assert len(statuses) == 4
        for analysis_type in AnalysisType:
            assert statuses[analysis_type.value] == {
                "status": "not_started",
                "updated_at": None,
            }


# --- mark_all_outdated Tests ---


class TestMarkAllOutdated:
    async def test_marks_all_rows_outdated(self, storage, mock_supabase):
        """mark_all_outdated sets status='outdated' and updates updated_at."""
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock()
        )

        await storage.mark_all_outdated("doc-001")

        # Verify table called correctly
        mock_supabase.table.assert_called_with("analysis_results")

        # Verify update payload
        update_call = mock_supabase.table.return_value.update
        update_call.assert_called_once()
        update_payload = update_call.call_args[0][0]
        assert update_payload["status"] == "outdated"
        assert "updated_at" in update_payload

        # Verify eq filter
        mock_supabase.table.return_value.update.return_value.eq.assert_called_with(
            "document_id", "doc-001"
        )

    async def test_no_op_when_no_rows_exist(self, storage, mock_supabase):
        """mark_all_outdated completes without error even if no rows match."""
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock()
        )

        # Should not raise
        await storage.mark_all_outdated("doc-nonexistent")

        # Still calls the update (Supabase handles empty match set gracefully)
        mock_supabase.table.return_value.update.assert_called_once()
