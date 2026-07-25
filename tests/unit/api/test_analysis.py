"""Unit tests for the analysis API endpoints.

Tests the analyze, confirm-type, and knowledge-model endpoints
using a mocked AnalysisService dependency.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.analysis import _get_analysis_service
from app.analysis.service import (
    AnalysisAlreadyExistsError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    InvalidDocumentTypeError,
    InvalidSessionStateError,
)
from app.main import create_app
from app.models.knowledge_model import AnalysisSession


@pytest.fixture
def mock_analysis_service():
    """Create a mock AnalysisService."""
    return AsyncMock()


@pytest.fixture
def app(mock_analysis_service):
    """Create a test FastAPI app with mocked analysis dependency."""
    test_app = create_app()
    test_app.dependency_overrides[_get_analysis_service] = lambda: mock_analysis_service
    return test_app


def _make_session(**overrides) -> AnalysisSession:
    """Helper to create an AnalysisSession with defaults."""
    defaults = {
        "id": "session-001",
        "document_id": "doc-001",
        "status": "awaiting_confirmation",
        "suggested_type": "prd",
        "suggested_type_justification": "Contains requirements and user stories.",
        "confirmed_type": None,
        "error_message": None,
        "created_at": datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return AnalysisSession(**defaults)


# --- Analyze endpoint tests ---


@pytest.mark.asyncio
class TestAnalyzeEndpoint:
    """Tests for POST /api/v1/documents/{document_id}/analyze."""

    async def test_successful_analyze_returns_202(self, app, mock_analysis_service):
        """A valid analyze request returns 202 with session details."""
        mock_analysis_service.start_analysis.return_value = _make_session()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/documents/doc-001/analyze")

        assert response.status_code == 202
        data = response.json()
        assert data["session_id"] == "session-001"
        assert data["document_id"] == "doc-001"
        assert data["status"] == "awaiting_confirmation"
        assert data["suggested_type"] == "prd"
        assert data["suggested_type_justification"] == "Contains requirements and user stories."

    async def test_document_not_found_returns_404(self, app, mock_analysis_service):
        """Analyzing a non-existent document returns 404 (Req 9.2)."""
        mock_analysis_service.start_analysis.side_effect = DocumentNotFoundError(
            "Document 'nonexistent' not found."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/documents/nonexistent/analyze")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
        assert "nonexistent" in data["message"]

    async def test_document_not_ready_returns_409(self, app, mock_analysis_service):
        """Analyzing a document not in 'ready' status returns 409 (Req 9.1)."""
        mock_analysis_service.start_analysis.side_effect = DocumentNotReadyError(
            "Document is not ready for analysis."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/documents/doc-002/analyze")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "not_ready"
        assert "not ready" in data["message"]

    async def test_analysis_already_exists_returns_409(self, app, mock_analysis_service):
        """Analyzing a document that already has analysis returns 409 (Req 9.7)."""
        mock_analysis_service.start_analysis.side_effect = AnalysisAlreadyExistsError(
            "Analysis already exists for document 'doc-001'."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/documents/doc-001/analyze")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "analysis_exists"
        assert "already exists" in data["message"]


# --- Confirm-type endpoint tests ---


@pytest.mark.asyncio
class TestConfirmTypeEndpoint:
    """Tests for POST /api/v1/documents/{document_id}/confirm-type."""

    async def test_successful_confirm_returns_202(self, app, mock_analysis_service):
        """A valid confirm-type request returns 202 with updated session."""
        mock_analysis_service.confirm_and_extract.return_value = _make_session(
            status="extracting",
            confirmed_type="prd",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/confirm-type",
                json={"document_type": "prd"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["session_id"] == "session-001"
        assert data["document_id"] == "doc-001"
        assert data["status"] == "extracting"
        assert data["confirmed_type"] == "prd"

    async def test_confirm_with_technical_spec_returns_202(self, app, mock_analysis_service):
        """Confirming with a different valid type works."""
        mock_analysis_service.confirm_and_extract.return_value = _make_session(
            status="extracting",
            confirmed_type="technical_spec",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/confirm-type",
                json={"document_type": "technical_spec"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["confirmed_type"] == "technical_spec"

    async def test_invalid_type_returns_400(self, app, mock_analysis_service):
        """An invalid document type returns 400 with valid types list (Req 4.5)."""
        mock_analysis_service.confirm_and_extract.side_effect = InvalidDocumentTypeError(
            "invalid_type"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/confirm-type",
                json={"document_type": "invalid_type"},
            )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_document_type"
        assert "valid_types" in data
        assert sorted(data["valid_types"]) == ["generic", "policy_process", "prd", "technical_spec"]

    async def test_document_not_found_returns_404(self, app, mock_analysis_service):
        """Confirming type for non-existent document returns 404."""
        mock_analysis_service.confirm_and_extract.side_effect = DocumentNotFoundError(
            "No analysis session found for document 'nonexistent'."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/nonexistent/confirm-type",
                json={"document_type": "prd"},
            )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"

    async def test_invalid_session_state_returns_409(self, app, mock_analysis_service):
        """Confirming type when session is not in awaiting_confirmation returns 409 (Req 4.4)."""
        mock_analysis_service.confirm_and_extract.side_effect = InvalidSessionStateError(
            "Session is in 'completed' state. Expected 'awaiting_confirmation' to confirm type."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/confirm-type",
                json={"document_type": "prd"},
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "invalid_session_state"
        assert "completed" in data["message"]

    async def test_confirm_already_completed_returns_409(self, app, mock_analysis_service):
        """Confirming type after analysis is complete returns 409 (Req 4.4)."""
        mock_analysis_service.confirm_and_extract.side_effect = InvalidSessionStateError(
            "Session is in 'completed' state. Expected 'awaiting_confirmation' to confirm type."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/confirm-type",
                json={"document_type": "generic"},
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "invalid_session_state"


# --- Knowledge-model endpoint tests ---


@pytest.mark.asyncio
class TestKnowledgeModelEndpoint:
    """Tests for GET /api/v1/documents/{document_id}/knowledge-model."""

    async def test_completed_analysis_returns_200(self, app, mock_analysis_service):
        """A completed analysis returns 200 with the full KM (Req 9.4)."""
        mock_analysis_service.get_session.return_value = _make_session(
            status="completed",
            confirmed_type="prd",
        )
        mock_analysis_service.get_knowledge_model.return_value = {
            "document_id": "doc-001",
            "document_type": "prd",
            "elements": [
                {
                    "id": "elem-001",
                    "type": "proposito",
                    "name": "Purpose",
                    "content": "Build an intelligent document analysis platform.",
                    "source_ref": {
                        "document_id": "doc-001",
                        "chunk_id": "chunk-000",
                        "section": "# Purpose",
                        "evidence": "Build an intelligent document analysis platform",
                    },
                    "relations": [],
                    "verified": True,
                }
            ],
            "extraction_metadata": {
                "prompt_version": "extraction-v1",
                "model_id": "gemini/gemini-2.5-flash-preview-05-20",
                "temperature": 0.1,
                "element_count": 1,
                "relationship_count": 0,
                "verification_rate": 1.0,
                "extracted_at": "2025-07-01T12:00:00Z",
            },
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-001/knowledge-model")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc-001"
        assert data["document_type"] == "prd"
        assert len(data["elements"]) == 1
        assert data["elements"][0]["type"] == "proposito"
        assert data["extraction_metadata"]["prompt_version"] == "extraction-v1"
        assert data["extraction_metadata"]["verification_rate"] == 1.0

    async def test_no_session_returns_404(self, app, mock_analysis_service):
        """No analysis session for the document returns 404 (Req 9.6)."""
        mock_analysis_service.get_session.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/nonexistent/knowledge-model")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
        assert "nonexistent" in data["message"]

    async def test_analysis_not_completed_returns_409(self, app, mock_analysis_service):
        """Analysis in progress returns 409 (Req 9.5)."""
        mock_analysis_service.get_session.return_value = _make_session(
            status="extracting",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-001/knowledge-model")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "not_completed"
        assert "extracting" in data["message"]

    async def test_awaiting_confirmation_returns_409(self, app, mock_analysis_service):
        """Analysis in awaiting_confirmation state returns 409 (Req 9.5)."""
        mock_analysis_service.get_session.return_value = _make_session(
            status="awaiting_confirmation",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-001/knowledge-model")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "not_completed"
        assert "awaiting_confirmation" in data["message"]

    async def test_failed_analysis_returns_409(self, app, mock_analysis_service):
        """Failed analysis returns 409 (not completed) (Req 9.5)."""
        mock_analysis_service.get_session.return_value = _make_session(
            status="failed",
            error_message="Type inference failed.",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-001/knowledge-model")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "not_completed"
        assert "failed" in data["message"]

    async def test_completed_but_km_none_returns_404(self, app, mock_analysis_service):
        """Edge case: session shows completed but KM is None (data inconsistency)."""
        mock_analysis_service.get_session.return_value = _make_session(
            status="completed",
        )
        mock_analysis_service.get_knowledge_model.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-001/knowledge-model")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
