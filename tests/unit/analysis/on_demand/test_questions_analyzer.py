"""Unit tests for QuestionsAnalyzer (Questions Answered, C3.3).

Tests cover: successful parse, invalid JSON, validation errors, timeout,
prompt construction, language parameter application, and cascade level validation.
All tests mock LLMClient.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMResponse
from app.analysis.on_demand.questions_analyzer import (
    QuestionsAnalyzer,
    QuestionsAnalysisError,
    _extract_json,
)
from app.analysis.on_demand.models import QuestionsResult
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


def _valid_questions_response() -> dict:
    """Return a valid QuestionsResult JSON structure."""
    return {
        "document_questions": [
            {
                "question": "What is the purpose of this policy?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Introduction to the policy.",
                    "section": "Introduction",
                },
            },
            {
                "question": "Who is responsible for enforcement?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c1", "c2"],
                    "text_excerpt": "The department head enforces compliance.",
                    "section": "Introduction",
                },
            },
            {
                "question": "What procedures are established?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Details of the procedure.",
                    "section": "Procedure",
                },
            },
        ],
        "section_questions": [
            {
                "question": "What does the policy cover?",
                "level": "section",
                "section_title": "Introduction",
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Introduction to the policy.",
                    "section": "Introduction",
                },
            },
            {
                "question": "How is the procedure conducted?",
                "level": "section",
                "section_title": "Procedure",
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Details of the procedure.",
                    "section": "Procedure",
                },
            },
        ],
    }


def _make_mock_llm_client(response_content: str) -> MagicMock:
    """Create a mock LLMClient that returns the given content."""
    mock_client = MagicMock()
    mock_client.call = AsyncMock(
        return_value=LLMResponse(content=response_content, model_id="gemini/gemini-2.5-flash")
    )
    return mock_client


class TestExtractJson:
    """Tests for the JSON extraction helper."""

    def test_plain_json(self):
        text = '{"document_questions": [], "section_questions": []}'
        assert _extract_json(text) == '{"document_questions": [], "section_questions": []}'

    def test_json_in_fences(self):
        text = '```json\n{"document_questions": [], "section_questions": []}\n```'
        assert _extract_json(text) == '{"document_questions": [], "section_questions": []}'

    def test_json_in_fences_no_language(self):
        text = '```\n{"document_questions": []}\n```'
        assert _extract_json(text) == '{"document_questions": []}'

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n```json\n{"document_questions": []}\n```\nDone.'
        assert _extract_json(text) == '{"document_questions": []}'

    def test_strips_whitespace(self):
        text = '  {"document_questions": []}  '
        assert _extract_json(text) == '{"document_questions": []}'


class TestQuestionsAnalyzerSuccess:
    """Tests for successful analysis scenarios."""

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        """A valid JSON response produces a valid AnalyzerResponse with QuestionsResult."""
        response_data = _valid_questions_response()
        mock_client = _make_mock_llm_client(json.dumps(response_data))
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        from app.analysis.on_demand.analyzer_response import AnalyzerResponse
        assert isinstance(response, AnalyzerResponse)
        result = response.result
        assert isinstance(result, QuestionsResult)
        assert len(result.document_questions) == 3
        assert len(result.section_questions) == 2
        assert result.document_questions[0].question == "What is the purpose of this policy?"
        assert result.document_questions[0].level == "document"
        assert result.section_questions[0].question == "What does the policy cover?"
        assert result.section_questions[0].level == "section"
        assert result.section_questions[0].section_title == "Introduction"

    @pytest.mark.asyncio
    async def test_response_with_json_fences(self):
        """LLM response wrapped in ```json fences is handled correctly."""
        response_data = _valid_questions_response()
        content = f"```json\n{json.dumps(response_data)}\n```"
        mock_client = _make_mock_llm_client(content)
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="en")

        from app.analysis.on_demand.analyzer_response import AnalyzerResponse
        assert isinstance(response, AnalyzerResponse)
        result = response.result
        assert isinstance(result, QuestionsResult)
        assert len(result.document_questions) == 3
        assert len(result.section_questions) == 2

    @pytest.mark.asyncio
    async def test_prompt_includes_document_text(self):
        """The prompt sent to the LLM includes the full document text."""
        mock_client = _make_mock_llm_client(
            json.dumps({"document_questions": [], "section_questions": []})
        )
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
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
        mock_client = _make_mock_llm_client(
            json.dumps({"document_questions": [], "section_questions": []})
        )
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "Respond in es" in prompt

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_parameters(self):
        """LLMClient.call is invoked with expected parameters."""
        mock_client = _make_mock_llm_client(
            json.dumps({"document_questions": [], "section_questions": []})
        )
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(
            ir, language="en", model_override="custom-model", auto_fallback=False
        )

        mock_client.call.assert_called_once()
        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["model_tier"] == "primary"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["model_override"] == "custom-model"
        assert call_kwargs["auto_fallback"] is False

    @pytest.mark.asyncio
    async def test_prompt_version_property(self):
        """The analyzer exposes the prompt version."""
        mock_client = MagicMock()
        analyzer = QuestionsAnalyzer(mock_client)

        assert analyzer.prompt_version == "questions-answered-v2"


class TestQuestionsAnalyzerCascadeValidation:
    """Tests for cascade level validation logic."""

    @pytest.mark.asyncio
    async def test_document_question_with_wrong_level_raises_error(self):
        """A document_question with level='section' raises QuestionsAnalysisError."""
        data = _valid_questions_response()
        data["document_questions"][0]["level"] = "section"
        mock_client = _make_mock_llm_client(json.dumps(data))
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(
            QuestionsAnalysisError, match="document_questions\\[0\\] has level='section'"
        ):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_section_question_with_wrong_level_raises_error(self):
        """A section_question with level='document' raises QuestionsAnalysisError."""
        data = _valid_questions_response()
        data["section_questions"][0]["level"] = "document"
        mock_client = _make_mock_llm_client(json.dumps(data))
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(
            QuestionsAnalysisError, match="section_questions\\[0\\] has level='document'"
        ):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_all_document_questions_have_correct_level(self):
        """All document_questions with correct level='document' pass validation."""
        data = _valid_questions_response()
        mock_client = _make_mock_llm_client(json.dumps(data))
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        for q in response.result.document_questions:
            assert q.level == "document"

    @pytest.mark.asyncio
    async def test_all_section_questions_have_correct_level(self):
        """All section_questions with correct level='section' pass validation."""
        data = _valid_questions_response()
        mock_client = _make_mock_llm_client(json.dumps(data))
        mock_client.primary_model = "gemini/gemini-2.5-flash"
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        for q in response.result.section_questions:
            assert q.level == "section"


class TestQuestionsAnalyzerFailures:
    """Tests for error scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self):
        """Non-JSON LLM response raises QuestionsAnalysisError."""
        mock_client = _make_mock_llm_client("This is not JSON at all.")
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(QuestionsAnalysisError, match="not valid JSON"):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_invalid_schema_raises_error(self):
        """Valid JSON that doesn't match QuestionsResult schema raises error."""
        # Missing required 'section_questions' field
        mock_client = _make_mock_llm_client(json.dumps({"questions": []}))
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(QuestionsAnalysisError, match="does not match QuestionsResult schema"):
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
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(asyncio.TimeoutError):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_llm_exception_propagates(self):
        """Exceptions from LLMClient.call propagate to the caller."""
        mock_client = MagicMock()
        mock_client.call = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            await analyzer.analyze(ir, language="es")
