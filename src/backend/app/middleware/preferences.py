"""Request preferences extraction from HTTP headers.

Provides a FastAPI dependency that parses user preference headers
(Accept-Language, X-Model-Preference, X-Auto-Fallback) and returns
a structured RequestPreferences object with validated defaults.
"""

from dataclasses import dataclass

from fastapi import Request


SUPPORTED_LANGUAGES = ("es", "en")
DEFAULT_LANGUAGE = "es"


@dataclass
class RequestPreferences:
    """User preferences extracted from HTTP request headers."""

    language: str  # 'es' | 'en' — from Accept-Language
    model_override: str | None  # None means use task-default assignment
    auto_fallback: bool  # from X-Auto-Fallback header


def get_request_preferences(request: Request) -> RequestPreferences:
    """FastAPI dependency that extracts user preferences from headers.

    Defaults: language='es', model_override=None, auto_fallback=True

    Header parsing rules:
    - Accept-Language: take first 2 chars, validate against supported languages.
    - X-Model-Preference: if 'default' or empty → None; otherwise use as-is.
    - X-Auto-Fallback: 'false' → False, anything else → True.
    """
    # Parse Accept-Language
    accept_language_raw = request.headers.get("accept-language", "")
    language_code = accept_language_raw[:2].lower() if accept_language_raw else ""
    language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    # Parse X-Model-Preference
    model_pref_raw = request.headers.get("x-model-preference", "")
    if not model_pref_raw or model_pref_raw.lower() == "default":
        model_override = None
    else:
        model_override = model_pref_raw

    # Parse X-Auto-Fallback
    auto_fallback_raw = request.headers.get("x-auto-fallback", "")
    auto_fallback = auto_fallback_raw.lower() != "false"

    return RequestPreferences(
        language=language,
        model_override=model_override,
        auto_fallback=auto_fallback,
    )
