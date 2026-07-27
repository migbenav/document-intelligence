"""Unit tests for the LLMAnalyzer module.

Tests cover:
- Successful call: valid JSON response → LLMAnalysisResult
- Timeout: asyncio.TimeoutError → returns None
- LLM error: LLMTransientError → returns None
- LLM auth error: LLMAuthenticationError → returns None
- Invalid JSON response → returns None
- Missing fields in JSON → returns None
- Invalid classification value → returns None
- Prompt construction: includes title, org_type, text sample ≤2000 chars
- model_tier="light" and temperature=0.1 are passed
- PROMPT_VERSION is included in result
- Data minimization: no document_id, user identity, or session history in prompt

Requirements validated: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.base_analysis.llm_analyzer import (
    LLM_TIMEOUT_SECONDS,
    LLMAnalysisResult,
    LLMAnalyzer,
    MAX_CHUNKS,
    MAX_TEXT_SAMPLE_CHARS,
)
from app.analysis.base_analysis.prompts import PROMPT_TEMPLATE, PROMPT_VERSION
from app.analysis.llm_client import (
    LLMAuthenticationError,
    LLMResponse,
    LLMTransientError,
)
from app.models.document import ContentChunkModel
from app.models.document_card import DocumentClassification, OrganizationType


# --- Helpers ---


def _make_chunk(text: str, order: int = 0) -> ContentChunkModel:
    """Create a content chunk for testing."""
    return ContentChunkModel(
        chunk_id=f"chunk-{order}",
        text=text,
        structural_context={"section": "Test Section"},
        order=order,
    )


def _make_chunks(count: int, text: str = "Sample text content.") -> list[ContentChunkModel]:
    """Create a list of content chunks for testing."""
    return [_make_chunk(text=f"{text} Chunk {i}.", order=i) for i in range(count)]


def _make_valid_llm_response(
    summary: str = "This is a test document about regulations.",
    classification: str = "normative",
    model_id: str = "groq/llama-3.3-70b-versatile",
) -> LLMResponse:
    """Create a valid LLM response with JSON content."""
    content = json.dumps({"summary": summary, "classification": classification})
    return LLMResponse(content=content, model_id=model_id)


def _make_mock_llm_client(response: LLMResponse | None = None) -> MagicMock:
    """Create a mock LLMClient that returns the given response."""
    client = MagicMock()
    if response is not None:
        client.call = AsyncMock(return_value=response)
    return client


# --- Tests: Successful Call ---


@pytest.mark.asyncio
async def test_analyze_success_returns_llm_analysis_result():
    """Valid JSON response from LLM produces a LLMAnalysisResult."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(5),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is not None
    assert isinstance(result, LLMAnalysisResult)
    assert result.summary == "This is a test document about regulations."
    assert result.classification == DocumentClassification.NORMATIVE
    assert result.model_id == "groq/llama-3.3-70b-versatile"
    assert result.prompt_version == PROMPT_VERSION


@pytest.mark.asyncio
async def test_analyze_success_all_classification_values():
    """Each valid classification value is accepted."""
    for classification in DocumentClassification:
        response = _make_valid_llm_response(classification=classification.value)
        client = _make_mock_llm_client(response)
        analyzer = LLMAnalyzer(client)

        result = await analyzer.analyze(
            title="Test",
            chunks=_make_chunks(1),
            organization_type=OrganizationType.FREE_FORM,
        )

        assert result is not None
        assert result.classification == classification


# --- Tests: Timeout ---


@pytest.mark.asyncio
async def test_analyze_timeout_returns_none():
    """asyncio.TimeoutError results in None (Req 3.3)."""
    client = MagicMock()
    client.call = AsyncMock(side_effect=asyncio.TimeoutError())
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.HEADED_SECTIONS,
    )

    assert result is None


# --- Tests: LLM Errors ---


@pytest.mark.asyncio
async def test_analyze_transient_error_returns_none():
    """LLMTransientError results in None (Req 3.4)."""
    client = MagicMock()
    client.call = AsyncMock(side_effect=LLMTransientError("Rate limit exceeded"))
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.NUMBERED_ARTICLES,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_auth_error_returns_none():
    """LLMAuthenticationError results in None (Req 3.4)."""
    client = MagicMock()
    client.call = AsyncMock(side_effect=LLMAuthenticationError("Invalid API key"))
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_unexpected_error_returns_none():
    """Any unexpected exception results in None (Req 3.4)."""
    client = MagicMock()
    client.call = AsyncMock(side_effect=RuntimeError("Something unexpected"))
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


# --- Tests: Invalid JSON ---


@pytest.mark.asyncio
async def test_analyze_invalid_json_returns_none():
    """Non-JSON LLM response results in None (Req 3.5)."""
    response = LLMResponse(content="This is not JSON at all", model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_json_array_returns_none():
    """JSON array (not object) results in None."""
    response = LLMResponse(content='["not", "an", "object"]', model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_empty_string_response_returns_none():
    """Empty string response results in None."""
    response = LLMResponse(content="", model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


# --- Tests: Missing Fields ---


@pytest.mark.asyncio
async def test_analyze_missing_summary_returns_none():
    """JSON missing 'summary' field results in None (Req 3.5)."""
    content = json.dumps({"classification": "normative"})
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_missing_classification_returns_none():
    """JSON missing 'classification' field results in None (Req 3.5)."""
    content = json.dumps({"summary": "Some summary text."})
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_empty_summary_returns_none():
    """Empty string summary results in None."""
    content = json.dumps({"summary": "", "classification": "normative"})
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_invalid_classification_value_returns_none():
    """Classification value not in the enum results in None."""
    content = json.dumps({"summary": "A summary.", "classification": "invalid_type"})
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


@pytest.mark.asyncio
async def test_analyze_null_summary_returns_none():
    """Null summary value results in None."""
    content = json.dumps({"summary": None, "classification": "normative"})
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


# --- Tests: Prompt Construction ---


@pytest.mark.asyncio
async def test_prompt_includes_title_and_org_type():
    """Prompt contains the title and organization_type (Req 3.1)."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="My Important Document",
        chunks=_make_chunks(3),
        organization_type=OrganizationType.NUMBERED_ARTICLES,
    )

    # Verify the prompt passed to LLMClient.call
    call_args = client.call.call_args
    prompt = call_args[0][0]  # First positional arg
    assert "My Important Document" in prompt
    assert "numbered_articles" in prompt


@pytest.mark.asyncio
async def test_prompt_includes_text_sample():
    """Prompt contains the text from chunks (Req 3.1)."""
    chunks = [_make_chunk("This is chunk content for testing.", order=0)]
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=chunks,
        organization_type=OrganizationType.FREE_FORM,
    )

    prompt = client.call.call_args[0][0]
    assert "This is chunk content for testing." in prompt


@pytest.mark.asyncio
async def test_text_sample_truncated_to_2000_chars():
    """Text sample is truncated to MAX_TEXT_SAMPLE_CHARS (2000) (Req 3.1)."""
    # Create chunks with text that totals well over 2000 chars
    long_text = "A" * 500  # Each chunk has 500 chars
    chunks = _make_chunks(10, text=long_text)  # 10 chunks * ~500 chars each > 2000

    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=chunks,
        organization_type=OrganizationType.FREE_FORM,
    )

    prompt = client.call.call_args[0][0]
    # The text sample section should not exceed 2000 chars
    # Extract the text between the markers
    start_marker = "--- BEGIN TEXT SAMPLE ---\n"
    end_marker = "\n--- END TEXT SAMPLE ---"
    start_idx = prompt.index(start_marker) + len(start_marker)
    end_idx = prompt.index(end_marker)
    text_sample = prompt[start_idx:end_idx]
    assert len(text_sample) <= MAX_TEXT_SAMPLE_CHARS


@pytest.mark.asyncio
async def test_only_first_10_chunks_used():
    """Only the first MAX_CHUNKS (10) chunks are used in the text sample (Decision 4)."""
    # Create 20 chunks, each with unique identifiable text
    chunks = [_make_chunk(f"UNIQUE_CHUNK_{i}_TEXT", order=i) for i in range(20)]

    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=chunks,
        organization_type=OrganizationType.FREE_FORM,
    )

    prompt = client.call.call_args[0][0]
    # First 10 chunks should be present
    for i in range(10):
        assert f"UNIQUE_CHUNK_{i}_TEXT" in prompt
    # Chunks beyond 10 should NOT be present
    for i in range(10, 20):
        assert f"UNIQUE_CHUNK_{i}_TEXT" not in prompt


# --- Tests: LLM Call Parameters ---


@pytest.mark.asyncio
async def test_call_uses_light_model_tier():
    """LLMClient.call is invoked with model_tier='light' (Req 3.1)."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    call_kwargs = client.call.call_args[1]
    assert call_kwargs["model_tier"] == "light"


@pytest.mark.asyncio
async def test_call_uses_temperature_01():
    """LLMClient.call is invoked with temperature=0.1 (Req 3.1)."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    call_kwargs = client.call.call_args[1]
    assert call_kwargs["temperature"] == 0.1


# --- Tests: PROMPT_VERSION ---


@pytest.mark.asyncio
async def test_prompt_version_included_in_result():
    """LLMAnalysisResult contains the current PROMPT_VERSION (Req 3.6)."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is not None
    assert result.prompt_version == "base-analysis-v2"


# --- Tests: Data Minimization (Req 3.7) ---


@pytest.mark.asyncio
async def test_prompt_contains_no_document_id():
    """Prompt does not contain document_id (Req 3.7 data minimization)."""
    chunks = [
        ContentChunkModel(
            chunk_id="doc-123-chunk-0",
            text="Some document text.",
            structural_context={"section": "Intro"},
            order=0,
        )
    ]
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=chunks,
        organization_type=OrganizationType.FREE_FORM,
    )

    prompt = client.call.call_args[0][0]
    # The prompt should not include the chunk_id which contains doc identifiers
    assert "doc-123-chunk-0" not in prompt


@pytest.mark.asyncio
async def test_prompt_contains_only_title_orgtype_and_text():
    """Prompt contains only title, organization_type, and text sample (Req 3.7)."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="My Title",
        chunks=_make_chunks(2, text="Doc content"),
        organization_type=OrganizationType.HIERARCHICAL_NUMBERING,
    )

    prompt = client.call.call_args[0][0]
    # Verify expected content is present
    assert "My Title" in prompt
    assert "hierarchical_numbering" in prompt
    assert "Doc content" in prompt


# --- Tests: Edge Cases ---


@pytest.mark.asyncio
async def test_analyze_with_empty_chunks():
    """Analyzer handles empty chunk list gracefully."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=[],
        organization_type=OrganizationType.FREE_FORM,
    )

    # Should still call LLM and return result (empty text sample is valid)
    assert result is not None
    client.call.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_with_json_wrapped_in_markdown_fences_returns_none():
    """JSON wrapped in markdown code fences is treated as invalid (Decision 5)."""
    content = '```json\n{"summary": "A summary.", "classification": "normative"}\n```'
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is None


# --- Tests: Language Confirmation (Req 7 criteria 3, 4) ---


@pytest.mark.asyncio
async def test_analyze_parses_language_confirmation():
    """LLM response with 'language' field is parsed into confirmed_language."""
    content = json.dumps({
        "summary": "A document about regulations.",
        "classification": "normative",
        "language": "es",
    })
    response = LLMResponse(content=content, model_id="groq/llama-3.3-70b-versatile")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
        language="es",
    )

    assert result is not None
    assert result.confirmed_language == "es"


@pytest.mark.asyncio
async def test_analyze_language_correction_different_from_detected():
    """LLM can correct the detected language to a different one."""
    content = json.dumps({
        "summary": "Um documento sobre regulamentos.",
        "classification": "normative",
        "language": "pt",
    })
    response = LLMResponse(content=content, model_id="groq/llama-3.3-70b-versatile")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
        language="es",  # System detected Spanish but document is Portuguese
    )

    assert result is not None
    assert result.confirmed_language == "pt"


@pytest.mark.asyncio
async def test_analyze_missing_language_field_gives_none():
    """When LLM response has no 'language' field, confirmed_language is None."""
    content = json.dumps({
        "summary": "A document.",
        "classification": "normative",
    })
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is not None
    assert result.confirmed_language is None


@pytest.mark.asyncio
async def test_analyze_invalid_language_code_ignored():
    """Invalid language code from LLM (too long, has digits) is ignored."""
    content = json.dumps({
        "summary": "A document.",
        "classification": "normative",
        "language": "spanish",  # Not a valid ISO 639-1 code
    })
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is not None
    assert result.confirmed_language is None


@pytest.mark.asyncio
async def test_analyze_language_code_normalized_lowercase():
    """Language code from LLM is normalized to lowercase."""
    content = json.dumps({
        "summary": "A document.",
        "classification": "normative",
        "language": "FR",
    })
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is not None
    assert result.confirmed_language == "fr"


@pytest.mark.asyncio
async def test_prompt_includes_detected_language():
    """Prompt includes the detected language for LLM to confirm/correct (Req 7 criterion 3)."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
        language="en",
    )

    prompt = client.call.call_args[0][0]
    assert "The system detected: en" in prompt


@pytest.mark.asyncio
async def test_prompt_includes_language_confirmation_instruction():
    """Prompt asks LLM to confirm or correct the language."""
    response = _make_valid_llm_response()
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    prompt = client.call.call_args[0][0]
    assert "confirm or correct the detected document language" in prompt
    assert "ISO 639-1" in prompt


@pytest.mark.asyncio
async def test_analyze_three_letter_language_code_accepted():
    """Three-letter ISO 639-2 codes are also accepted (e.g., 'por')."""
    content = json.dumps({
        "summary": "A document.",
        "classification": "normative",
        "language": "por",
    })
    response = LLMResponse(content=content, model_id="groq/test")
    client = _make_mock_llm_client(response)
    analyzer = LLMAnalyzer(client)

    result = await analyzer.analyze(
        title="Test",
        chunks=_make_chunks(1),
        organization_type=OrganizationType.FREE_FORM,
    )

    assert result is not None
    assert result.confirmed_language == "por"
