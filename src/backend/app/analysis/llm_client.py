"""LLM abstraction layer wrapping LiteLLM.

Provides a centralized point of communication with LLM providers (Gemini, Groq)
with automatic fallback on transient errors, credential validation at startup,
and reproducibility tracking.

Requirements covered: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""

import logging
import os
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# Default model configuration (Decision 1 from design.md)
DEFAULT_PRIMARY_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_LIGHT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_FALLBACK_MODEL = "gemini/gemini-2.5-flash"


class ConfigurationError(Exception):
    """Raised when required LLM configuration is missing or invalid."""

    pass


class LLMTransientError(Exception):
    """Raised on transient LLM errors (rate limit, timeout, service unavailable)."""

    pass


class LLMAuthenticationError(Exception):
    """Raised on LLM authentication/credential errors."""

    pass


@dataclass
class LLMResponse:
    """Response from an LLM call with tracking metadata."""

    content: str
    model_id: str  # The model that actually produced the response (Req 1.5, Property 9)


class LLMClient:
    """Centralized LLM communication layer with fallback and config tracking.

    Constructor validates API keys at instantiation (Req 1.6).
    The `call` method routes to the correct model based on tier,
    handles transient error fallback (Req 1.3), and tracks which
    model actually produced the result (Req 1.5).
    """

    # Error types from litellm that are considered transient
    _transient_error_types: tuple = ()
    # Error type from litellm for authentication failures
    _auth_error_type: type | None = None

    def __init__(self) -> None:
        """Initialize the LLM client, reading config from environment variables.

        Raises:
            ConfigurationError: If required API keys are missing (Req 1.6).
        """
        # Read model configuration with defaults
        self.primary_model = os.environ.get("PRIMARY_MODEL", DEFAULT_PRIMARY_MODEL)
        self.light_model = os.environ.get("LIGHT_MODEL", DEFAULT_LIGHT_MODEL)
        self.fallback_model = os.environ.get("FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)

        # Validate required API keys at instantiation (Req 1.6)
        missing_keys: list[str] = []

        self._gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not self._gemini_api_key:
            missing_keys.append("GEMINI_API_KEY")

        self._groq_api_key = os.environ.get("GROQ_API_KEY")

        if missing_keys:
            raise ConfigurationError(
                f"Missing required LLM API keys: {', '.join(missing_keys)}. "
                "Set these environment variables before starting the application."
            )

        # Import and configure litellm (deferred to allow testing without litellm installed)
        self._setup_litellm()

    def _setup_litellm(self) -> None:
        """Import and configure litellm. Sets API keys and captures error types."""
        try:
            import litellm
            from litellm.exceptions import (
                AuthenticationError,
                RateLimitError,
                ServiceUnavailableError,
                Timeout,
            )

            litellm.gemini_key = self._gemini_api_key
            if self._groq_api_key:
                litellm.groq_key = self._groq_api_key

            self._transient_error_types = (RateLimitError, Timeout, ServiceUnavailableError)
            self._auth_error_type = AuthenticationError
            self._acompletion = litellm.acompletion
        except ImportError:
            # Allow instantiation without litellm for testing
            # Actual calls will fail if litellm is not available
            self._acompletion = None  # type: ignore

    async def call(
        self,
        prompt: str,
        *,
        model_tier: Literal["primary", "light"] = "primary",
        temperature: float = 0.1,
    ) -> LLMResponse:
        """Make an LLM call with automatic fallback on transient errors.

        Routes to the correct model based on model_tier:
        - "primary" -> PRIMARY_MODEL (Gemini)
        - "light" -> LIGHT_MODEL (Groq)

        On transient errors (rate limit, timeout, service unavailable),
        automatically falls back to FALLBACK_MODEL (Req 1.3).
        On authentication/credential errors, raises immediately without
        fallback attempt (Req 1.3).

        Args:
            prompt: The prompt text to send to the LLM.
            model_tier: Which model tier to use ("primary" or "light").
            temperature: Generation temperature (default 0.1 for reproducibility, Req 1.4).

        Returns:
            LLMResponse with the generated content and actual model_id used.

        Raises:
            LLMAuthenticationError: On credential errors (no fallback attempted).
            LLMTransientError: When both primary and fallback fail with transient errors.
            Exception: On non-transient, non-auth errors (Req 1.7).
        """
        if self._acompletion is None:
            raise RuntimeError(
                "litellm is not installed. Install it with: pip install litellm"
            )

        # Determine target model based on tier
        target_model = self.primary_model if model_tier == "primary" else self.light_model

        # Attempt primary call
        try:
            content = await self._make_call(target_model, prompt, temperature)
            logger.info(
                "LLM call successful",
                extra={"model_id": target_model, "model_tier": model_tier},
            )
            return LLMResponse(content=content, model_id=target_model)

        except BaseException as e:
            # Credential errors: raise immediately, no fallback (Req 1.3)
            if self._auth_error_type and isinstance(e, self._auth_error_type):
                logger.error(
                    "Authentication error — not attempting fallback",
                    extra={"model_id": target_model, "model_tier": model_tier},
                )
                raise LLMAuthenticationError(str(e)) from e

            # Transient errors: attempt fallback (Req 1.3)
            if self._transient_error_types and isinstance(e, self._transient_error_types):
                logger.warning(
                    "Transient error on primary model, attempting fallback",
                    extra={
                        "model_id": target_model,
                        "model_tier": model_tier,
                        "error_type": type(e).__name__,
                    },
                )

                try:
                    content = await self._make_call(
                        self.fallback_model, prompt, temperature
                    )
                    logger.info(
                        "Fallback call successful",
                        extra={
                            "model_id": self.fallback_model,
                            "original_model": target_model,
                        },
                    )
                    return LLMResponse(content=content, model_id=self.fallback_model)

                except BaseException as fallback_error:
                    # Both primary and fallback failed — raise to caller (Req 1.7)
                    logger.error(
                        "Fallback model also failed",
                        extra={
                            "fallback_model": self.fallback_model,
                            "fallback_error_type": type(fallback_error).__name__,
                        },
                    )
                    raise LLMTransientError(
                        f"Both primary ({target_model}) and fallback ({self.fallback_model}) failed. "
                        f"Last error: {fallback_error}"
                    ) from fallback_error

            # Non-transient, non-auth error: re-raise for caller (Req 1.7)
            raise

    async def _make_call(self, model: str, prompt: str, temperature: float) -> str:
        """Execute a single LLM call via LiteLLM acompletion.

        Args:
            model: The LiteLLM model identifier.
            prompt: The prompt text.
            temperature: Generation temperature.

        Returns:
            The text content from the LLM response.
        """
        response = await self._acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return response.choices[0].message.content
