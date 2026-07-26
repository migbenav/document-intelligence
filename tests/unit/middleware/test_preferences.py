"""Unit tests for the request preferences middleware.

Validates: Requirements 5 (criteria 2-5)
"""

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI, Depends

from app.middleware.preferences import (
    RequestPreferences,
    get_request_preferences,
)


@pytest.fixture
def app():
    """Create a minimal FastAPI app with an endpoint using the dependency."""
    _app = FastAPI()

    @_app.get("/test")
    def test_endpoint(prefs: RequestPreferences = Depends(get_request_preferences)):
        return {
            "language": prefs.language,
            "model_override": prefs.model_override,
            "auto_fallback": prefs.auto_fallback,
        }

    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAllHeadersPresent:
    """Test with all headers present → correct values."""

    def test_spanish_with_model_and_fallback_enabled(self, client):
        response = client.get(
            "/test",
            headers={
                "Accept-Language": "es",
                "X-Model-Preference": "gemini/gemini-2.5-flash",
                "X-Auto-Fallback": "true",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "es"
        assert data["model_override"] == "gemini/gemini-2.5-flash"
        assert data["auto_fallback"] is True

    def test_english_with_groq_model_and_fallback_disabled(self, client):
        response = client.get(
            "/test",
            headers={
                "Accept-Language": "en",
                "X-Model-Preference": "groq/llama-3.3-70b-versatile",
                "X-Auto-Fallback": "false",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"
        assert data["model_override"] == "groq/llama-3.3-70b-versatile"
        assert data["auto_fallback"] is False


class TestMissingHeaders:
    """Test with missing headers → defaults (es, None, True)."""

    def test_no_headers_returns_defaults(self, client):
        response = client.get("/test")
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "es"
        assert data["model_override"] is None
        assert data["auto_fallback"] is True


class TestInvalidLanguage:
    """Test with invalid language → falls back to 'es'."""

    def test_unsupported_language_code(self, client):
        response = client.get(
            "/test",
            headers={"Accept-Language": "fr"},
        )
        data = response.json()
        assert data["language"] == "es"

    def test_empty_accept_language(self, client):
        response = client.get(
            "/test",
            headers={"Accept-Language": ""},
        )
        data = response.json()
        assert data["language"] == "es"

    def test_gibberish_language(self, client):
        response = client.get(
            "/test",
            headers={"Accept-Language": "xyz"},
        )
        data = response.json()
        assert data["language"] == "es"

    def test_accept_language_with_quality_values(self, client):
        """Accept-Language with full format like 'en-US,en;q=0.9' should parse first 2 chars."""
        response = client.get(
            "/test",
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        data = response.json()
        assert data["language"] == "en"


class TestModelPreferenceDefault:
    """Test with X-Model-Preference: 'default' → model_override is None."""

    def test_default_string_returns_none(self, client):
        response = client.get(
            "/test",
            headers={"X-Model-Preference": "default"},
        )
        data = response.json()
        assert data["model_override"] is None

    def test_default_case_insensitive(self, client):
        response = client.get(
            "/test",
            headers={"X-Model-Preference": "Default"},
        )
        data = response.json()
        assert data["model_override"] is None

    def test_empty_model_preference_returns_none(self, client):
        response = client.get(
            "/test",
            headers={"X-Model-Preference": ""},
        )
        data = response.json()
        assert data["model_override"] is None


class TestAutoFallbackFalse:
    """Test with X-Auto-Fallback: 'false' → auto_fallback is False."""

    def test_false_string_returns_false(self, client):
        response = client.get(
            "/test",
            headers={"X-Auto-Fallback": "false"},
        )
        data = response.json()
        assert data["auto_fallback"] is False

    def test_true_string_returns_true(self, client):
        response = client.get(
            "/test",
            headers={"X-Auto-Fallback": "true"},
        )
        data = response.json()
        assert data["auto_fallback"] is True

    def test_empty_fallback_defaults_to_true(self, client):
        response = client.get(
            "/test",
            headers={"X-Auto-Fallback": ""},
        )
        data = response.json()
        assert data["auto_fallback"] is True
