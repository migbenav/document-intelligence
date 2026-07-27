"""Unit tests for LLM error classification — quota vs transient errors.

Tests cover:
- RateLimitError with "429" raises LLMQuotaExhaustedError
- Quota error does NOT trigger fallback
- Other transient errors still trigger fallback
- LLMQuotaExhaustedError carries model_id attribute

Requirements validated: Req 5 (criteria 2, 6)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.llm_client import (
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_PRIMARY_MODEL,
    LLMClient,
    LLMQuotaExhaustedError,
    LLMTransientError,
)


# --- Fake exceptions simulating litellm errors ---


class FakeRateLimitError(Exception):
    """Simulates litellm.exceptions.RateLimitError."""

    pass


class FakeTimeout(Exception):
    """Simulates litellm.exceptions.Timeout."""

    pass


class FakeServiceUnavailableError(Exception):
    """Simulates litellm.exceptions.ServiceUnavailableError."""

    pass


class FakeAuthenticationError(Exception):
    """Simulates litellm.exceptions.AuthenticationError."""

    pass


# --- Helpers ---


def _make_mock_response(content: str = "LLM response content") -> MagicMock:
    """Create a mock LiteLLM response object."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    return mock_response


# --- Fixtures ---


@pytest.fixture
def env_with_keys(monkeypatch):
    """Set up environment with valid API keys."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")


@pytest.fixture
def client(env_with_keys) -> LLMClient:
    """Create an LLMClient with mocked litellm internals for unit testing."""
    with patch.object(LLMClient, "_setup_litellm"):
        c = LLMClient()

    # Set up the mock acompletion and error types
    c._acompletion = AsyncMock(return_value=_make_mock_response())
    c._transient_error_types = (
        FakeRateLimitError,
        FakeTimeout,
        FakeServiceUnavailableError,
    )
    c._auth_error_type = FakeAuthenticationError
    return c


# --- Quota Error Classification Tests (Req 5, criterion 2) ---


class TestQuotaErrorClassification:
    """Tests that RateLimitError / 429 errors are classified as quota errors."""

    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_quota_exhausted(self, client):
        """RateLimitError raises LLMQuotaExhaustedError (Req 5 criterion 2).

        When the LLM returns a RateLimitError (which is also a transient error type),
        it must be classified as a quota error and raise LLMQuotaExhaustedError,
        NOT trigger fallback.
        """
        # Patch _is_quota_error to return True for FakeRateLimitError
        # (in production, this checks isinstance(error, RateLimitError))
        original_is_quota = client._is_quota_error
        client._is_quota_error = lambda e: isinstance(e, FakeRateLimitError)

        client._acompletion.side_effect = FakeRateLimitError("429 Rate limit exceeded")

        with pytest.raises(LLMQuotaExhaustedError) as exc_info:
            await client.call("test prompt", model_tier="primary")

        assert exc_info.value.model_id == DEFAULT_PRIMARY_MODEL
        assert "Quota exhausted" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_quota_error_with_429_in_message(self, client):
        """Error message containing '429' triggers quota classification."""
        # Use a generic exception with "429" in message
        error = Exception("HTTP 429 Too Many Requests - quota exceeded")
        assert client._is_quota_error(error) is True

    @pytest.mark.asyncio
    async def test_quota_error_with_quota_in_message(self, client):
        """Error message containing 'quota' triggers quota classification."""
        error = Exception("Resource quota has been exhausted for this project")
        assert client._is_quota_error(error) is True

    @pytest.mark.asyncio
    async def test_quota_error_with_rate_limit_in_message(self, client):
        """Error message containing 'rate_limit' triggers quota classification."""
        error = Exception("rate_limit: too many requests per minute")
        assert client._is_quota_error(error) is True

    @pytest.mark.asyncio
    async def test_non_quota_error_not_classified(self, client):
        """Normal errors without quota keywords are NOT classified as quota."""
        error = Exception("Internal server error")
        assert client._is_quota_error(error) is False

    @pytest.mark.asyncio
    async def test_quota_error_carries_model_id(self, client):
        """LLMQuotaExhaustedError carries the model_id that hit quota (Req 5 criterion 6)."""
        client._is_quota_error = lambda e: isinstance(e, FakeRateLimitError)
        client._acompletion.side_effect = FakeRateLimitError("quota exhausted")

        with pytest.raises(LLMQuotaExhaustedError) as exc_info:
            await client.call(
                "prompt", model_override="gemini/gemini-2.5-flash"
            )

        assert exc_info.value.model_id == "gemini/gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_quota_error_with_model_override(self, client):
        """Quota error on overridden model reports that model in the exception."""
        client._is_quota_error = lambda e: isinstance(e, FakeRateLimitError)
        client._acompletion.side_effect = FakeRateLimitError("429")

        with pytest.raises(LLMQuotaExhaustedError) as exc_info:
            await client.call(
                "prompt", model_override="groq/llama-3.3-70b-versatile"
            )

        assert exc_info.value.model_id == "groq/llama-3.3-70b-versatile"


# --- Quota Error Does NOT Trigger Fallback (Req 5, criterion 2) ---


class TestQuotaErrorNoFallback:
    """Tests that quota errors do NOT trigger the fallback mechanism."""

    @pytest.mark.asyncio
    async def test_quota_error_does_not_trigger_fallback(self, client):
        """LLMQuotaExhaustedError is raised immediately, no fallback attempted (Req 5 criterion 2).

        This is the key behavioral distinction: quota errors mean "user should switch models",
        not "try another model automatically." Only one call should be made.
        """
        client._is_quota_error = lambda e: isinstance(e, FakeRateLimitError)
        client._acompletion.side_effect = FakeRateLimitError("429 quota limit")

        with pytest.raises(LLMQuotaExhaustedError):
            await client.call("prompt", model_tier="primary", auto_fallback=True)

        # Only ONE call made — no fallback attempt
        client._acompletion.assert_called_once()

    @pytest.mark.asyncio
    async def test_quota_error_no_fallback_even_with_auto_fallback_true(self, client):
        """Quota error does not fallback even when auto_fallback=True."""
        client._is_quota_error = lambda e: isinstance(e, FakeRateLimitError)
        fallback_response = _make_mock_response("should not reach this")
        client._acompletion.side_effect = [
            FakeRateLimitError("Rate limit 429"),
            fallback_response,
        ]

        with pytest.raises(LLMQuotaExhaustedError):
            await client.call("prompt", model_tier="primary", auto_fallback=True)

        # Only primary call made, fallback never reached
        assert client._acompletion.call_count == 1


# --- Other Transient Errors Still Trigger Fallback ---


class TestTransientErrorsFallback:
    """Tests that non-quota transient errors still trigger fallback normally."""

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self, client):
        """Timeout (non-quota transient) triggers fallback as usual."""
        fallback_response = _make_mock_response("fallback succeeded")
        client._acompletion.side_effect = [
            FakeTimeout("Request timed out"),
            fallback_response,
        ]

        result = await client.call("prompt", model_tier="primary")

        assert result.content == "fallback succeeded"
        assert result.model_id == DEFAULT_FALLBACK_MODEL
        assert client._acompletion.call_count == 2

    @pytest.mark.asyncio
    async def test_service_unavailable_triggers_fallback(self, client):
        """ServiceUnavailableError (non-quota transient) triggers fallback."""
        fallback_response = _make_mock_response("fallback response")
        client._acompletion.side_effect = [
            FakeServiceUnavailableError("Service down"),
            fallback_response,
        ]

        result = await client.call("prompt", model_tier="primary")

        assert result.content == "fallback response"
        assert result.model_id == DEFAULT_FALLBACK_MODEL
        assert client._acompletion.call_count == 2

    @pytest.mark.asyncio
    async def test_transient_error_does_not_raise_quota_error(self, client):
        """Non-rate-limit transient errors are NOT classified as quota errors."""
        # Timeout with no quota-related keywords should NOT be a quota error
        error = FakeTimeout("Request timed out after 60s")
        assert client._is_quota_error(error) is False

    @pytest.mark.asyncio
    async def test_service_unavailable_not_classified_as_quota(self, client):
        """ServiceUnavailableError is NOT classified as a quota error."""
        error = FakeServiceUnavailableError("503 Service Unavailable")
        assert client._is_quota_error(error) is False


# --- _is_quota_error method edge cases ---


class TestIsQuotaErrorMethod:
    """Tests for the _is_quota_error classification method."""

    def test_is_quota_error_case_insensitive(self, client):
        """Keyword matching is case-insensitive."""
        error = Exception("HTTP 429 RATE LIMIT EXCEEDED")
        assert client._is_quota_error(error) is True

    def test_is_quota_error_quota_keyword(self, client):
        """'quota' keyword in any position triggers detection."""
        error = Exception("User quota has been exceeded")
        assert client._is_quota_error(error) is True

    def test_is_quota_error_no_match(self, client):
        """Unrelated error message is not classified as quota."""
        error = Exception("Connection refused to model endpoint")
        assert client._is_quota_error(error) is False

    def test_is_quota_error_empty_message(self, client):
        """Empty error message is not classified as quota."""
        error = Exception("")
        assert client._is_quota_error(error) is False
