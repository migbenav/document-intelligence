"""Unit tests for OnDemandAnalysisService.

Verifies execute (idempotency, outdated handling, LLM failure propagation,
IR not available), get_result delegation, and get_all_statuses delegation.
All tests mock analyzers, storage, and ingestion_storage.

Requirements: Req 6 (criteria 1-8)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
    IndexResult,
    RelationsResult,
    QuestionsResult,
    ConclusionsResult,
)
from app.analysis.on_demand.service import (
    DocumentIRNotAvailableError,
    OnDemandAnalysisService,
)
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)

pytestmark = pytest.mark.asyncio


# --- Fixtures ---


def _make_ir() -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="policy.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=2048,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="c1",
                text="Introduction to the policy.",
                structural_context={"section": "Introduction"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="c2",
                text="Details of the procedure.",
                structural_context={"section": "Procedure"},
                order=1,
            ),
        ],
    )


def _make_completed_record(
    analysis_type: AnalysisType = AnalysisType.BUILD_INDEX,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
) -> AnalysisRecord:
    """Create a completed AnalysisRecord for testing."""
    return AnalysisRecord(
        id="result-001",
        document_id="doc-001",
        analysis_type=analysis_type,
        status=status,
        result={"tree": [{"id": "n1", "title": "Intro", "level": 1, "children": []}]},
        model_id="gemini/gemini-2.5-flash",
        prompt_version="build-index-v1",
        error_message=None,
        created_at=datetime(2026, 7, 26, 15, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 26, 15, 0, 12, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_index_analyzer():
    analyzer = MagicMock()
    analyzer.prompt_version = "build-index-v1"
    analyzer.analyze = AsyncMock(
        return_value=IndexResult(tree=[])
    )
    return analyzer


@pytest.fixture
def mock_relations_analyzer():
    analyzer = MagicMock()
    analyzer.prompt_version = "section-relations-v1"
    analyzer.analyze = AsyncMock(
        return_value=RelationsResult(relations=[])
    )
    return analyzer


@pytest.fixture
def mock_questions_analyzer():
    analyzer = MagicMock()
    analyzer.prompt_version = "questions-answered-v1"
    analyzer.analyze = AsyncMock(
        return_value=QuestionsResult(document_questions=[], section_questions=[])
    )
    return analyzer


@pytest.fixture
def mock_conclusions_analyzer():
    analyzer = MagicMock()
    analyzer.PROMPT_VERSION = "conclusions-v1"
    analyzer.analyze = AsyncMock(
        return_value=ConclusionsResult(observations=[])
    )
    return analyzer


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_result = AsyncMock(return_value=None)
    storage.save_result = AsyncMock()
    storage.get_all_statuses = AsyncMock(return_value={
        "build_index": {"status": "not_started", "updated_at": None},
        "section_relations": {"status": "not_started", "updated_at": None},
        "questions_answered": {"status": "not_started", "updated_at": None},
        "conclusions": {"status": "not_started", "updated_at": None},
    })
    return storage


@pytest.fixture
def mock_ingestion_storage():
    storage = MagicMock()
    storage.get_ir = AsyncMock(return_value=_make_ir())
    return storage


@pytest.fixture
def service(
    mock_index_analyzer,
    mock_relations_analyzer,
    mock_questions_analyzer,
    mock_conclusions_analyzer,
    mock_storage,
    mock_ingestion_storage,
) -> OnDemandAnalysisService:
    return OnDemandAnalysisService(
        index_analyzer=mock_index_analyzer,
        relations_analyzer=mock_relations_analyzer,
        questions_analyzer=mock_questions_analyzer,
        conclusions_analyzer=mock_conclusions_analyzer,
        storage=mock_storage,
        ingestion_storage=mock_ingestion_storage,
    )


@pytest.fixture
def default_preferences() -> dict:
    return {
        "language": "es",
        "model_override": None,
        "auto_fallback": True,
        "document_language": None,
    }


# --- execute: Successful New Analysis ---


class TestExecuteSuccess:
    """Tests for successful new analysis execution."""

    async def test_executes_build_index_and_persists(
        self, service, mock_index_analyzer, mock_storage, mock_ingestion_storage, default_preferences
    ):
        """execute calls IndexAnalyzer and persists the result when no cached result exists."""
        result = await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.analysis_type == AnalysisType.BUILD_INDEX
        assert result.document_id == "doc-001"
        mock_index_analyzer.analyze.assert_called_once()
        mock_storage.save_result.assert_called_once()
        mock_ingestion_storage.get_ir.assert_called_once_with("doc-001")

    async def test_executes_section_relations(
        self, service, mock_relations_analyzer, mock_storage, default_preferences
    ):
        """execute routes to RelationsAnalyzer for section_relations type."""
        result = await service.execute("doc-001", AnalysisType.SECTION_RELATIONS, default_preferences)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.analysis_type == AnalysisType.SECTION_RELATIONS
        mock_relations_analyzer.analyze.assert_called_once()
        mock_storage.save_result.assert_called_once()

    async def test_executes_questions_answered(
        self, service, mock_questions_analyzer, mock_storage, default_preferences
    ):
        """execute routes to QuestionsAnalyzer for questions_answered type."""
        result = await service.execute("doc-001", AnalysisType.QUESTIONS_ANSWERED, default_preferences)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.analysis_type == AnalysisType.QUESTIONS_ANSWERED
        mock_questions_analyzer.analyze.assert_called_once()
        mock_storage.save_result.assert_called_once()

    async def test_executes_conclusions(
        self, service, mock_conclusions_analyzer, mock_storage, default_preferences
    ):
        """execute routes to ConclusionsAnalyzer for conclusions type."""
        result = await service.execute("doc-001", AnalysisType.CONCLUSIONS, default_preferences)

        assert result.status == AnalysisStatus.COMPLETED
        assert result.analysis_type == AnalysisType.CONCLUSIONS
        mock_conclusions_analyzer.analyze.assert_called_once()
        mock_storage.save_result.assert_called_once()

    async def test_passes_preferences_to_analyzer(
        self, service, mock_index_analyzer, default_preferences
    ):
        """execute passes language, model_override, and auto_fallback to the analyzer."""
        preferences = {
            "language": "en",
            "model_override": "custom-model",
            "auto_fallback": False,
            "document_language": None,
        }

        await service.execute("doc-001", AnalysisType.BUILD_INDEX, preferences)

        call_kwargs = mock_index_analyzer.analyze.call_args[1]
        assert call_kwargs["language"] == "en"
        assert call_kwargs["model_override"] == "custom-model"
        assert call_kwargs["auto_fallback"] is False

    async def test_section_relations_passes_index_result_if_available(
        self, service, mock_relations_analyzer, mock_storage, default_preferences
    ):
        """When build_index result exists, it is passed to RelationsAnalyzer."""
        completed_index = _make_completed_record(AnalysisType.BUILD_INDEX)

        # First call returns None (for the initial idempotency check on section_relations),
        # second call returns the build_index record (for _get_index_result)
        mock_storage.get_result = AsyncMock(
            side_effect=[None, completed_index]
        )

        await service.execute("doc-001", AnalysisType.SECTION_RELATIONS, default_preferences)

        call_kwargs = mock_relations_analyzer.analyze.call_args[1]
        assert call_kwargs["index_result"] is not None

    async def test_section_relations_passes_none_when_no_index(
        self, service, mock_relations_analyzer, mock_storage, default_preferences
    ):
        """When no build_index result exists, None is passed to RelationsAnalyzer."""
        # Both calls return None
        mock_storage.get_result = AsyncMock(return_value=None)

        await service.execute("doc-001", AnalysisType.SECTION_RELATIONS, default_preferences)

        call_kwargs = mock_relations_analyzer.analyze.call_args[1]
        assert call_kwargs["index_result"] is None


# --- execute: Idempotency ---


class TestExecuteIdempotency:
    """Tests that existing completed results are returned without LLM calls."""

    async def test_returns_cached_completed_result(
        self, service, mock_index_analyzer, mock_storage, mock_ingestion_storage, default_preferences
    ):
        """When a completed result exists, it is returned without calling the analyzer."""
        cached_record = _make_completed_record()
        mock_storage.get_result = AsyncMock(return_value=cached_record)

        result = await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)

        assert result is cached_record
        assert result.status == AnalysisStatus.COMPLETED
        mock_index_analyzer.analyze.assert_not_called()
        mock_ingestion_storage.get_ir.assert_not_called()
        mock_storage.save_result.assert_not_called()


# --- execute: Outdated Result ---


class TestExecuteOutdated:
    """Tests that outdated results trigger fresh execution."""

    async def test_outdated_result_triggers_fresh_analysis(
        self, service, mock_index_analyzer, mock_storage, mock_ingestion_storage, default_preferences
    ):
        """When an outdated result exists, the analyzer is called for a fresh execution."""
        outdated_record = _make_completed_record(status=AnalysisStatus.OUTDATED)
        mock_storage.get_result = AsyncMock(return_value=outdated_record)

        result = await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)

        assert result.status == AnalysisStatus.COMPLETED
        mock_index_analyzer.analyze.assert_called_once()
        mock_ingestion_storage.get_ir.assert_called_once_with("doc-001")
        mock_storage.save_result.assert_called_once()

    async def test_failed_result_triggers_fresh_analysis(
        self, service, mock_index_analyzer, mock_storage, mock_ingestion_storage, default_preferences
    ):
        """When a failed result exists, the analyzer is called for a fresh execution."""
        failed_record = _make_completed_record(status=AnalysisStatus.FAILED)
        mock_storage.get_result = AsyncMock(return_value=failed_record)

        result = await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)

        assert result.status == AnalysisStatus.COMPLETED
        mock_index_analyzer.analyze.assert_called_once()
        mock_storage.save_result.assert_called_once()


# --- execute: LLM Failure ---


class TestExecuteLLMFailure:
    """Tests that LLM failures propagate as exceptions."""

    async def test_analyzer_exception_propagates(
        self, service, mock_index_analyzer, mock_storage, default_preferences
    ):
        """When the analyzer raises, the exception propagates to the caller."""
        mock_index_analyzer.analyze = AsyncMock(
            side_effect=RuntimeError("LLM timeout")
        )

        with pytest.raises(RuntimeError, match="LLM timeout"):
            await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)

        # No result should be saved on failure
        mock_storage.save_result.assert_not_called()

    async def test_timeout_error_propagates(
        self, service, mock_index_analyzer, mock_storage, default_preferences
    ):
        """asyncio.TimeoutError from the analyzer propagates."""
        import asyncio

        mock_index_analyzer.analyze = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        with pytest.raises(asyncio.TimeoutError):
            await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)

        mock_storage.save_result.assert_not_called()

    async def test_value_error_from_analyzer_propagates(
        self, service, mock_conclusions_analyzer, mock_storage, default_preferences
    ):
        """ValueError from the analyzer (e.g., invalid response) propagates."""
        mock_conclusions_analyzer.analyze = AsyncMock(
            side_effect=ValueError("Invalid analysis response")
        )

        with pytest.raises(ValueError, match="Invalid analysis response"):
            await service.execute("doc-001", AnalysisType.CONCLUSIONS, default_preferences)

        mock_storage.save_result.assert_not_called()


# --- execute: IR Not Available ---


class TestExecuteIRNotAvailable:
    """Tests that missing IR raises the appropriate error."""

    async def test_raises_when_ir_is_none(
        self, service, mock_index_analyzer, mock_ingestion_storage, default_preferences
    ):
        """When ingestion_storage.get_ir returns None, DocumentIRNotAvailableError is raised."""
        mock_ingestion_storage.get_ir = AsyncMock(return_value=None)

        with pytest.raises(DocumentIRNotAvailableError):
            await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)

        mock_index_analyzer.analyze.assert_not_called()

    async def test_error_message_includes_document_id(
        self, service, mock_ingestion_storage, default_preferences
    ):
        """The error message includes the document_id for debugging."""
        mock_ingestion_storage.get_ir = AsyncMock(return_value=None)

        with pytest.raises(DocumentIRNotAvailableError, match="doc-001"):
            await service.execute("doc-001", AnalysisType.BUILD_INDEX, default_preferences)


# --- get_result ---


class TestGetResult:
    """Tests that get_result delegates to storage."""

    async def test_delegates_to_storage(self, service, mock_storage):
        """get_result passes through to storage.get_result."""
        expected = _make_completed_record()
        mock_storage.get_result = AsyncMock(return_value=expected)

        result = await service.get_result("doc-001", AnalysisType.BUILD_INDEX)

        assert result is expected
        mock_storage.get_result.assert_called_once_with("doc-001", AnalysisType.BUILD_INDEX)

    async def test_returns_none_when_no_result(self, service, mock_storage):
        """get_result returns None when storage has no record."""
        mock_storage.get_result = AsyncMock(return_value=None)

        result = await service.get_result("doc-001", AnalysisType.CONCLUSIONS)

        assert result is None
        mock_storage.get_result.assert_called_once_with("doc-001", AnalysisType.CONCLUSIONS)


# --- get_all_statuses ---


class TestGetAllStatuses:
    """Tests that get_all_statuses delegates to storage."""

    async def test_returns_status_map_from_storage(self, service, mock_storage):
        """get_all_statuses returns whatever storage provides."""
        expected = {
            "build_index": {"status": "completed", "updated_at": "2026-07-26T15:00:12+00:00"},
            "section_relations": {"status": "not_started", "updated_at": None},
            "questions_answered": {"status": "not_started", "updated_at": None},
            "conclusions": {"status": "outdated", "updated_at": "2026-07-26T14:00:00+00:00"},
        }
        mock_storage.get_all_statuses = AsyncMock(return_value=expected)

        result = await service.get_all_statuses("doc-001")

        assert result == expected
        mock_storage.get_all_statuses.assert_called_once_with("doc-001")
