"""Unit tests for IndexAnalyzer (Build Index, C3.1).

Tests cover: successful parse, invalid JSON, validation errors, timeout,
prompt construction, and language parameter application.
All tests mock LLMClient.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMResponse
from app.analysis.on_demand.analyzer_response import AnalyzerResponse
from app.analysis.on_demand.index_analyzer import (
    IndexAnalyzer,
    IndexAnalysisError,
    _extract_json,
)
from app.analysis.on_demand.models import IndexResult
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)


def _make_ir(chunks: list[ContentChunkModel] | None = None) -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    if chunks is None:
        chunks = [
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
        ]
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="policy.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=2048,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )


def _valid_index_response() -> dict:
    """Return a valid IndexResult JSON structure."""
    return {
        "tree": [
            {
                "id": "node-1",
                "title": "Introduction",
                "level": 1,
                "role": "defines",
                "question_answered": "What is this document about?",
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Introduction to the policy.",
                    "section": "Introduction",
                },
                "children": [
                    {
                        "id": "node-1.1",
                        "title": "Scope",
                        "level": 2,
                        "role": "restricts",
                        "question_answered": "What is the scope of this policy?",
                        "source_ref": {
                            "chunk_ids": ["c1"],
                            "text_excerpt": "Introduction to the policy.",
                            "section": "Introduction",
                        },
                        "children": [],
                    }
                ],
            },
            {
                "id": "node-2",
                "title": "Procedure",
                "level": 1,
                "role": "establishes",
                "question_answered": "How is the procedure conducted?",
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Details of the procedure.",
                    "section": "Procedure",
                },
                "children": [],
            },
        ]
    }


def _make_mock_llm_client(response_content: str, model_id: str = "gemini/gemini-2.5-flash") -> MagicMock:
    """Create a mock LLMClient that returns the given content."""
    mock_client = MagicMock()
    mock_client.primary_model = "gemini/gemini-2.5-flash"
    mock_client.call = AsyncMock(
        return_value=LLMResponse(content=response_content, model_id=model_id)
    )
    return mock_client


class TestExtractJson:
    """Tests for the JSON extraction helper."""

    def test_plain_json(self):
        text = '{"tree": []}'
        assert _extract_json(text) == '{"tree": []}'

    def test_json_in_fences(self):
        text = '```json\n{"tree": []}\n```'
        assert _extract_json(text) == '{"tree": []}'

    def test_json_in_fences_no_language(self):
        text = '```\n{"tree": []}\n```'
        assert _extract_json(text) == '{"tree": []}'

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n```json\n{"tree": []}\n```\nDone.'
        assert _extract_json(text) == '{"tree": []}'

    def test_strips_whitespace(self):
        text = '  {"tree": []}  '
        assert _extract_json(text) == '{"tree": []}'


class TestIndexAnalyzerSuccess:
    """Tests for successful analysis scenarios."""

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        """A valid JSON response produces a valid AnalyzerResponse with IndexResult."""
        response_data = _valid_index_response()
        mock_client = _make_mock_llm_client(json.dumps(response_data))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        assert isinstance(response, AnalyzerResponse)
        assert isinstance(response.result, IndexResult)
        assert response.model_id == "gemini/gemini-2.5-flash"
        assert response.prompt_version == "build-index-v2"
        assert response.fallback_used is False
        assert len(response.result.tree) == 2
        assert response.result.tree[0].title == "Introduction"
        assert response.result.tree[0].role == "defines"
        assert response.result.tree[0].children[0].title == "Scope"
        assert response.result.tree[1].title == "Procedure"

    @pytest.mark.asyncio
    async def test_response_with_json_fences(self):
        """LLM response wrapped in ```json fences is handled correctly."""
        response_data = _valid_index_response()
        content = f"```json\n{json.dumps(response_data)}\n```"
        mock_client = _make_mock_llm_client(content)
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="en")

        assert isinstance(response, AnalyzerResponse)
        assert isinstance(response.result, IndexResult)
        assert len(response.result.tree) == 2

    @pytest.mark.asyncio
    async def test_prompt_includes_document_text(self):
        """The prompt sent to the LLM includes the full document text."""
        mock_client = _make_mock_llm_client(json.dumps({"tree": []}))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "[Section: Introduction] (chunk 0)" in prompt
        assert "Introduction to the policy." in prompt
        assert "[Section: Procedure] (chunk 1)" in prompt
        assert "Details of the procedure." in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_language(self):
        """The prompt includes the response language instruction."""
        mock_client = _make_mock_llm_client(json.dumps({"tree": []}))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "Respond in es" in prompt

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_parameters(self):
        """LLMClient.call is invoked with expected parameters."""
        mock_client = _make_mock_llm_client(json.dumps({"tree": []}))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(
            ir, language="en", model_override="custom-model", auto_fallback=False
        )

        mock_client.call.assert_called_once()
        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["model_tier"] == "primary"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["model_override"] == "custom-model"
        assert call_kwargs["auto_fallback"] is False
        # model_id differs from model_override, so fallback_used should be True
        assert response.fallback_used is True

    @pytest.mark.asyncio
    async def test_prompt_version_property(self):
        """The analyzer exposes the prompt version."""
        mock_client = MagicMock()
        analyzer = IndexAnalyzer(mock_client)

        assert analyzer.prompt_version == "build-index-v2"


class TestIndexAnalyzerFailures:
    """Tests for error scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self):
        """Non-JSON LLM response raises IndexAnalysisError."""
        mock_client = _make_mock_llm_client("This is not JSON at all.")
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(IndexAnalysisError, match="not valid JSON"):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_invalid_schema_raises_error(self):
        """Valid JSON that doesn't match IndexResult schema raises IndexAnalysisError."""
        # Missing required 'tree' field
        mock_client = _make_mock_llm_client(json.dumps({"nodes": []}))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(IndexAnalysisError, match="does not match IndexResult schema"):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_invalid_node_structure_raises_error(self):
        """A tree node with invalid level raises IndexAnalysisError."""
        data = {
            "tree": [
                {
                    "id": "node-1",
                    "title": "Test",
                    "level": 10,  # exceeds max of 6
                    "role": None,
                    "question_answered": None,
                    "source_ref": None,
                    "children": [],
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(IndexAnalysisError, match="does not match IndexResult schema"):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_timeout_raises_asyncio_timeout(self):
        """LLM call exceeding timeout raises asyncio.TimeoutError."""
        mock_client = MagicMock()
        mock_client.primary_model = "gemini/gemini-2.5-flash"

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(120)
            return LLMResponse(content="{}", model_id="test")

        mock_client.call = slow_call
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(asyncio.TimeoutError):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_llm_exception_propagates(self):
        """Exceptions from LLMClient.call propagate to the caller."""
        mock_client = MagicMock()
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        mock_client.call = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            await analyzer.analyze(ir, language="es")
