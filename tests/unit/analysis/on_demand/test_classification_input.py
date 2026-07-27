"""Unit tests for classification propagation from card_storage to analyzers.

Verifies that:
1. The service loads the card and passes classification to the analyzer.
2. When no card exists, "generic" is used as classification.
3. The document_language from the card is passed correctly to the analyzer.

Requirements: Req 8 (criteria 1-5)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.on_demand.analyzer_response import AnalyzerResponse
from app.analysis.on_demand.models import (
    AnalysisStatus,
    AnalysisType,
    IndexResult,
    ConclusionsResult,
)
from app.analysis.on_demand.service import OnDemandAnalysisService
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


def _make_ir() -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    return IntermediateRepresentation(
        document_id="doc-class-001",
        metadata=DocumentMetadata(
            original_filename="reglamento.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=2048,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="c1",
                text="Artículo 1. Objeto del reglamento.",
                structural_context={"section": "Artículo 1"},
                order=0,
            ),
        ],
    )


def _make_card(
    classification: DocumentClassification = DocumentClassification.NORMATIVE,
    language: str | None = "es",
) -> DocumentCard:
    """Create a DocumentCard with configurable classification and language."""
    return DocumentCard(
        id="card-001",
        document_id="doc-class-001",
        title="Reglamento de Convivencia",
        summary="Un reglamento normativo.",
        classification=classification,
        organization_type=OrganizationType.NUMBERED_ARTICLES,
        statistics=DocumentCardStatistics(
            total_chunks=10,
            sections_detected=5,
            hierarchy_levels=2,
            has_existing_index=False,
        ),
        file_metadata=FileMetadata(
            size_bytes=2048,
            format="markdown",
            language=language,
            last_modified=None,
        ),
        status="completed",
        outdated=False,
        model_id="gemini/gemini-2.5-flash",
        prompt_version="base-analysis-v1",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _build_service(
    card_storage_mock,
    index_analyzer_mock=None,
    conclusions_analyzer_mock=None,
) -> OnDemandAnalysisService:
    """Build an OnDemandAnalysisService with mocked dependencies."""
    if index_analyzer_mock is None:
        index_analyzer_mock = MagicMock()
        index_analyzer_mock.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=IndexResult(tree=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="build-index-v1",
                fallback_used=False,
            )
        )

    if conclusions_analyzer_mock is None:
        conclusions_analyzer_mock = MagicMock()
        conclusions_analyzer_mock.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=ConclusionsResult(observations=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="conclusions-v1",
                fallback_used=False,
            )
        )

    mock_storage = MagicMock()
    mock_storage.get_result = AsyncMock(return_value=None)
    mock_storage.save_result = AsyncMock()

    mock_ingestion_storage = MagicMock()
    mock_ingestion_storage.get_ir = AsyncMock(return_value=_make_ir())

    return OnDemandAnalysisService(
        index_analyzer=index_analyzer_mock,
        relations_analyzer=MagicMock(),
        questions_analyzer=MagicMock(),
        conclusions_analyzer=conclusions_analyzer_mock,
        storage=mock_storage,
        ingestion_storage=mock_ingestion_storage,
        card_storage=card_storage_mock,
    )


# --- Test: Service loads card and passes classification to analyzer ---


class TestClassificationPropagation:
    """Verify that classification from the card is passed to analyzers."""

    async def test_normative_classification_passed_to_index_analyzer(self):
        """Service loads card with 'normative' classification and passes it to IndexAnalyzer."""
        card = _make_card(classification=DocumentClassification.NORMATIVE)
        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=card)

        index_analyzer = MagicMock()
        index_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=IndexResult(tree=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="build-index-v1",
                fallback_used=False,
            )
        )

        service = _build_service(card_storage, index_analyzer_mock=index_analyzer)

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,
        }

        await service.execute("doc-class-001", AnalysisType.BUILD_INDEX, preferences)

        call_kwargs = index_analyzer.analyze.call_args[1]
        assert call_kwargs["classification"] == "normative"

    async def test_procedure_classification_passed_to_analyzer(self):
        """Service passes 'procedure' classification from the card."""
        card = _make_card(classification=DocumentClassification.PROCEDURE)
        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=card)

        index_analyzer = MagicMock()
        index_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=IndexResult(tree=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="build-index-v1",
                fallback_used=False,
            )
        )

        service = _build_service(card_storage, index_analyzer_mock=index_analyzer)

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,
        }

        await service.execute("doc-class-001", AnalysisType.BUILD_INDEX, preferences)

        call_kwargs = index_analyzer.analyze.call_args[1]
        assert call_kwargs["classification"] == "procedure"

    async def test_narrative_classification_passed_to_analyzer(self):
        """Service passes 'narrative' classification from the card."""
        card = _make_card(classification=DocumentClassification.NARRATIVE)
        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=card)

        index_analyzer = MagicMock()
        index_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=IndexResult(tree=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="build-index-v1",
                fallback_used=False,
            )
        )

        service = _build_service(card_storage, index_analyzer_mock=index_analyzer)

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,
        }

        await service.execute("doc-class-001", AnalysisType.BUILD_INDEX, preferences)

        call_kwargs = index_analyzer.analyze.call_args[1]
        assert call_kwargs["classification"] == "narrative"


# --- Test: Missing card results in "generic" classification ---


class TestMissingCardDefaultsToGeneric:
    """Verify that when no card exists, 'generic' is used as classification."""

    async def test_no_card_uses_generic_classification(self):
        """When card_storage.get_card returns None, classification defaults to 'generic'."""
        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=None)

        index_analyzer = MagicMock()
        index_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=IndexResult(tree=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="build-index-v1",
                fallback_used=False,
            )
        )

        service = _build_service(card_storage, index_analyzer_mock=index_analyzer)

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,
        }

        await service.execute("doc-class-001", AnalysisType.BUILD_INDEX, preferences)

        call_kwargs = index_analyzer.analyze.call_args[1]
        assert call_kwargs["classification"] == "generic"

    async def test_card_with_null_classification_uses_generic(self):
        """When card.classification is None, classification defaults to 'generic'."""
        card = _make_card(classification=DocumentClassification.NORMATIVE)
        # Override classification to None to simulate a partial card
        card.classification = None

        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=card)

        index_analyzer = MagicMock()
        index_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=IndexResult(tree=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="build-index-v1",
                fallback_used=False,
            )
        )

        service = _build_service(card_storage, index_analyzer_mock=index_analyzer)

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,
        }

        await service.execute("doc-class-001", AnalysisType.BUILD_INDEX, preferences)

        call_kwargs = index_analyzer.analyze.call_args[1]
        assert call_kwargs["classification"] == "generic"

    async def test_no_card_storage_uses_generic_classification(self):
        """When card_storage is None (not provided), classification defaults to 'generic'."""
        index_analyzer = MagicMock()
        index_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=IndexResult(tree=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="build-index-v1",
                fallback_used=False,
            )
        )

        mock_storage = MagicMock()
        mock_storage.get_result = AsyncMock(return_value=None)
        mock_storage.save_result = AsyncMock()

        mock_ingestion_storage = MagicMock()
        mock_ingestion_storage.get_ir = AsyncMock(return_value=_make_ir())

        service = OnDemandAnalysisService(
            index_analyzer=index_analyzer,
            relations_analyzer=MagicMock(),
            questions_analyzer=MagicMock(),
            conclusions_analyzer=MagicMock(),
            storage=mock_storage,
            ingestion_storage=mock_ingestion_storage,
            card_storage=None,
        )

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,
        }

        await service.execute("doc-class-001", AnalysisType.BUILD_INDEX, preferences)

        call_kwargs = index_analyzer.analyze.call_args[1]
        assert call_kwargs["classification"] == "generic"


# --- Test: document_language from card is passed correctly ---


class TestDocumentLanguagePropagation:
    """Verify that document_language from the card is used when not in preferences."""

    async def test_card_language_used_for_conclusions_when_not_in_preferences(self):
        """document_language from card.file_metadata.language is used for conclusions."""
        card = _make_card(classification=DocumentClassification.NORMATIVE, language="pt")
        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=card)

        conclusions_analyzer = MagicMock()
        conclusions_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=ConclusionsResult(observations=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="conclusions-v1",
                fallback_used=False,
            )
        )

        service = _build_service(
            card_storage, conclusions_analyzer_mock=conclusions_analyzer
        )

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,  # Not provided in preferences
        }

        await service.execute("doc-class-001", AnalysisType.CONCLUSIONS, preferences)

        call_kwargs = conclusions_analyzer.analyze.call_args[1]
        assert call_kwargs["document_language"] == "pt"

    async def test_preference_language_overrides_card_language(self):
        """When document_language is provided in preferences, it takes priority over card."""
        card = _make_card(classification=DocumentClassification.NORMATIVE, language="pt")
        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=card)

        conclusions_analyzer = MagicMock()
        conclusions_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=ConclusionsResult(observations=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="conclusions-v1",
                fallback_used=False,
            )
        )

        service = _build_service(
            card_storage, conclusions_analyzer_mock=conclusions_analyzer
        )

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": "en",  # Explicitly provided
        }

        await service.execute("doc-class-001", AnalysisType.CONCLUSIONS, preferences)

        call_kwargs = conclusions_analyzer.analyze.call_args[1]
        assert call_kwargs["document_language"] == "en"

    async def test_no_card_language_falls_back_to_ui_language(self):
        """When card has no language and preferences has no document_language, UI language is used."""
        card = _make_card(classification=DocumentClassification.NORMATIVE, language=None)
        card_storage = MagicMock()
        card_storage.get_card = AsyncMock(return_value=card)

        conclusions_analyzer = MagicMock()
        conclusions_analyzer.analyze = AsyncMock(
            return_value=AnalyzerResponse(
                result=ConclusionsResult(observations=[]),
                model_id="gemini/gemini-2.5-flash",
                prompt_version="conclusions-v1",
                fallback_used=False,
            )
        )

        service = _build_service(
            card_storage, conclusions_analyzer_mock=conclusions_analyzer
        )

        preferences = {
            "language": "es",
            "model_override": None,
            "auto_fallback": True,
            "document_language": None,
        }

        await service.execute("doc-class-001", AnalysisType.CONCLUSIONS, preferences)

        call_kwargs = conclusions_analyzer.analyze.call_args[1]
        # Falls back to UI language "es" when neither preference nor card has it
        assert call_kwargs["document_language"] == "es"
