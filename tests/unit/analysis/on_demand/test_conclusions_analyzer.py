"""Unit tests for ConclusionsAnalyzer.

Tests: successful parse, invalid JSON raises, timeout raises,
prompt includes full document text, language parameters applied,
and category validation.

Requirements: Req 5 (criteria 1-7)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.on_demand.conclusions_analyzer import (
    ALLOWED_CATEGORIES,
    ConclusionsAnalyzer,
)
from app.analysis.on_demand.models import ConclusionsResult
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentMetadata,
    IntermediateRepresentation,
)


# --- Fixtures ---


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient."""
    client = MagicMock(spec=LLMClient)
    client.call = AsyncMock()
    return client


@pytest.fixture
def sample_ir():
    """Create a sample IntermediateRepresentation for testing."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format="markdown",
            size_bytes=1024,
            language=DetectedLanguage.SPANISH,
            upload_timestamp="2026-07-26T15:00:00Z",
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="c1",
                text="Este reglamento establece las normas de convivencia.",
                structural_context={"section": "Introducción"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="c2",
                text="Los procedimientos de compra se rigen por las siguientes reglas.",
                structural_context={"section": "Procedimientos"},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="c3",
                text="Las definiciones de términos usados en este documento.",
                structural_context={"section": "Definiciones"},
                order=2,
            ),
        ],
    )


@pytest.fixture
def valid_conclusions_response():
    """A valid JSON response representing ConclusionsResult."""
    return {
        "observations": [
            {
                "category": "reordering",
                "description": "La sección de Definiciones aparece después de los Procedimientos que usan esos términos.",
                "suggestion": "Considere mover la sección Definiciones antes del capítulo de Procedimientos.",
                "section_ref": "Definiciones",
                "source_ref": {
                    "chunk_ids": ["c3"],
                    "text_excerpt": "Las definiciones de términos usados en este documento.",
                    "section": "Definiciones",
                },
            },
            {
                "category": "coherence",
                "description": "Section mixes normative and procedural content.",
                "suggestion": "Separar el contenido normativo del procedimental en secciones distintas.",
                "section_ref": "Procedimientos",
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Los procedimientos de compra se rigen por las siguientes reglas.",
                    "section": "Procedimientos",
                },
            },
            {
                "category": "missing",
                "description": "No scope section found for a normative document.",
                "suggestion": "Agregar una sección de Alcance al inicio del documento.",
                "section_ref": None,
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Este reglamento establece las normas de convivencia.",
                    "section": "Introducción",
                },
            },
        ]
    }


# --- Tests ---


class TestConclusionsAnalyzerSuccess:
    """Tests for successful analysis execution."""

    @pytest.mark.asyncio
    async def test_successful_parse_returns_conclusions_result(
        self, mock_llm_client, sample_ir, valid_conclusions_response
    ):
        """Analyzer returns ConclusionsResult on valid LLM response."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_conclusions_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        result = await analyzer.analyze(
            sample_ir, language="es", document_language="es"
        )

        assert isinstance(result, ConclusionsResult)
        assert len(result.observations) == 3
        assert result.observations[0].category == "reordering"
        assert result.observations[1].category == "coherence"
        assert result.observations[2].category == "missing"

    @pytest.mark.asyncio
    async def test_strips_json_fences(
        self, mock_llm_client, sample_ir, valid_conclusions_response
    ):
        """Analyzer strips ```json fences from LLM response."""
        fenced_content = f"```json\n{json.dumps(valid_conclusions_response)}\n```"
        mock_llm_client.call.return_value = LLMResponse(
            content=fenced_content,
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        result = await analyzer.analyze(
            sample_ir, language="en", document_language="es"
        )

        assert isinstance(result, ConclusionsResult)
        assert len(result.observations) == 3

    @pytest.mark.asyncio
    async def test_prompt_includes_document_text(
        self, mock_llm_client, sample_ir, valid_conclusions_response
    ):
        """Prompt sent to LLM includes the full document text from IR chunks."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_conclusions_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(sample_ir, language="es", document_language="es")

        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0]  # First positional arg is the prompt

        # Verify all chunk texts are in the prompt
        assert "Este reglamento establece las normas de convivencia." in prompt
        assert "Los procedimientos de compra se rigen por las siguientes reglas." in prompt
        assert "Las definiciones de términos usados en este documento." in prompt
        # Verify section markers
        assert "[Section: Introducción]" in prompt
        assert "[Section: Procedimientos]" in prompt
        assert "[Section: Definiciones]" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_both_languages(
        self, mock_llm_client, sample_ir, valid_conclusions_response
    ):
        """Prompt includes both response_language and document_language placeholders."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_conclusions_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(
            sample_ir, language="en", document_language="es"
        )

        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0]

        # The prompt should contain the language values substituted
        assert "en" in prompt  # response_language
        assert "es" in prompt  # document_language

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_parameters(
        self, mock_llm_client, sample_ir, valid_conclusions_response
    ):
        """LLM client is called with primary tier, temperature 0.1."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_conclusions_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(
            sample_ir,
            language="es",
            document_language="es",
            model_override="custom-model",
            auto_fallback=False,
        )

        mock_llm_client.call.assert_called_once()
        call_kwargs = mock_llm_client.call.call_args[1]
        assert call_kwargs["model_tier"] == "primary"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["model_override"] == "custom-model"
        assert call_kwargs["auto_fallback"] is False


class TestConclusionsAnalyzerErrors:
    """Tests for error conditions."""

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(
        self, mock_llm_client, sample_ir
    ):
        """Analyzer raises ValueError when LLM returns invalid JSON."""
        mock_llm_client.call.return_value = LLMResponse(
            content="This is not JSON at all",
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)

        with pytest.raises(ValueError, match="invalid JSON"):
            await analyzer.analyze(
                sample_ir, language="es", document_language="es"
            )

    @pytest.mark.asyncio
    async def test_schema_validation_failure_raises_value_error(
        self, mock_llm_client, sample_ir
    ):
        """Analyzer raises ValueError when JSON doesn't match ConclusionsResult schema."""
        # Missing required 'observations' field
        invalid_data = {"wrong_field": []}
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(invalid_data),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)

        with pytest.raises(ValueError, match="schema validation"):
            await analyzer.analyze(
                sample_ir, language="es", document_language="es"
            )

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error(
        self, mock_llm_client, sample_ir
    ):
        """Analyzer raises TimeoutError when LLM exceeds 30s."""

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(60)
            return LLMResponse(content="{}", model_id="test")

        mock_llm_client.call = slow_call

        analyzer = ConclusionsAnalyzer(mock_llm_client)

        with pytest.raises(asyncio.TimeoutError):
            await analyzer.analyze(
                sample_ir, language="es", document_language="es"
            )


class TestConclusionsAnalyzerCategoryValidation:
    """Tests for category validation logic."""

    @pytest.mark.asyncio
    async def test_invalid_category_defaults_to_coherence(
        self, mock_llm_client, sample_ir
    ):
        """Observations with invalid categories default to 'coherence'."""
        data = {
            "observations": [
                {
                    "category": "style",  # Invalid category
                    "description": "Some observation",
                    "suggestion": "Some suggestion",
                    "section_ref": None,
                    "source_ref": {
                        "chunk_ids": ["c1"],
                        "text_excerpt": "Some text",
                        "section": "Intro",
                    },
                }
            ]
        }
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(data),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        result = await analyzer.analyze(
            sample_ir, language="es", document_language="es"
        )

        # Invalid category "style" should be corrected to "coherence"
        assert result.observations[0].category == "coherence"

    def test_allowed_categories_matches_spec(self):
        """ALLOWED_CATEGORIES constant matches the spec's five categories."""
        expected = {"coherence", "reordering", "duplication", "orphan", "missing"}
        assert ALLOWED_CATEGORIES == expected

    @pytest.mark.asyncio
    async def test_all_valid_categories_pass_through(
        self, mock_llm_client, sample_ir
    ):
        """All valid categories pass through without modification."""
        data = {
            "observations": [
                {
                    "category": category,
                    "description": f"Observation about {category}",
                    "suggestion": f"Fix {category}",
                    "section_ref": None,
                    "source_ref": {
                        "chunk_ids": ["c1"],
                        "text_excerpt": "text",
                        "section": "Section",
                    },
                }
                for category in ALLOWED_CATEGORIES
            ]
        }
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(data),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        result = await analyzer.analyze(
            sample_ir, language="en", document_language="en"
        )

        result_categories = {obs.category for obs in result.observations}
        assert result_categories == ALLOWED_CATEGORIES


class TestConclusionsAnalyzerPromptVersion:
    """Tests for prompt version tracking."""

    def test_prompt_version_is_conclusions_v1(self):
        """ConclusionsAnalyzer.PROMPT_VERSION matches the prompt template version."""
        assert ConclusionsAnalyzer.PROMPT_VERSION == "conclusions-v1"
