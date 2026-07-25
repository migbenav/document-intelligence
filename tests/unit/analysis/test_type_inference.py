"""Unit tests for the TypeInferenceService.

Tests cover:
- Successful classification (valid type returned by LLM)
- Low confidence defaults to generic suggestion with None type
- Unparseable response defaults gracefully
- Text sample construction from IR chunks
- LLM called with light model tier (Req 3.5)

Requirements validated: 3.1, 3.2, 3.3, 3.5
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.type_inference import TypeInferenceService, _MAX_SAMPLE_CHARS
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.knowledge_model import TypeSuggestion


# --- Fixtures ---


def _make_ir(chunks_text: list[str]) -> IntermediateRepresentation:
    """Create an IntermediateRepresentation with the given chunk texts."""
    chunks = [
        ContentChunkModel(
            chunk_id=f"chunk-{i:03d}",
            text=text,
            structural_context={"section": f"Section {i}"},
            order=i,
        )
        for i, text in enumerate(chunks_text)
    ]
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient for unit testing."""
    client = AsyncMock(spec=LLMClient)
    return client


@pytest.fixture
def service(mock_llm_client) -> TypeInferenceService:
    """Create a TypeInferenceService with a mocked LLMClient."""
    return TypeInferenceService(llm_client=mock_llm_client)


# --- Successful Classification Tests (Req 3.1, 3.2) ---


class TestSuccessfulClassification:
    @pytest.mark.asyncio
    async def test_prd_classification(self, service, mock_llm_client):
        """When LLM returns a valid PRD type, document_type and suggested_type are set."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "prd",
                "justification": "Contains user stories and acceptance criteria.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["# Product Requirements\n\nAs a user, I want..."])
        result = await service.infer(ir)

        assert result.document_type == "prd"
        assert result.suggested_type == "prd"
        assert result.justification == "Contains user stories and acceptance criteria."

    @pytest.mark.asyncio
    async def test_technical_spec_classification(self, service, mock_llm_client):
        """When LLM returns technical_spec, both fields are set correctly."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "technical_spec",
                "justification": "Contains API definitions and architecture diagrams.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["# API Design\n\nEndpoint: POST /api/v1/users"])
        result = await service.infer(ir)

        assert result.document_type == "technical_spec"
        assert result.suggested_type == "technical_spec"
        assert result.justification == "Contains API definitions and architecture diagrams."

    @pytest.mark.asyncio
    async def test_policy_process_classification(self, service, mock_llm_client):
        """When LLM returns policy_process, both fields are set correctly."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "policy_process",
                "justification": "Describes organizational procedures.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["# Code Review Policy\n\nAll changes must be reviewed."])
        result = await service.infer(ir)

        assert result.document_type == "policy_process"
        assert result.suggested_type == "policy_process"
        assert result.justification == "Describes organizational procedures."

    @pytest.mark.asyncio
    async def test_justification_always_populated(self, service, mock_llm_client):
        """Justification is always populated regardless of type (Req 3.2)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "prd",
                "justification": "This is clearly a PRD.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Some document content"])
        result = await service.infer(ir)

        assert result.justification != ""
        assert len(result.justification) > 0


# --- Low Confidence / Generic Tests (Req 3.3) ---


class TestLowConfidenceDefaults:
    @pytest.mark.asyncio
    async def test_generic_type_from_llm_means_low_confidence(self, service, mock_llm_client):
        """When LLM returns 'generic', document_type=None, suggested_type='generic' (Req 3.3)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "generic",
                "justification": "Does not clearly fit any specific category.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Some ambiguous text content."])
        result = await service.infer(ir)

        assert result.document_type is None
        assert result.suggested_type == "generic"
        assert result.justification == "Does not clearly fit any specific category."

    @pytest.mark.asyncio
    async def test_unknown_type_defaults_to_generic(self, service, mock_llm_client):
        """When LLM returns an unknown type, defaults to generic (Req 3.3)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "unknown_type",
                "justification": "Some justification.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Document content"])
        result = await service.infer(ir)

        assert result.document_type is None
        assert result.suggested_type == "generic"

    @pytest.mark.asyncio
    async def test_null_type_defaults_to_generic(self, service, mock_llm_client):
        """When LLM returns null for document_type, defaults to generic (Req 3.3)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": None,
                "justification": "Could not determine type.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Document content"])
        result = await service.infer(ir)

        assert result.document_type is None
        assert result.suggested_type == "generic"


# --- Unparseable Response Tests (Req 3.3) ---


class TestUnparseableResponse:
    @pytest.mark.asyncio
    async def test_invalid_json_defaults_gracefully(self, service, mock_llm_client):
        """Completely invalid JSON defaults to generic with None type (Req 3.3)."""
        mock_llm_client.call.return_value = LLMResponse(
            content="This is not JSON at all",
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Some content"])
        result = await service.infer(ir)

        assert result.document_type is None
        assert result.suggested_type == "generic"
        assert "parse" in result.justification.lower() or "default" in result.justification.lower()

    @pytest.mark.asyncio
    async def test_partial_json_defaults_gracefully(self, service, mock_llm_client):
        """Partial/truncated JSON defaults gracefully (Req 3.3)."""
        mock_llm_client.call.return_value = LLMResponse(
            content='{"document_type": "prd", "justif',
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Document content"])
        result = await service.infer(ir)

        assert result.document_type is None
        assert result.suggested_type == "generic"

    @pytest.mark.asyncio
    async def test_empty_response_defaults_gracefully(self, service, mock_llm_client):
        """Empty response defaults gracefully (Req 3.3)."""
        mock_llm_client.call.return_value = LLMResponse(
            content="",
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Document content"])
        result = await service.infer(ir)

        assert result.document_type is None
        assert result.suggested_type == "generic"

    @pytest.mark.asyncio
    async def test_json_with_extra_text_surrounding(self, service, mock_llm_client):
        """JSON embedded in extra text cannot be parsed, defaults gracefully."""
        mock_llm_client.call.return_value = LLMResponse(
            content='Here is my answer: {"document_type": "prd", "justification": "reason"} end',
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Document content"])
        result = await service.infer(ir)

        # Can't parse because of surrounding text
        assert result.document_type is None
        assert result.suggested_type == "generic"


# --- LLM Call Configuration Tests (Req 3.5) ---


class TestLLMCallConfiguration:
    @pytest.mark.asyncio
    async def test_uses_light_model_tier(self, service, mock_llm_client):
        """Type inference uses model_tier='light' for the LLM call (Req 3.5)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "prd",
                "justification": "It's a PRD.",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Content"])
        await service.infer(ir)

        mock_llm_client.call.assert_called_once()
        call_kwargs = mock_llm_client.call.call_args
        assert call_kwargs.kwargs["model_tier"] == "light"

    @pytest.mark.asyncio
    async def test_prompt_contains_ir_text(self, service, mock_llm_client):
        """The prompt sent to the LLM contains the IR text sample."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "prd",
                "justification": "reason",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["Unique document content for testing"])
        await service.infer(ir)

        prompt_arg = mock_llm_client.call.call_args.args[0]
        assert "Unique document content for testing" in prompt_arg


# --- Text Sample Construction Tests ---


class TestTextSampleConstruction:
    @pytest.mark.asyncio
    async def test_combines_multiple_chunks(self, service, mock_llm_client):
        """Text sample combines text from multiple chunks."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "prd",
                "justification": "reason",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        ir = _make_ir(["First chunk.", "Second chunk.", "Third chunk."])
        await service.infer(ir)

        prompt_arg = mock_llm_client.call.call_args.args[0]
        assert "First chunk." in prompt_arg
        assert "Second chunk." in prompt_arg
        assert "Third chunk." in prompt_arg

    @pytest.mark.asyncio
    async def test_respects_chunk_order(self, service, mock_llm_client):
        """Chunks are included in document order."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "prd",
                "justification": "reason",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        # Create chunks out of order to verify sorting
        chunks = [
            ContentChunkModel(chunk_id="c2", text="Second", structural_context={}, order=1),
            ContentChunkModel(chunk_id="c0", text="First", structural_context={}, order=0),
            ContentChunkModel(chunk_id="c3", text="Third", structural_context={}, order=2),
        ]
        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1024,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            chunks=chunks,
        )
        await service.infer(ir)

        prompt_arg = mock_llm_client.call.call_args.args[0]
        first_idx = prompt_arg.index("First")
        second_idx = prompt_arg.index("Second")
        third_idx = prompt_arg.index("Third")
        assert first_idx < second_idx < third_idx

    @pytest.mark.asyncio
    async def test_truncates_at_max_sample_chars(self, service, mock_llm_client):
        """Text sample is limited to ~2000 characters."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({
                "document_type": "prd",
                "justification": "reason",
            }),
            model_id="groq/llama-3.3-70b-versatile",
        )

        # Create chunks that exceed the limit. Use a unique marker char that
        # does not appear in the prompt template itself.
        long_text = "\u2588" * 1500  # Unicode full block character
        ir = _make_ir([long_text, long_text, long_text])
        await service.infer(ir)

        prompt_arg = mock_llm_client.call.call_args.args[0]
        # The text sample should not include more than _MAX_SAMPLE_CHARS
        # worth of our marker character (the third chunk should not appear fully)
        assert prompt_arg.count("\u2588") <= _MAX_SAMPLE_CHARS
