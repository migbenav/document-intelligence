"""Unit tests for Questions Answered v2 prompt and model changes.

Tests cover:
- Prompt includes document classification
- Normative classification produces regulatory-style instructions
- QuestionsResult with coherence_note parses correctly
- Prompt instructs specificity (questions are not generic)

Requirements covered: Req 2 (criteria 1-9)
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMResponse
from app.analysis.on_demand.analyzer_response import AnalyzerResponse
from app.analysis.on_demand.models import QuestionsResult
from app.analysis.on_demand.prompts.questions_answered_v2 import (
    PROMPT_VERSION,
    format_prompt,
    get_classification_instructions,
)
from app.analysis.on_demand.questions_analyzer import QuestionsAnalyzer
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)


def _make_ir() -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    chunks = [
        ContentChunkModel(
            chunk_id="c1",
            text="Artículo 1. Objeto del reglamento.",
            structural_context={"section": "Capítulo I"},
            order=0,
        ),
        ContentChunkModel(
            chunk_id="c2",
            text="Artículo 2. Ámbito de aplicación.",
            structural_context={"section": "Capítulo II"},
            order=1,
        ),
    ]
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="reglamento.pdf",
            format=DocumentFormat.PDF,
            size_bytes=4096,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )


def _valid_questions_response_with_coherence_note() -> dict:
    """Return a valid QuestionsResult JSON with coherence_note set."""
    return {
        "document_questions": [
            {
                "question": "¿Qué regula este reglamento?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Artículo 1. Objeto del reglamento.",
                    "section": "Capítulo I",
                },
            },
            {
                "question": "¿A quién aplica este reglamento?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Artículo 2. Ámbito de aplicación.",
                    "section": "Capítulo II",
                },
            },
            {
                "question": "¿Cuáles son las consecuencias del incumplimiento?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Artículo 1. Objeto del reglamento.",
                    "section": "Capítulo I",
                },
            },
        ],
        "section_questions": [
            {
                "question": "¿Qué establece el Capítulo I como objeto regulatorio?",
                "level": "section",
                "section_title": "Capítulo I",
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Artículo 1. Objeto del reglamento.",
                    "section": "Capítulo I",
                },
            },
        ],
        "coherence_note": "El documento carece de un hilo conductor claro entre los capítulos.",
    }


def _valid_questions_response_no_coherence_note() -> dict:
    """Return a valid QuestionsResult JSON without coherence_note."""
    return {
        "document_questions": [
            {
                "question": "¿Qué regula este reglamento?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Artículo 1. Objeto del reglamento.",
                    "section": "Capítulo I",
                },
            },
            {
                "question": "¿A quién aplica este reglamento?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Artículo 2. Ámbito de aplicación.",
                    "section": "Capítulo II",
                },
            },
            {
                "question": "¿Cuáles son las consecuencias del incumplimiento?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Artículo 1. Objeto del reglamento.",
                    "section": "Capítulo I",
                },
            },
        ],
        "section_questions": [
            {
                "question": "¿Qué establece el Capítulo I?",
                "level": "section",
                "section_title": "Capítulo I",
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Artículo 1. Objeto del reglamento.",
                    "section": "Capítulo I",
                },
            },
        ],
    }


def _make_mock_llm_client(response_content: str) -> MagicMock:
    """Create a mock LLMClient that returns the given content."""
    mock_client = MagicMock()
    mock_client.call = AsyncMock(
        return_value=LLMResponse(
            content=response_content, model_id="gemini/gemini-2.5-flash"
        )
    )
    mock_client.primary_model = "gemini/gemini-2.5-flash"
    return mock_client


class TestPromptIncludesClassification:
    """Verify that the prompt includes the document classification."""

    @pytest.mark.asyncio
    async def test_prompt_contains_classification_label(self):
        """The formatted prompt includes 'This is a {classification} document.'"""
        mock_client = _make_mock_llm_client(
            json.dumps(_valid_questions_response_no_coherence_note())
        )
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "This is a normative document." in prompt

    @pytest.mark.asyncio
    async def test_prompt_contains_procedure_classification(self):
        """The prompt reflects 'procedure' classification when provided."""
        mock_client = _make_mock_llm_client(
            json.dumps(_valid_questions_response_no_coherence_note())
        )
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="procedure")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "This is a procedure document." in prompt

    @pytest.mark.asyncio
    async def test_prompt_defaults_to_generic_classification(self):
        """Without explicit classification, 'generic' is used."""
        mock_client = _make_mock_llm_client(
            json.dumps(_valid_questions_response_no_coherence_note())
        )
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "This is a generic document." in prompt

    def test_format_prompt_includes_classification(self):
        """format_prompt() embeds the classification in the output."""
        prompt = format_prompt(
            classification="narrative",
            response_language="en",
            document_text="Some text here.",
        )
        assert "This is a narrative document." in prompt


class TestNormativeClassificationInstructions:
    """Verify normative classification produces regulatory-style instructions."""

    def test_get_classification_instructions_normative(self):
        """Normative classification returns regulatory logic instructions."""
        instructions = get_classification_instructions("normative")
        assert "REGULATORY LOGIC" in instructions
        assert "What does it regulate?" in instructions
        assert "What is permitted?" in instructions
        assert "What is prohibited?" in instructions
        assert "Who enforces?" in instructions
        assert "What are consequences?" in instructions

    def test_get_classification_instructions_procedure(self):
        """Procedure classification returns process logic instructions."""
        instructions = get_classification_instructions("procedure")
        assert "PROCESS LOGIC" in instructions
        assert "Who decides?" in instructions

    def test_get_classification_instructions_narrative(self):
        """Narrative classification returns narrative logic instructions."""
        instructions = get_classification_instructions("narrative")
        assert "NARRATIVE LOGIC" in instructions
        assert "What sequence does it follow?" in instructions

    def test_get_classification_instructions_generic(self):
        """Generic classification returns functional logic instructions."""
        instructions = get_classification_instructions("generic")
        assert "FUNCTIONAL LOGIC" in instructions

    def test_get_classification_instructions_unknown_falls_back_to_generic(self):
        """Unknown classification falls back to generic instructions."""
        instructions = get_classification_instructions("unknown_type")
        assert "FUNCTIONAL LOGIC" in instructions

    @pytest.mark.asyncio
    async def test_normative_prompt_contains_regulatory_instructions(self):
        """Full prompt for normative documents includes regulatory keywords."""
        mock_client = _make_mock_llm_client(
            json.dumps(_valid_questions_response_no_coherence_note())
        )
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "REGULATORY LOGIC" in prompt
        assert "What is permitted?" in prompt
        assert "What is prohibited?" in prompt


class TestCoherenceNoteParsing:
    """Verify QuestionsResult with coherence_note parses correctly."""

    @pytest.mark.asyncio
    async def test_result_with_coherence_note(self):
        """QuestionsResult includes coherence_note when LLM provides it."""
        response_data = _valid_questions_response_with_coherence_note()
        mock_client = _make_mock_llm_client(json.dumps(response_data))
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        analyzer_response = await analyzer.analyze(
            ir, language="es", classification="generic"
        )

        result = analyzer_response.result
        assert isinstance(result, QuestionsResult)
        assert result.coherence_note is not None
        assert "carece de un hilo conductor" in result.coherence_note

    @pytest.mark.asyncio
    async def test_result_without_coherence_note(self):
        """QuestionsResult has coherence_note=None when not provided by LLM."""
        response_data = _valid_questions_response_no_coherence_note()
        mock_client = _make_mock_llm_client(json.dumps(response_data))
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        analyzer_response = await analyzer.analyze(
            ir, language="es", classification="normative"
        )

        result = analyzer_response.result
        assert isinstance(result, QuestionsResult)
        assert result.coherence_note is None

    def test_questions_result_model_validate_with_coherence_note(self):
        """QuestionsResult.model_validate parses coherence_note correctly."""
        data = _valid_questions_response_with_coherence_note()
        result = QuestionsResult.model_validate(data)
        assert result.coherence_note == "El documento carece de un hilo conductor claro entre los capítulos."

    def test_questions_result_model_validate_without_coherence_note(self):
        """QuestionsResult.model_validate sets coherence_note to None when absent."""
        data = _valid_questions_response_no_coherence_note()
        result = QuestionsResult.model_validate(data)
        assert result.coherence_note is None

    def test_questions_result_model_validate_with_null_coherence_note(self):
        """QuestionsResult.model_validate handles explicit null coherence_note."""
        data = _valid_questions_response_no_coherence_note()
        data["coherence_note"] = None
        result = QuestionsResult.model_validate(data)
        assert result.coherence_note is None


class TestPromptInstructsSpecificity:
    """Verify the prompt instructs questions to be specific, not generic."""

    def test_prompt_contains_specificity_instruction(self):
        """The prompt template includes instructions against generic questions."""
        prompt = format_prompt(
            classification="normative",
            response_language="es",
            document_text="Documento de prueba.",
        )
        # Check that the prompt explicitly asks for specificity
        assert "SPECIFIC" in prompt
        assert "never generic" in prompt

    def test_prompt_contains_bad_question_examples(self):
        """The prompt includes examples of bad generic questions to avoid."""
        prompt = format_prompt(
            classification="generic",
            response_language="en",
            document_text="Test document.",
        )
        assert "What does chapter 3 cover?" in prompt
        assert "What is discussed in the introduction?" in prompt

    def test_prompt_contains_good_question_examples(self):
        """The prompt includes examples of specific logic-revealing questions."""
        prompt = format_prompt(
            classification="generic",
            response_language="en",
            document_text="Test document.",
        )
        assert "Who is authorized to approve expenses" in prompt
        assert "What sequence of steps converts" in prompt

    def test_prompt_forbids_describing_content(self):
        """The prompt explicitly forbids questions that just describe content."""
        prompt = format_prompt(
            classification="procedure",
            response_language="es",
            document_text="Procedimiento de compras.",
        )
        assert 'Do NOT produce questions that simply describe what a section "talks about."' in prompt

    def test_prompt_requires_logical_chain(self):
        """The prompt requires questions to reveal the document's logical chain."""
        prompt = format_prompt(
            classification="normative",
            response_language="en",
            document_text="Regulatory document.",
        )
        assert "LOGICAL CHAIN" in prompt

    @pytest.mark.asyncio
    async def test_analyzer_returns_analyzer_response(self):
        """Analyzer returns an AnalyzerResponse with correct metadata."""
        response_data = _valid_questions_response_no_coherence_note()
        mock_client = _make_mock_llm_client(json.dumps(response_data))
        analyzer = QuestionsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(
            ir, language="es", classification="normative"
        )

        assert isinstance(response, AnalyzerResponse)
        assert response.model_id == "gemini/gemini-2.5-flash"
        assert response.prompt_version == "questions-answered-v2"
        assert response.fallback_used is False
