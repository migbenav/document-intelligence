"""Unit tests for BaseAnalysisService.

Tests cover:
- analyze: successful (completed card with LLM result)
- analyze: LLM fails (partial card saved)
- analyze: idempotent (existing completed card returned without re-execution)
- analyze: does not raise on any failure
- retry_llm: success updates card to completed
- retry_llm: LLM fails again sets status="failed_llm"
- retry_llm: raises CardNotFoundError when no card exists

All tests mock LocalAnalyzer, LLMAnalyzer, and BaseAnalysisStorage.

Requirements validated: Req 1 (criteria 3, 4), Req 5 (criteria 1, 2, 3)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.base_analysis.llm_analyzer import LLMAnalysisResult
from app.analysis.base_analysis.local_analyzer import LocalAnalysisResult
from app.analysis.base_analysis.service import BaseAnalysisService, CardNotFoundError
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.document_card import (
    DocumentCard,
    DocumentCardStatistics,
    DocumentClassification,
    FileMetadata,
    OrganizationType,
)

pytestmark = pytest.mark.asyncio


# --- Helpers ---


def _make_ir(
    document_id: str = "doc-001",
    size_bytes: int = 5000,
    filename: str = "test_document.pdf",
) -> IntermediateRepresentation:
    """Create a minimal IntermediateRepresentation for testing."""
    return IntermediateRepresentation(
        document_id=document_id,
        metadata=DocumentMetadata(
            original_filename=filename,
            format=DocumentFormat.PDF,
            size_bytes=size_bytes,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-0",
                text="Artículo 1. Disposiciones generales.",
                structural_context={"section": "Disposiciones generales", "level": 1},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-1",
                text="Este reglamento establece las normas de convivencia.",
                structural_context={"section": "Disposiciones generales"},
                order=1,
            ),
        ],
    )


def _make_local_result() -> LocalAnalysisResult:
    """Create a typical LocalAnalysisResult."""
    return LocalAnalysisResult(
        title="Disposiciones generales",
        statistics=DocumentCardStatistics(
            total_chunks=2,
            sections_detected=1,
            hierarchy_levels=1,
            has_existing_index=False,
        ),
        organization_type=OrganizationType.NUMBERED_ARTICLES,
        file_metadata=FileMetadata(
            size_bytes=5000,
            format="pdf",
            language="es",
        ),
    )


def _make_llm_result() -> LLMAnalysisResult:
    """Create a typical LLMAnalysisResult."""
    return LLMAnalysisResult(
        summary="Este documento establece normas de convivencia para propiedades horizontales.",
        classification=DocumentClassification.NORMATIVE,
        model_id="groq/llama-3.3-70b-versatile",
        prompt_version="base-analysis-v1",
    )


def _make_completed_card(
    document_id: str = "doc-001", size_bytes: int = 5000
) -> DocumentCard:
    """Create a completed DocumentCard."""
    return DocumentCard(
        id="card-001",
        document_id=document_id,
        title="Disposiciones generales",
        summary="Este documento establece normas de convivencia.",
        classification=DocumentClassification.NORMATIVE,
        organization_type=OrganizationType.NUMBERED_ARTICLES,
        statistics=DocumentCardStatistics(
            total_chunks=2,
            sections_detected=1,
            hierarchy_levels=1,
            has_existing_index=False,
        ),
        file_metadata=FileMetadata(
            size_bytes=size_bytes,
            format="pdf",
            language="es",
        ),
        status="completed",
        outdated=False,
        model_id="groq/llama-3.3-70b-versatile",
        prompt_version="base-analysis-v1",
        created_at=datetime(2026, 7, 26, 10, 30, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 26, 10, 30, 4, tzinfo=timezone.utc),
    )


def _make_partial_card(document_id: str = "doc-001") -> DocumentCard:
    """Create a partial DocumentCard (LLM failed)."""
    return DocumentCard(
        id="card-002",
        document_id=document_id,
        title="Disposiciones generales",
        summary=None,
        classification=None,
        organization_type=OrganizationType.NUMBERED_ARTICLES,
        statistics=DocumentCardStatistics(
            total_chunks=2,
            sections_detected=1,
            hierarchy_levels=1,
            has_existing_index=False,
        ),
        file_metadata=FileMetadata(
            size_bytes=5000,
            format="pdf",
            language="es",
        ),
        status="partial",
        outdated=False,
        model_id=None,
        prompt_version=None,
        created_at=datetime(2026, 7, 26, 10, 30, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 26, 10, 30, 4, tzinfo=timezone.utc),
    )


# --- Fixtures ---


@pytest.fixture
def mock_local_analyzer():
    """Mock LocalAnalyzer with a working analyze method."""
    analyzer = MagicMock()
    analyzer.analyze.return_value = _make_local_result()
    return analyzer


@pytest.fixture
def mock_llm_analyzer():
    """Mock LLMAnalyzer with a working async analyze method."""
    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value=_make_llm_result())
    return analyzer


@pytest.fixture
def mock_storage():
    """Mock BaseAnalysisStorage with async methods."""
    storage = MagicMock()
    storage.get_card = AsyncMock(return_value=None)
    storage.upsert_card = AsyncMock(return_value=None)
    return storage


@pytest.fixture
def service(mock_local_analyzer, mock_llm_analyzer, mock_storage) -> BaseAnalysisService:
    """Create a BaseAnalysisService with mocked dependencies."""
    return BaseAnalysisService(
        local_analyzer=mock_local_analyzer,
        llm_analyzer=mock_llm_analyzer,
        storage=mock_storage,
    )


# --- Tests: analyze() — Successful (Completed Card) ---


class TestAnalyzeSuccess:
    async def test_returns_completed_card_when_llm_succeeds(
        self, service, mock_local_analyzer, mock_llm_analyzer, mock_storage
    ):
        """analyze() returns a card with status='completed' when LLM succeeds."""
        ir = _make_ir()

        card = await service.analyze("doc-001", ir)

        assert card.status == "completed"
        assert card.document_id == "doc-001"
        assert card.title == "Disposiciones generales"
        assert card.summary == "Este documento establece normas de convivencia para propiedades horizontales."
        assert card.classification == DocumentClassification.NORMATIVE
        assert card.organization_type == OrganizationType.NUMBERED_ARTICLES
        assert card.model_id == "groq/llama-3.3-70b-versatile"
        assert card.prompt_version == "base-analysis-v1"

    async def test_calls_local_then_llm_then_persists(
        self, service, mock_local_analyzer, mock_llm_analyzer, mock_storage
    ):
        """analyze() calls local → LLM → upsert in sequence."""
        ir = _make_ir()

        await service.analyze("doc-001", ir)

        # Local analyzer called with IR
        mock_local_analyzer.analyze.assert_called_once_with(ir)
        # LLM analyzer called with title, chunks, org_type, language
        mock_llm_analyzer.analyze.assert_called_once_with(
            title="Disposiciones generales",
            chunks=ir.chunks,
            organization_type=OrganizationType.NUMBERED_ARTICLES,
            language="es",
            model_override=None,
            auto_fallback=True,
        )
        # Storage upsert called
        mock_storage.upsert_card.assert_called_once()

    async def test_persisted_card_has_correct_fields(
        self, service, mock_storage
    ):
        """The card passed to upsert_card has all required fields populated."""
        ir = _make_ir()

        await service.analyze("doc-001", ir)

        persisted_card = mock_storage.upsert_card.call_args[0][0]
        assert persisted_card.document_id == "doc-001"
        assert persisted_card.title == "Disposiciones generales"
        assert persisted_card.summary is not None
        assert persisted_card.classification is not None
        assert persisted_card.statistics.total_chunks == 2
        assert persisted_card.file_metadata.size_bytes == 5000
        assert persisted_card.status == "completed"
        assert persisted_card.id is not None
        assert persisted_card.created_at is not None
        assert persisted_card.updated_at is not None


# --- Tests: analyze() — LLM Fails (Partial Card) ---


class TestAnalyzeLlmFails:
    async def test_returns_partial_card_when_llm_returns_none(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """analyze() returns a card with status='partial' when LLM returns None (Req 5.2, 5.3)."""
        mock_llm_analyzer.analyze = AsyncMock(return_value=None)
        ir = _make_ir()

        card = await service.analyze("doc-001", ir)

        assert card.status == "partial"
        assert card.summary is None
        assert card.classification is None
        assert card.model_id is None
        assert card.prompt_version is None

    async def test_partial_card_has_all_local_fields(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """Partial card still has title, statistics, org_type, file_metadata (Req 5.3)."""
        mock_llm_analyzer.analyze = AsyncMock(return_value=None)
        ir = _make_ir()

        card = await service.analyze("doc-001", ir)

        assert card.title == "Disposiciones generales"
        assert card.organization_type == OrganizationType.NUMBERED_ARTICLES
        assert card.statistics.total_chunks == 2
        assert card.statistics.sections_detected == 1
        assert card.statistics.hierarchy_levels == 1
        assert card.statistics.has_existing_index is False
        assert card.file_metadata.size_bytes == 5000
        assert card.file_metadata.format == "pdf"
        assert card.file_metadata.language == "es"

    async def test_partial_card_is_persisted(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """Partial card is still persisted via upsert_card."""
        mock_llm_analyzer.analyze = AsyncMock(return_value=None)
        ir = _make_ir()

        await service.analyze("doc-001", ir)

        mock_storage.upsert_card.assert_called_once()
        persisted = mock_storage.upsert_card.call_args[0][0]
        assert persisted.status == "partial"


# --- Tests: analyze() — Idempotent (Existing Completed Card) ---


class TestAnalyzeIdempotent:
    async def test_returns_existing_card_when_completed_and_size_matches(
        self, service, mock_local_analyzer, mock_llm_analyzer, mock_storage
    ):
        """analyze() returns existing completed card without re-execution (Req 1.3)."""
        existing_card = _make_completed_card(document_id="doc-001", size_bytes=5000)
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        card = await service.analyze("doc-001", ir)

        assert card is existing_card
        # Should NOT call local or LLM analyzers
        mock_local_analyzer.analyze.assert_not_called()
        mock_llm_analyzer.analyze.assert_not_called()
        # Should NOT persist
        mock_storage.upsert_card.assert_not_called()

    async def test_re_executes_when_size_differs(
        self, service, mock_local_analyzer, mock_llm_analyzer, mock_storage
    ):
        """analyze() re-executes when existing card size_bytes doesn't match IR."""
        existing_card = _make_completed_card(document_id="doc-001", size_bytes=3000)
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        card = await service.analyze("doc-001", ir)

        # Should re-execute full pipeline
        mock_local_analyzer.analyze.assert_called_once()
        mock_llm_analyzer.analyze.assert_called_once()
        mock_storage.upsert_card.assert_called_once()
        assert card.status == "completed"

    async def test_re_executes_when_existing_card_is_partial(
        self, service, mock_local_analyzer, mock_llm_analyzer, mock_storage
    ):
        """analyze() re-executes when existing card has status='partial'."""
        partial_card = _make_partial_card(document_id="doc-001")
        mock_storage.get_card = AsyncMock(return_value=partial_card)
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        card = await service.analyze("doc-001", ir)

        mock_local_analyzer.analyze.assert_called_once()
        mock_llm_analyzer.analyze.assert_called_once()
        mock_storage.upsert_card.assert_called_once()


# --- Tests: analyze() — Does Not Raise on Any Failure ---


class TestAnalyzeNeverRaises:
    async def test_does_not_raise_when_local_analyzer_fails(
        self, service, mock_local_analyzer, mock_storage
    ):
        """analyze() catches exceptions from LocalAnalyzer and returns a fallback card (Req 1.4)."""
        mock_local_analyzer.analyze.side_effect = RuntimeError("Unexpected local error")
        ir = _make_ir()

        # Should NOT raise
        card = await service.analyze("doc-001", ir)

        assert card is not None
        assert card.status == "partial"
        assert card.document_id == "doc-001"

    async def test_does_not_raise_when_storage_get_fails(
        self, service, mock_storage
    ):
        """analyze() catches exceptions from storage.get_card and returns a card (Req 1.4)."""
        mock_storage.get_card = AsyncMock(side_effect=RuntimeError("DB connection error"))
        ir = _make_ir()

        card = await service.analyze("doc-001", ir)

        assert card is not None
        assert card.document_id == "doc-001"

    async def test_does_not_raise_when_storage_upsert_fails(
        self, service, mock_local_analyzer, mock_llm_analyzer, mock_storage
    ):
        """analyze() catches exceptions from storage.upsert_card (Req 1.4)."""
        mock_storage.upsert_card = AsyncMock(side_effect=RuntimeError("DB write error"))
        ir = _make_ir()

        card = await service.analyze("doc-001", ir)

        # Falls into the exception handler which builds a fallback card
        assert card is not None
        assert card.document_id == "doc-001"

    async def test_does_not_raise_when_llm_raises_unexpected(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """analyze() catches unexpected exceptions from LLMAnalyzer (Req 1.4)."""
        mock_llm_analyzer.analyze = AsyncMock(
            side_effect=RuntimeError("Unexpected LLM crash")
        )
        ir = _make_ir()

        card = await service.analyze("doc-001", ir)

        # Falls into the exception handler
        assert card is not None
        assert card.document_id == "doc-001"


# --- Tests: retry_llm() — Success ---


class TestRetryLlmSuccess:
    async def test_updates_card_to_completed_on_llm_success(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """retry_llm() updates status to 'completed' when LLM succeeds."""
        existing_card = _make_partial_card(document_id="doc-001")
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir()

        card = await service.retry_llm("doc-001", ir)

        assert card.status == "completed"
        assert card.summary == "Este documento establece normas de convivencia para propiedades horizontales."
        assert card.classification == DocumentClassification.NORMATIVE
        assert card.model_id == "groq/llama-3.3-70b-versatile"
        assert card.prompt_version == "base-analysis-v1"

    async def test_preserves_local_fields_on_retry_success(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """retry_llm() keeps title, statistics, org_type, file_metadata from existing card."""
        existing_card = _make_partial_card(document_id="doc-001")
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir()

        card = await service.retry_llm("doc-001", ir)

        assert card.title == existing_card.title
        assert card.organization_type == existing_card.organization_type
        assert card.statistics == existing_card.statistics
        assert card.file_metadata == existing_card.file_metadata
        assert card.id == existing_card.id

    async def test_persists_updated_card(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """retry_llm() calls upsert_card with the updated card."""
        existing_card = _make_partial_card(document_id="doc-001")
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir()

        await service.retry_llm("doc-001", ir)

        mock_storage.upsert_card.assert_called_once()
        persisted = mock_storage.upsert_card.call_args[0][0]
        assert persisted.status == "completed"
        assert persisted.summary is not None


# --- Tests: retry_llm() — LLM Fails Again ---


class TestRetryLlmFails:
    async def test_sets_status_failed_llm_when_llm_returns_none(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """retry_llm() sets status='failed_llm' when LLM returns None again."""
        existing_card = _make_partial_card(document_id="doc-001")
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        mock_llm_analyzer.analyze = AsyncMock(return_value=None)
        ir = _make_ir()

        card = await service.retry_llm("doc-001", ir)

        assert card.status == "failed_llm"
        assert card.summary is None
        assert card.classification is None

    async def test_persists_failed_llm_card(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """retry_llm() persists card with status='failed_llm'."""
        existing_card = _make_partial_card(document_id="doc-001")
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        mock_llm_analyzer.analyze = AsyncMock(return_value=None)
        ir = _make_ir()

        await service.retry_llm("doc-001", ir)

        mock_storage.upsert_card.assert_called_once()
        persisted = mock_storage.upsert_card.call_args[0][0]
        assert persisted.status == "failed_llm"

    async def test_updates_timestamp_on_failed_retry(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """retry_llm() updates updated_at even when LLM fails."""
        existing_card = _make_partial_card(document_id="doc-001")
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        mock_llm_analyzer.analyze = AsyncMock(return_value=None)
        ir = _make_ir()

        card = await service.retry_llm("doc-001", ir)

        assert card.updated_at != existing_card.updated_at


# --- Tests: retry_llm() — CardNotFoundError ---


class TestRetryLlmCardNotFound:
    async def test_raises_card_not_found_when_no_card_exists(
        self, service, mock_storage
    ):
        """retry_llm() raises CardNotFoundError when storage returns None."""
        mock_storage.get_card = AsyncMock(return_value=None)
        ir = _make_ir()

        with pytest.raises(CardNotFoundError):
            await service.retry_llm("doc-001", ir)

    async def test_does_not_call_llm_when_no_card(
        self, service, mock_llm_analyzer, mock_storage
    ):
        """retry_llm() does not call LLM analyzer when no card exists."""
        mock_storage.get_card = AsyncMock(return_value=None)
        ir = _make_ir()

        with pytest.raises(CardNotFoundError):
            await service.retry_llm("doc-001", ir)

        mock_llm_analyzer.analyze.assert_not_called()

    async def test_does_not_persist_when_no_card(
        self, service, mock_storage
    ):
        """retry_llm() does not call upsert_card when no card exists."""
        mock_storage.get_card = AsyncMock(return_value=None)
        ir = _make_ir()

        with pytest.raises(CardNotFoundError):
            await service.retry_llm("doc-001", ir)

        mock_storage.upsert_card.assert_not_called()


# --- Tests: analyze() — Outdated Propagation on Re-upload ---


class TestAnalyzeOutdatedPropagation:
    """Tests for on-demand analysis outdated propagation when size mismatch is detected.

    Requirements validated: On-Demand Req 6 (criterion 6)
    """

    @pytest.fixture
    def mock_on_demand_storage(self):
        """Mock OnDemandAnalysisStorage with async mark_all_outdated."""
        storage = MagicMock()
        storage.mark_all_outdated = AsyncMock(return_value=None)
        return storage

    @pytest.fixture
    def service_with_on_demand(
        self, mock_local_analyzer, mock_llm_analyzer, mock_storage, mock_on_demand_storage
    ):
        """Create a BaseAnalysisService with on_demand_storage wired."""
        return BaseAnalysisService(
            local_analyzer=mock_local_analyzer,
            llm_analyzer=mock_llm_analyzer,
            storage=mock_storage,
            on_demand_storage=mock_on_demand_storage,
        )

    async def test_marks_on_demand_outdated_when_size_differs(
        self,
        service_with_on_demand,
        mock_storage,
        mock_on_demand_storage,
    ):
        """analyze() calls mark_all_outdated when existing card size doesn't match IR."""
        existing_card = _make_completed_card(document_id="doc-001", size_bytes=3000)
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        await service_with_on_demand.analyze("doc-001", ir)

        mock_on_demand_storage.mark_all_outdated.assert_called_once_with("doc-001")

    async def test_does_not_mark_outdated_when_size_matches(
        self,
        service_with_on_demand,
        mock_storage,
        mock_on_demand_storage,
    ):
        """analyze() does NOT call mark_all_outdated when size matches (idempotent)."""
        existing_card = _make_completed_card(document_id="doc-001", size_bytes=5000)
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        await service_with_on_demand.analyze("doc-001", ir)

        mock_on_demand_storage.mark_all_outdated.assert_not_called()

    async def test_does_not_mark_outdated_when_no_existing_card(
        self,
        service_with_on_demand,
        mock_storage,
        mock_on_demand_storage,
    ):
        """analyze() does NOT call mark_all_outdated when there is no existing card."""
        mock_storage.get_card = AsyncMock(return_value=None)
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        await service_with_on_demand.analyze("doc-001", ir)

        mock_on_demand_storage.mark_all_outdated.assert_not_called()

    async def test_continues_analysis_when_mark_outdated_fails(
        self,
        service_with_on_demand,
        mock_storage,
        mock_on_demand_storage,
        mock_local_analyzer,
        mock_llm_analyzer,
    ):
        """analyze() continues normally even if mark_all_outdated raises an exception."""
        existing_card = _make_completed_card(document_id="doc-001", size_bytes=3000)
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        mock_on_demand_storage.mark_all_outdated = AsyncMock(
            side_effect=RuntimeError("DB connection failed")
        )
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        card = await service_with_on_demand.analyze("doc-001", ir)

        # Analysis should still complete successfully
        assert card.status == "completed"
        mock_local_analyzer.analyze.assert_called_once()
        mock_llm_analyzer.analyze.assert_called_once()

    async def test_does_not_call_mark_outdated_when_on_demand_storage_is_none(
        self,
        mock_local_analyzer,
        mock_llm_analyzer,
        mock_storage,
    ):
        """analyze() skips mark_all_outdated when on_demand_storage is None."""
        service_without_od = BaseAnalysisService(
            local_analyzer=mock_local_analyzer,
            llm_analyzer=mock_llm_analyzer,
            storage=mock_storage,
            on_demand_storage=None,
        )
        existing_card = _make_completed_card(document_id="doc-001", size_bytes=3000)
        mock_storage.get_card = AsyncMock(return_value=existing_card)
        ir = _make_ir(document_id="doc-001", size_bytes=5000)

        # Should not raise, should proceed normally
        card = await service_without_od.analyze("doc-001", ir)

        assert card.status == "completed"


# --- Tests: Language Confirmation Update (Req 7 criteria 3, 4) ---


class TestLanguageConfirmation:
    """Tests for LLM language confirmation updating file_metadata.language."""

    async def test_language_updated_when_llm_confirms_different_language(self):
        """When LLM returns a different language, file_metadata.language is updated."""
        local_result = _make_local_result()
        assert local_result.file_metadata.language == "es"

        # LLM says the document is actually Portuguese
        llm_result = LLMAnalysisResult(
            summary="Um documento sobre regulamentos.",
            classification=DocumentClassification.NORMATIVE,
            model_id="groq/llama-3.3-70b-versatile",
            prompt_version="base-analysis-v2",
            confirmed_language="pt",
        )

        local_analyzer = MagicMock()
        local_analyzer.analyze = MagicMock(return_value=local_result)

        llm_analyzer = MagicMock()
        llm_analyzer.analyze = AsyncMock(return_value=llm_result)

        storage = MagicMock()
        storage.get_card = AsyncMock(return_value=None)
        storage.upsert_card = AsyncMock()

        service = BaseAnalysisService(
            local_analyzer=local_analyzer,
            llm_analyzer=llm_analyzer,
            storage=storage,
        )

        ir = _make_ir()
        card = await service.analyze("doc-001", ir)

        assert card.status == "completed"
        assert card.file_metadata.language == "pt"

    async def test_language_unchanged_when_llm_confirms_same_language(self):
        """When LLM confirms same language as detected, file_metadata.language stays the same."""
        local_result = _make_local_result()
        assert local_result.file_metadata.language == "es"

        llm_result = LLMAnalysisResult(
            summary="Un documento normativo.",
            classification=DocumentClassification.NORMATIVE,
            model_id="groq/llama-3.3-70b-versatile",
            prompt_version="base-analysis-v2",
            confirmed_language="es",
        )

        local_analyzer = MagicMock()
        local_analyzer.analyze = MagicMock(return_value=local_result)

        llm_analyzer = MagicMock()
        llm_analyzer.analyze = AsyncMock(return_value=llm_result)

        storage = MagicMock()
        storage.get_card = AsyncMock(return_value=None)
        storage.upsert_card = AsyncMock()

        service = BaseAnalysisService(
            local_analyzer=local_analyzer,
            llm_analyzer=llm_analyzer,
            storage=storage,
        )

        ir = _make_ir()
        card = await service.analyze("doc-001", ir)

        assert card.status == "completed"
        assert card.file_metadata.language == "es"

    async def test_language_unchanged_when_llm_returns_no_language(self):
        """When LLM returns no language confirmation, file_metadata.language stays as detected."""
        local_result = _make_local_result()

        llm_result = LLMAnalysisResult(
            summary="Un documento normativo.",
            classification=DocumentClassification.NORMATIVE,
            model_id="groq/llama-3.3-70b-versatile",
            prompt_version="base-analysis-v2",
            confirmed_language=None,
        )

        local_analyzer = MagicMock()
        local_analyzer.analyze = MagicMock(return_value=local_result)

        llm_analyzer = MagicMock()
        llm_analyzer.analyze = AsyncMock(return_value=llm_result)

        storage = MagicMock()
        storage.get_card = AsyncMock(return_value=None)
        storage.upsert_card = AsyncMock()

        service = BaseAnalysisService(
            local_analyzer=local_analyzer,
            llm_analyzer=llm_analyzer,
            storage=storage,
        )

        ir = _make_ir()
        card = await service.analyze("doc-001", ir)

        assert card.status == "completed"
        assert card.file_metadata.language == "es"
