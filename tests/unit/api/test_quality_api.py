"""Unit tests for the quality analysis API endpoints.

Tests the POST and GET quality-analysis endpoints using mocked
QualityAnalysisService and AnalysisStorageService dependencies.

Requirements covered: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.quality import (
    _get_analysis_storage_service,
    _get_quality_analysis_service,
)
from app.main import create_app
from app.models.quality_analysis import (
    FindingSourceRef,
    Inconsistency,
    MissingElement,
    QualityAnalysisMetadata,
    QualityAnalysisResult,
    Suggestion,
)


# --- Fixtures ---


@pytest.fixture
def mock_quality_service():
    """Create a mock QualityAnalysisService."""
    return AsyncMock()


@pytest.fixture
def mock_storage():
    """Create a mock AnalysisStorageService."""
    return MagicMock()


@pytest.fixture
def app(mock_quality_service, mock_storage):
    """Create a test FastAPI app with mocked quality dependencies."""
    test_app = create_app()
    test_app.dependency_overrides[_get_quality_analysis_service] = (
        lambda: mock_quality_service
    )
    test_app.dependency_overrides[_get_analysis_storage_service] = (
        lambda: mock_storage
    )
    return test_app


def _make_completed_session(**overrides) -> dict:
    """Helper to create a completed analysis session dict."""
    defaults = {
        "id": "session-001",
        "document_id": "doc-001",
        "status": "completed",
        "suggested_type": "prd",
        "confirmed_type": "prd",
        "quality_status": None,
        "quality_analysis": None,
        "quality_error_message": None,
        "quality_started_at": None,
        "quality_completed_at": None,
        "knowledge_model": {"elements": []},
        "created_at": datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "updated_at": datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
    }
    defaults.update(overrides)
    return defaults


def _make_quality_result() -> QualityAnalysisResult:
    """Helper to create a full QualityAnalysisResult for testing."""
    return QualityAnalysisResult(
        document_id="doc-001",
        status="completed",
        inconsistencies=[
            Inconsistency(
                id="inc-001",
                type="contradiction",
                description="Section A contradicts Section B on response time.",
                severity="high",
                affected_element_ids=["elem-001", "elem-002"],
                source_refs=[
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        section="## Performance",
                        evidence="Response time must be under 200ms",
                        evidence_verified=True,
                    ),
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-003",
                        section="## SLA",
                        evidence="Response time SLA is 500ms",
                        evidence_verified=True,
                    ),
                ],
                from_explicit_relationship=True,
            ),
        ],
        missing_elements=[
            MissingElement(
                id="miss-001",
                classification="missing",
                expected_element="criterios de éxito",
                description="PRD should define measurable success criteria.",
                severity="medium",
                schema_reference="prd",
            ),
        ],
        suggestions=[
            Suggestion(
                id="sug-001",
                description="Add a section defining measurable success criteria.",
                category="completeness",
                priority="medium",
                related_finding_ids=["miss-001"],
                source_refs=[
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        section="## Introduction",
                        evidence="This document defines the product requirements",
                        evidence_verified=True,
                    ),
                ],
            ),
        ],
        metadata=QualityAnalysisMetadata(
            prompt_versions={
                "contradiction_detection": "contradiction-v1",
                "ambiguity_detection": "ambiguity-v1",
                "completeness_evaluation": "completeness-v1",
                "suggestion_generation": "suggestion-v1",
            },
            model_id="gemini/gemini-2.5-flash-preview-05-20",
            temperature=0.1,
            document_type="prd",
            started_at=datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2025, 7, 1, 12, 1, 15, tzinfo=timezone.utc),
            finding_counts={
                "contradictions": 1,
                "ambiguities": 0,
                "missing_elements": 1,
                "suggestions": 1,
            },
        ),
    )


# --- POST /quality-analysis endpoint tests ---


@pytest.mark.asyncio
class TestTriggerQualityAnalysis:
    """Tests for POST /api/v1/documents/{document_id}/quality-analysis."""

    async def test_successful_trigger_returns_202(self, app, mock_storage):
        """A valid POST request triggers analysis and returns 202 (Req 5.2)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["document_id"] == "doc-001"
        assert data["status"] == "analyzing"

    async def test_document_not_found_returns_404(self, app, mock_storage):
        """POST for non-existent document returns 404 (Req 5.5)."""
        mock_storage.get_document.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/nonexistent/quality-analysis"
            )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
        assert "nonexistent" in data["message"]

    async def test_km_not_completed_returns_409(self, app, mock_storage):
        """POST when KM is not completed returns 409 (Req 5.4)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = {
            "id": "session-001",
            "document_id": "doc-001",
            "status": "extracting",
            "quality_status": None,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "km_not_completed"
        assert "extracting" in data["message"]

    async def test_no_session_returns_409(self, app, mock_storage):
        """POST when no analysis session exists returns 409."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "km_not_completed"

    async def test_analysis_in_progress_returns_409(self, app, mock_storage):
        """POST when analysis is already running returns 409."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="analyzing",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "analysis_in_progress"
        assert "already running" in data["message"]

    async def test_analysis_in_phase_returns_409(self, app, mock_storage):
        """POST when analysis is in a specific phase returns 409."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="analyzing_contradictions",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "analysis_in_progress"

    async def test_retrigger_after_completion_returns_202(self, app, mock_storage):
        """POST after previous analysis completed allows re-trigger (Req 6.6)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="completed",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["document_id"] == "doc-001"
        assert data["status"] == "analyzing"

    async def test_retrigger_after_failure_returns_202(self, app, mock_storage):
        """POST after failed analysis allows re-trigger (Req 6.6)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="failed",
            quality_error_message="Timeout",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "analyzing"


# --- GET /quality-analysis endpoint tests ---


@pytest.mark.asyncio
class TestGetQualityAnalysis:
    """Tests for GET /api/v1/documents/{document_id}/quality-analysis."""

    async def test_completed_returns_200_with_full_results(
        self, app, mock_storage, mock_quality_service
    ):
        """GET for completed analysis returns 200 with results (Req 5.1, 5.7, 5.8)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="completed",
        )
        mock_quality_service.get_results.return_value = _make_quality_result()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc-001"
        assert data["status"] == "completed"
        assert len(data["inconsistencies"]) == 1
        assert data["inconsistencies"][0]["type"] == "contradiction"
        assert data["inconsistencies"][0]["severity"] == "high"
        assert len(data["inconsistencies"][0]["source_refs"]) == 2
        assert len(data["missing_elements"]) == 1
        assert data["missing_elements"][0]["classification"] == "missing"
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["category"] == "completeness"
        # Metadata (Req 5.7)
        assert data["metadata"] is not None
        assert "prompt_versions" in data["metadata"]
        assert "model_id" in data["metadata"]
        assert "started_at" in data["metadata"]
        assert "completed_at" in data["metadata"]
        assert "finding_counts" in data["metadata"]
        assert data["metadata"]["document_type"] == "prd"

    async def test_document_not_found_returns_404(self, app, mock_storage):
        """GET for non-existent document returns 404 (Req 5.5)."""
        mock_storage.get_document.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/nonexistent/quality-analysis"
            )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
        assert "nonexistent" in data["message"]

    async def test_no_session_returns_404(self, app, mock_storage):
        """GET when no analysis session exists returns 404."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"

    async def test_km_not_completed_returns_409(self, app, mock_storage):
        """GET when KM is not completed returns 409 (Req 5.4)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = {
            "id": "session-001",
            "document_id": "doc-001",
            "status": "extracting",
            "quality_status": None,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "km_not_completed"
        assert "extracting" in data["message"]

    async def test_not_triggered_returns_404(self, app, mock_storage):
        """GET when analysis has not been triggered returns 404."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status=None,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
        assert "not been triggered" in data["message"]

    async def test_in_progress_analyzing_returns_202(self, app, mock_storage):
        """GET when analysis is in progress returns 202 with status (Req 5.3)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="analyzing_contradictions",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["document_id"] == "doc-001"
        assert data["status"] == "analyzing_contradictions"

    async def test_in_progress_ambiguities_returns_202(self, app, mock_storage):
        """GET when analysis is in ambiguity phase returns 202 (Req 5.3)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="analyzing_ambiguities",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "analyzing_ambiguities"

    async def test_in_progress_completeness_returns_202(self, app, mock_storage):
        """GET when analysis is in completeness phase returns 202."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="analyzing_completeness",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "analyzing_completeness"

    async def test_in_progress_suggestions_returns_202(self, app, mock_storage):
        """GET when analysis is generating suggestions returns 202."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="generating_suggestions",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "generating_suggestions"

    async def test_failed_returns_500_with_error_details(self, app, mock_storage):
        """GET when analysis failed returns 500 with error info (Req 5.6)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="failed",
            quality_error_message="LLM service unavailable",
            quality_analysis={
                "error_phase": "analyzing_ambiguities",
                "status": "failed",
            },
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "analysis_failed"
        assert "LLM service unavailable" in data["message"]
        assert data["phase"] == "analyzing_ambiguities"

    async def test_failed_without_phase_returns_500(self, app, mock_storage):
        """GET when analysis failed without phase info still returns 500."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="failed",
            quality_error_message="Timeout after 120 seconds",
            quality_analysis=None,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "analysis_failed"
        assert "Timeout" in data["message"]
        assert "phase" not in data

    async def test_completed_but_results_none_returns_500(
        self, app, mock_storage, mock_quality_service
    ):
        """GET when marked completed but results are missing returns 500."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="completed",
        )
        mock_quality_service.get_results.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "analysis_failed"
        assert "results not found" in data["message"]

    async def test_idempotent_retrieval(self, app, mock_storage, mock_quality_service):
        """GET returns same results without re-triggering (Req 5.8)."""
        mock_storage.get_document.return_value = {"document_id": "doc-001", "status": "ready"}
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="completed",
        )
        result = _make_quality_result()
        mock_quality_service.get_results.return_value = result

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response1 = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )
            response2 = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json() == response2.json()
        # get_results was called twice (no re-trigger)
        assert mock_quality_service.get_results.call_count == 2
        # run_analysis was never called
        mock_quality_service.run_analysis.assert_not_called()


# --- Error response format consistency tests ---


@pytest.mark.asyncio
class TestErrorResponseFormat:
    """Tests verifying error response format consistency."""

    async def test_all_error_responses_have_error_and_message(self, app, mock_storage):
        """All error responses follow the {"error": "code", "message": "..."} format."""
        mock_storage.get_document.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test 404 on POST
            response = await client.post(
                "/api/v1/documents/missing/quality-analysis"
            )
            data = response.json()
            assert "error" in data
            assert "message" in data
            assert isinstance(data["error"], str)
            assert isinstance(data["message"], str)

            # Test 404 on GET
            response = await client.get(
                "/api/v1/documents/missing/quality-analysis"
            )
            data = response.json()
            assert "error" in data
            assert "message" in data
