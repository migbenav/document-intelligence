"""Unit tests for model_id propagation through the analysis pipeline.

Verifies that:
1. Analyzers return actual model_id from LLMResponse (not the requested model).
2. The service uses the actual model_id in AnalysisRecord (not model_override).
3. fallback_used is True when response.model_id differs from the requested model.

Requirements: Req 5 (criteria 1, 3)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.on_demand.analyzer_response import AnalyzerResponse
from app.analysis.on_demand.index_analyzer import IndexAnalyzer
from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
    IndexResult,
    QuestionsResult,
)
from app.analysis.on_demand.questions_analyzer import QuestionsAnalyzer
from app.analysis.on_demand.service import OnDemandAnalysisService
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)

pytestmark = pytest.mark.asyncio


# --- Helpers ---


def _make_ir() -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    return IntermediateRepresentation(
        document_id="doc-prop-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="c1",
                text="Test content for analysis.",
                structural_context={"section": "Introduction"},
                order=0,
            ),
        ],
    )


# --- Test: Analyzer returns actual model_id from LLMResponse ---


class TestAnalyzerReturnsActualModelId:
    """Verify analyzers propagate the actual model_id from LLMResponse."""

    async def test_index_analyzer_returns_actual_model_from_response(self):
        """IndexAnalyzer returns the model_id that LLMResponse reports, not the requested one."""
        # The LLM responded with a different model (e.g., fallback happened at LiteLLM level)
        mock_llm_response = LLMResponse(
            content='{"tree": []}',
            model_id="groq/llama-3.3-70b-versatile",
        )

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(return_value=mock_llm_response)
        mock_llm_client.primary_model = "gemini/gemini-2.5-flash"

        analyzer = IndexAnalyzer(llm_client=mock_llm_client)

        ir = _make_ir()
        response = await analyzer.analyze(
            ir=ir,
            language="es",
            model_override="gemini/gemini-2.5-flash",
            auto_fallback=True,
        )

        assert response.model_id == "groq/llama-3.3-70b-versatile"
        assert response.model_id != "gemini/gemini-2.5-flash"

    async def test_index_analyzer_returns_requested_model_when_no_fallback(self):
        """IndexAnalyzer returns the requested model when no fallback occurred."""
        mock_llm_response = LLMResponse(
            content='{"tree": []}',
            model_id="gemini/gemini-2.5-flash",
        )

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(return_value=mock_llm_response)
        mock_llm_client.primary_model = "gemini/gemini-2.5-flash"

        analyzer = IndexAnalyzer(llm_client=mock_llm_client)

        ir = _make_ir()
        response = await analyzer.analyze(
            ir=ir,
            language="es",
            model_override="gemini/gemini-2.5-flash",
            auto_fallback=True,
        )

        assert response.model_id == "gemini/gemini-2.5-flash"


# --- Test: Service uses actual model_id in AnalysisRecord ---


class TestServiceUsesActualModelId:
    """Verify the service stores actual model_id from AnalyzerResponse, not the model_override."""

    async def test_service_record_uses_response_model_id_not_override(self):
        """AnalysisRecord.model_id is set from the AnalyzerResponse, not from preferences.model_override."""
        # Analyzer returns a response where the actual model differs from requested
        mock_analyzer_response = AnalyzerResponse(
            result=IndexResult(tree=[]),
            model_id="groq/llama-3.3-70b-versatile",
            prompt_version="build-index-v1",
            fallback_used=True,
        )

        mock_index_analyzer = MagicMock()
        mock_index_analyzer.analyze = AsyncMock(return_value=mock_analyzer_response)

        mock_relations_analyzer = MagicMock()
        mock_questions_analyzer = MagicMock()
        mock_conclusions_analyzer = MagicMock()

        mock_storage = MagicMock()
        mock_storage.get_result = AsyncMock(return_value=None)
        mock_storage.save_result = AsyncMock()

        mock_ingestion_storage = MagicMock()
        mock_ingestion_storage.get_ir = AsyncMock(return_value=_make_ir())

        service = OnDemandAnalysisService(
            index_analyzer=mock_index_analyzer,
            relations_analyzer=mock_relations_analyzer,
            questions_analyzer=mock_questions_analyzer,
            conclusions_analyzer=mock_conclusions_analyzer,
            storage=mock_storage,
            ingestion_storage=mock_ingestion_storage,
            card_storage=MagicMock(get_card=AsyncMock(return_value=None)),
        )

        preferences = {
            "language": "es",
            "model_override": "gemini/gemini-2.5-flash",
            "auto_fallback": True,
            "document_language": None,
        }

        record = await service.execute("doc-prop-001", AnalysisType.BUILD_INDEX, preferences)

        # model_id on record should be the ACTUAL model from response, not the override
        assert record.model_id == "groq/llama-3.3-70b-versatile"
        assert record.model_id != "gemini/gemini-2.5-flash"

    async def test_service_record_stores_requested_model_from_override(self):
        """AnalysisRecord.requested_model is set from preferences.model_override."""
        mock_analyzer_response = AnalyzerResponse(
            result=IndexResult(tree=[]),
            model_id="groq/llama-3.3-70b-versatile",
            prompt_version="build-index-v1",
            fallback_used=True,
        )

        mock_index_analyzer = MagicMock()
        mock_index_analyzer.analyze = AsyncMock(return_value=mock_analyzer_response)

        mock_storage = MagicMock()
        mock_storage.get_result = AsyncMock(return_value=None)
        mock_storage.save_result = AsyncMock()

        mock_ingestion_storage = MagicMock()
        mock_ingestion_storage.get_ir = AsyncMock(return_value=_make_ir())

        service = OnDemandAnalysisService(
            index_analyzer=mock_index_analyzer,
            relations_analyzer=MagicMock(),
            questions_analyzer=MagicMock(),
            conclusions_analyzer=MagicMock(),
            storage=mock_storage,
            ingestion_storage=mock_ingestion_storage,
            card_storage=MagicMock(get_card=AsyncMock(return_value=None)),
        )

        preferences = {
            "language": "es",
            "model_override": "gemini/gemini-2.5-flash",
            "auto_fallback": True,
            "document_language": None,
        }

        record = await service.execute("doc-prop-001", AnalysisType.BUILD_INDEX, preferences)

        # requested_model stores what the user originally asked for
        assert record.requested_model == "gemini/gemini-2.5-flash"

    async def test_service_record_requested_model_is_none_when_default(self):
        """AnalysisRecord.requested_model is None when model_override is 'default' or None."""
        mock_analyzer_response = AnalyzerResponse(
            result=IndexResult(tree=[]),
            model_id="gemini/gemini-2.5-flash",
            prompt_version="build-index-v1",
            fallback_used=False,
        )

        mock_index_analyzer = MagicMock()
        mock_index_analyzer.analyze = AsyncMock(return_value=mock_analyzer_response)

        mock_storage = MagicMock()
        mock_storage.get_result = AsyncMock(return_value=None)
        mock_storage.save_result = AsyncMock()

        mock_ingestion_storage = MagicMock()
        mock_ingestion_storage.get_ir = AsyncMock(return_value=_make_ir())

        service = OnDemandAnalysisService(
            index_analyzer=mock_index_analyzer,
            relations_analyzer=MagicMock(),
            questions_analyzer=MagicMock(),
            conclusions_analyzer=MagicMock(),
            storage=mock_storage,
            ingestion_storage=mock_ingestion_storage,
            card_storage=MagicMock(get_card=AsyncMock(return_value=None)),
        )

        # Test with model_override = "default"
        preferences = {
            "language": "es",
            "model_override": "default",
            "auto_fallback": True,
            "document_language": None,
        }

        record = await service.execute("doc-prop-001", AnalysisType.BUILD_INDEX, preferences)
        assert record.requested_model is None

        # Reset mocks for second call
        mock_storage.get_result = AsyncMock(return_value=None)

        # Test with model_override = None
        preferences["model_override"] = None
        record = await service.execute("doc-prop-001", AnalysisType.BUILD_INDEX, preferences)
        assert record.requested_model is None


# --- Test: fallback_used is True when model_id differs from requested ---


class TestFallbackUsedDetection:
    """Verify fallback_used is correctly determined based on model_id comparison."""

    async def test_fallback_used_true_when_actual_differs_from_requested(self):
        """fallback_used is True when response.model_id != requested model."""
        mock_llm_response = LLMResponse(
            content='{"tree": []}',
            model_id="groq/llama-3.3-70b-versatile",
        )

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(return_value=mock_llm_response)
        mock_llm_client.primary_model = "gemini/gemini-2.5-flash"

        analyzer = IndexAnalyzer(llm_client=mock_llm_client)

        ir = _make_ir()
        response = await analyzer.analyze(
            ir=ir,
            language="es",
            model_override="gemini/gemini-2.5-flash",
            auto_fallback=True,
        )

        assert response.fallback_used is True

    async def test_fallback_used_false_when_actual_matches_requested(self):
        """fallback_used is False when response.model_id == requested model."""
        mock_llm_response = LLMResponse(
            content='{"tree": []}',
            model_id="gemini/gemini-2.5-flash",
        )

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(return_value=mock_llm_response)
        mock_llm_client.primary_model = "gemini/gemini-2.5-flash"

        analyzer = IndexAnalyzer(llm_client=mock_llm_client)

        ir = _make_ir()
        response = await analyzer.analyze(
            ir=ir,
            language="es",
            model_override="gemini/gemini-2.5-flash",
            auto_fallback=True,
        )

        assert response.fallback_used is False

    async def test_fallback_used_when_no_override_uses_primary_model(self):
        """When no model_override, fallback_used compares against the primary model."""
        mock_llm_response = LLMResponse(
            content='{"tree": []}',
            model_id="groq/llama-3.3-70b-versatile",
        )

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(return_value=mock_llm_response)
        mock_llm_client.primary_model = "gemini/gemini-2.5-flash"

        analyzer = IndexAnalyzer(llm_client=mock_llm_client)

        ir = _make_ir()
        # No model_override — should compare against primary_model
        response = await analyzer.analyze(
            ir=ir,
            language="es",
            model_override=None,
            auto_fallback=True,
        )

        # Response model differs from primary → fallback was used
        assert response.fallback_used is True

    async def test_service_propagates_fallback_used_to_record(self):
        """Service propagates fallback_used from AnalyzerResponse to AnalysisRecord."""
        mock_analyzer_response = AnalyzerResponse(
            result=IndexResult(tree=[]),
            model_id="groq/llama-3.3-70b-versatile",
            prompt_version="build-index-v1",
            fallback_used=True,
        )

        mock_index_analyzer = MagicMock()
        mock_index_analyzer.analyze = AsyncMock(return_value=mock_analyzer_response)

        mock_storage = MagicMock()
        mock_storage.get_result = AsyncMock(return_value=None)
        mock_storage.save_result = AsyncMock()

        mock_ingestion_storage = MagicMock()
        mock_ingestion_storage.get_ir = AsyncMock(return_value=_make_ir())

        service = OnDemandAnalysisService(
            index_analyzer=mock_index_analyzer,
            relations_analyzer=MagicMock(),
            questions_analyzer=MagicMock(),
            conclusions_analyzer=MagicMock(),
            storage=mock_storage,
            ingestion_storage=mock_ingestion_storage,
            card_storage=MagicMock(get_card=AsyncMock(return_value=None)),
        )

        preferences = {
            "language": "es",
            "model_override": "gemini/gemini-2.5-flash",
            "auto_fallback": True,
            "document_language": None,
        }

        record = await service.execute("doc-prop-001", AnalysisType.BUILD_INDEX, preferences)

        assert record.fallback_used is True
        assert record.model_id == "groq/llama-3.3-70b-versatile"
        assert record.requested_model == "gemini/gemini-2.5-flash"
