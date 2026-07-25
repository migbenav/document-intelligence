"""Unit tests for the LLM abstraction layer.

Tests cover:
- Successful call routing (primary and light tiers)
- Transient error triggers fallback
- Credential/authentication error skips fallback
- Missing env vars raise ConfigurationError at init
- model_id tracking reflects actual model used (Property 9)

Requirements validated: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.llm_client import (
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_LIGHT_MODEL,
    DEFAULT_PRIMARY_MODEL,
    ConfigurationError,
    LLMAuthenticationError,
    LLMClient,
    LLMResponse,
    LLMTransientError,
)


# --- Custom exceptions simulating litellm errors for testing ---


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


# --- Fixtures ---


@pytest.fixture
def env_with_keys(monkeypatch):
    """Set up environment with valid API keys."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")


@pytest.fixture
def env_with_keys_and_models(monkeypatch, env_with_keys):
    """Set up environment with valid API keys and custom models."""
    monkeypatch.setenv("PRIMARY_MODEL", "gemini/custom-model")
    monkeypatch.setenv("LIGHT_MODEL", "groq/custom-light")
    monkeypatch.setenv("FALLBACK_MODEL", "groq/custom-fallback")


def _make_mock_response(content: str = "LLM response content") -> MagicMock:
    """Create a mock LiteLLM response object."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    return mock_response


@pytest.fixture
def client(env_with_keys) -> LLMClient:
    """Create an LLMClient with mocked litellm internals for unit testing."""
    with patch.object(LLMClient, "_setup_litellm"):
        client = LLMClient()

    # Set up the mock acompletion and error types
    client._acompletion = AsyncMock(return_value=_make_mock_response())
    client._transient_error_types = (
        FakeRateLimitError,
        FakeTimeout,
        FakeServiceUnavailableError,
    )
    client._auth_error_type = FakeAuthenticationError
    return client


# --- Initialization / Configuration Tests (Req 1.6) ---


class TestLLMClientInit:
    def test_missing_gemini_key_raises_configuration_error(self, monkeypatch):
        """Missing GEMINI_API_KEY raises ConfigurationError at init (Req 1.6)."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

        with patch.object(LLMClient, "_setup_litellm"):
            with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
                LLMClient()

    def test_missing_groq_key_raises_configuration_error(self, monkeypatch):
        """Missing GROQ_API_KEY raises ConfigurationError at init (Req 1.6)."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        with patch.object(LLMClient, "_setup_litellm"):
            with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
                LLMClient()

    def test_missing_both_keys_reports_both(self, monkeypatch):
        """All missing keys are reported in a single error (Req 1.6)."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        with patch.object(LLMClient, "_setup_litellm"):
            with pytest.raises(ConfigurationError) as exc_info:
                LLMClient()

        error_msg = str(exc_info.value)
        assert "GEMINI_API_KEY" in error_msg
        assert "GROQ_API_KEY" in error_msg

    def test_empty_string_key_treated_as_missing(self, monkeypatch):
        """Empty string API keys are treated as missing (Req 1.6)."""
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

        with patch.object(LLMClient, "_setup_litellm"):
            with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
                LLMClient()

    def test_valid_keys_initializes_successfully(self, env_with_keys):
        """Valid API keys allow successful initialization (Req 1.6)."""
        with patch.object(LLMClient, "_setup_litellm"):
            client = LLMClient()

        assert client.primary_model == DEFAULT_PRIMARY_MODEL
        assert client.light_model == DEFAULT_LIGHT_MODEL
        assert client.fallback_model == DEFAULT_FALLBACK_MODEL

    def test_custom_model_config_from_env(self, env_with_keys_and_models):
        """Custom model names from environment override defaults (Req 1.2)."""
        with patch.object(LLMClient, "_setup_litellm"):
            client = LLMClient()

        assert client.primary_model == "gemini/custom-model"
        assert client.light_model == "groq/custom-light"
        assert client.fallback_model == "groq/custom-fallback"


# --- Successful Call Tests (Req 1.1, 1.4, 1.5) ---


class TestLLMClientCall:
    @pytest.mark.asyncio
    async def test_primary_tier_routes_to_primary_model(self, client):
        """model_tier='primary' routes to PRIMARY_MODEL (Req 1.1)."""
        result = await client.call("test prompt", model_tier="primary")

        client._acompletion.assert_called_once_with(
            model=DEFAULT_PRIMARY_MODEL,
            messages=[{"role": "user", "content": "test prompt"}],
            temperature=0.1,
        )
        assert result.content == "LLM response content"
        assert result.model_id == DEFAULT_PRIMARY_MODEL

    @pytest.mark.asyncio
    async def test_light_tier_routes_to_light_model(self, client):
        """model_tier='light' routes to LIGHT_MODEL (Req 1.1, 1.2)."""
        result = await client.call("test prompt", model_tier="light")

        client._acompletion.assert_called_once_with(
            model=DEFAULT_LIGHT_MODEL,
            messages=[{"role": "user", "content": "test prompt"}],
            temperature=0.1,
        )
        assert result.content == "LLM response content"
        assert result.model_id == DEFAULT_LIGHT_MODEL

    @pytest.mark.asyncio
    async def test_default_temperature_is_0_1(self, client):
        """Default temperature is 0.1 for reproducibility (Req 1.4)."""
        await client.call("prompt")

        call_kwargs = client._acompletion.call_args
        assert call_kwargs.kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_custom_temperature(self, client):
        """Custom temperature is passed through (Req 1.4)."""
        await client.call("prompt", temperature=0.3)

        call_kwargs = client._acompletion.call_args
        assert call_kwargs.kwargs["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_model_id_tracks_actual_model_used(self, client):
        """model_id in response reflects the model that produced the result (Req 1.5)."""
        result = await client.call("prompt", model_tier="primary")
        assert result.model_id == DEFAULT_PRIMARY_MODEL

        client._acompletion.reset_mock()
        result = await client.call("prompt", model_tier="light")
        assert result.model_id == DEFAULT_LIGHT_MODEL


# --- Fallback Logic Tests (Req 1.3) ---


class TestLLMClientFallback:
    @pytest.mark.asyncio
    async def test_rate_limit_triggers_fallback(self, client):
        """RateLimitError on primary triggers fallback to FALLBACK_MODEL (Req 1.3)."""
        fallback_response = _make_mock_response("fallback response")
        client._acompletion.side_effect = [
            FakeRateLimitError("Rate limited"),
            fallback_response,
        ]

        result = await client.call("prompt", model_tier="primary")

        assert result.content == "fallback response"
        assert result.model_id == DEFAULT_FALLBACK_MODEL

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self, client):
        """Timeout on primary triggers fallback (Req 1.3)."""
        fallback_response = _make_mock_response("fallback response")
        client._acompletion.side_effect = [
            FakeTimeout("Request timed out"),
            fallback_response,
        ]

        result = await client.call("prompt", model_tier="primary")

        assert result.content == "fallback response"
        assert result.model_id == DEFAULT_FALLBACK_MODEL

    @pytest.mark.asyncio
    async def test_service_unavailable_triggers_fallback(self, client):
        """ServiceUnavailableError on primary triggers fallback (Req 1.3)."""
        fallback_response = _make_mock_response("fallback response")
        client._acompletion.side_effect = [
            FakeServiceUnavailableError("Service unavailable"),
            fallback_response,
        ]

        result = await client.call("prompt", model_tier="primary")

        assert result.content == "fallback response"
        assert result.model_id == DEFAULT_FALLBACK_MODEL

    @pytest.mark.asyncio
    async def test_fallback_model_id_reflects_actual_model(self, client):
        """When fallback succeeds, model_id is the fallback model (Property 9)."""
        fallback_response = _make_mock_response("from fallback")
        client._acompletion.side_effect = [
            FakeRateLimitError("Rate limited"),
            fallback_response,
        ]

        result = await client.call("prompt", model_tier="primary")

        # model_id must reflect the fallback, not the original target
        assert result.model_id == DEFAULT_FALLBACK_MODEL
        assert result.model_id != DEFAULT_PRIMARY_MODEL

    @pytest.mark.asyncio
    async def test_fallback_failure_raises_to_caller(self, client):
        """When both primary and fallback fail, error reaches caller for retry (Req 1.7)."""
        client._acompletion.side_effect = [
            FakeRateLimitError("Rate limited"),
            FakeServiceUnavailableError("Fallback also down"),
        ]

        with pytest.raises(LLMTransientError, match="Both primary.*and fallback.*failed"):
            await client.call("prompt", model_tier="primary")

    @pytest.mark.asyncio
    async def test_fallback_called_with_correct_model(self, client):
        """Fallback call uses FALLBACK_MODEL, not the original target (Req 1.3)."""
        fallback_response = _make_mock_response("fallback content")
        client._acompletion.side_effect = [
            FakeTimeout("Timed out"),
            fallback_response,
        ]

        await client.call("prompt", model_tier="primary", temperature=0.2)

        # Second call should be to fallback model
        assert client._acompletion.call_count == 2
        fallback_call = client._acompletion.call_args_list[1]
        assert fallback_call.kwargs["model"] == DEFAULT_FALLBACK_MODEL
        assert fallback_call.kwargs["temperature"] == 0.2


# --- Authentication Error Tests (Req 1.3) ---


class TestLLMClientAuthErrors:
    @pytest.mark.asyncio
    async def test_auth_error_skips_fallback(self, client):
        """AuthenticationError raises immediately without fallback attempt (Req 1.3)."""
        client._acompletion.side_effect = FakeAuthenticationError("Invalid API key")

        with pytest.raises(LLMAuthenticationError):
            await client.call("prompt", model_tier="primary")

        # acompletion should only be called once (no fallback attempt)
        client._acompletion.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_error_on_light_model_skips_fallback(self, client):
        """AuthenticationError on light model also raises immediately (Req 1.3)."""
        client._acompletion.side_effect = FakeAuthenticationError("Invalid API key")

        with pytest.raises(LLMAuthenticationError):
            await client.call("prompt", model_tier="light")

        client._acompletion.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_error_preserves_original_message(self, client):
        """AuthenticationError message is preserved in the raised exception (Req 1.3)."""
        client._acompletion.side_effect = FakeAuthenticationError(
            "Invalid API key for gemini"
        )

        with pytest.raises(LLMAuthenticationError, match="Invalid API key for gemini"):
            await client.call("prompt", model_tier="primary")
