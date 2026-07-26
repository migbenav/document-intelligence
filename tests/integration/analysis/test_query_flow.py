"""Integration tests for the natural language query pipeline flow.

End-to-end tests exercising the full HTTP flow through the query API:
- POST /api/v1/documents/{id}/query → submit question → receive structured answer
- Mock the AnalysisService to provide controlled session/KM/IR data.
- Mock the QueryService to return controlled responses or raise errors.
- Test all status codes: 200, 404, 409, 422, 500.

Requirements covered: 5.1, 5.2, 5.3, 5.4, 5.5, 1.3
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.query.service import QueryError, QueryService
from app.analysis.service import AnalysisService
from app.api.v1.query import _get_analysis_service, _get_query_service
from app.main import create_app
from app.models.knowledge_model import AnalysisSession
from app.models.query import (
    QueryMetadata,
    QueryResponse,
    QuerySourceRef,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_analysis_service():
    """Create a mock AnalysisService with controllable session responses."""
    service = AsyncMock(spec=AnalysisService)
    return service


@pytest.fixture
def mock_query_service():
    """Create a mock QueryService with controllable answer responses."""
    service = AsyncMock(spec=QueryService)
    return service


@pytest.fixture
def app(mock_analysis_service, mock_query_service):
    """Create a FastAPI app with mocked query dependencies."""
    application = create_app()
    application.dependency_overrides[_get_analysis_service] = (
        lambda: mock_analysis_service
    )
    application.dependency_overrides[_get_query_service] = (
        lambda: mock_query_service
    )
    return application


@pytest_asyncio.fixture
async def async_client(app):
    """Create an httpx AsyncClient for testing the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Helper: completed session
# ---------------------------------------------------------------------------


def _make_completed_session(document_id: str = "doc-001") -> AnalysisSession:
    """Create a completed AnalysisSession for testing."""
    now = datetime.now(timezone.utc)
    return AnalysisSession(
        id="session-001",
        document_id=document_id,
        status="completed",
        suggested_type="prd",
        suggested_type_justification="Test justification",
        confirmed_type="prd",
        error_message=None,
        created_at=now,
        updated_at=now,
    )


def _make_extracting_session(document_id: str = "doc-001") -> AnalysisSession:
    """Create an AnalysisSession with status != completed."""
    now = datetime.now(timezone.utc)
    return AnalysisSession(
        id="session-001",
        document_id=document_id,
        status="extracting",
        suggested_type="prd",
        suggested_type_justification="Test justification",
        confirmed_type="prd",
        error_message=None,
        created_at=now,
        updated_at=now,
    )


def _make_query_response(document_id: str = "doc-001") -> QueryResponse:
    """Create a valid QueryResponse with verified evidence."""
    return QueryResponse(
        answer="The document describes three main actors: the System Administrator, the End User, and the API Consumer.",
        answerable=True,
        source_refs=[
            QuerySourceRef(
                document_id=document_id,
                chunk_id="chunk-005",
                page=None,
                section="## Actors and Roles",
                evidence="The System Administrator is responsible for infrastructure management",
                evidence_verified=True,
            ),
            QuerySourceRef(
                document_id=document_id,
                chunk_id="chunk-005",
                page=None,
                section="## Actors and Roles",
                evidence="End Users interact with the product through the web interface",
                evidence_verified=True,
            ),
        ],
        all_evidence_unverified=False,
        metadata=QueryMetadata(
            prompt_version="query-answering-v1",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
            temperature=0.1,
            timestamp=datetime.now(timezone.utc),
        ),
    )


def _make_cannot_answer_response() -> QueryResponse:
    """Create a cannot-answer QueryResponse."""
    return QueryResponse(
        answer="The available knowledge does not contain information relevant to this question.",
        answerable=False,
        source_refs=[],
        all_evidence_unverified=False,
        metadata=QueryMetadata(
            prompt_version="query-answering-v1",
            model_id="none",
            temperature=0.1,
            timestamp=datetime.now(timezone.utc),
        ),
    )


# ---------------------------------------------------------------------------
# Happy path: full query flow with verified evidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHappyPathQueryFlow:
    """Full flow: completed KM + valid question → 200 with QueryResponse."""

    async def test_full_query_returns_200_with_verified_evidence(
        self, async_client, mock_analysis_service, mock_query_service
    ):
        """E2E: document with completed KM → POST query → 200 with full response.

        Requirements: 5.1
        """
        # Setup: session is completed, KM and IR exist
        mock_analysis_service.get_session.return_value = _make_completed_session()
        mock_analysis_service.get_knowledge_model_object.return_value = MagicMock()
        mock_analysis_service.get_ir.return_value = MagicMock()

        expected_response = _make_query_response()
        mock_query_service.answer.return_value = expected_response

        # Act
        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": "What are the main actors in this document?"},
        )

        # Assert
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert data["answerable"] is True
        assert "actors" in data["answer"].lower() or "actor" in data["answer"].lower()
        assert len(data["source_refs"]) == 2
        assert data["all_evidence_unverified"] is False

        # Verify evidence references
        for ref in data["source_refs"]:
            assert ref["document_id"] == "doc-001"
            assert ref["chunk_id"] is not None
            assert ref["evidence"] is not None
            assert ref["evidence_verified"] is True

        # Verify metadata
        assert data["metadata"]["prompt_version"] == "query-answering-v1"
        assert data["metadata"]["model_id"] == "gemini/gemini-2.5-flash-preview-05-20"
        assert data["metadata"]["temperature"] == 0.1
        assert data["metadata"]["timestamp"] is not None

        # Verify QueryService was called with correct args
        mock_query_service.answer.assert_called_once()
        call_kwargs = mock_query_service.answer.call_args
        assert call_kwargs.kwargs["document_id"] == "doc-001"
        assert call_kwargs.kwargs["question"] == "What are the main actors in this document?"


# ---------------------------------------------------------------------------
# 404: Document not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDocumentNotFound:
    """Query for a non-existent document returns 404."""

    async def test_query_nonexistent_document_returns_404(
        self, async_client, mock_analysis_service
    ):
        """POST query for non-existent document returns 404 with 'not_found' error.

        Requirements: 5.3
        """
        mock_analysis_service.get_session.return_value = None

        resp = await async_client.post(
            "/api/v1/documents/nonexistent-doc/query",
            json={"question": "What is this about?"},
        )

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "nonexistent-doc" in data["message"]


# ---------------------------------------------------------------------------
# 409: Knowledge Model not completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestKMNotCompleted:
    """Query for a document without completed KM returns 409."""

    async def test_query_incomplete_km_returns_409(
        self, async_client, mock_analysis_service
    ):
        """POST query when KM status != 'completed' returns 409.

        Requirements: 5.2
        """
        mock_analysis_service.get_session.return_value = _make_extracting_session()

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": "What is this about?"},
        )

        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "km_not_completed"
        assert "extracting" in data["message"]


# ---------------------------------------------------------------------------
# 422: Invalid question length
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInvalidQuestionLength:
    """Query with invalid question length returns 422."""

    async def test_empty_question_returns_422(self, async_client):
        """POST query with empty question returns 422 validation error.

        Requirements: 5.4
        """
        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": ""},
        )

        assert resp.status_code == 422

    async def test_question_too_long_returns_422(self, async_client):
        """POST query with question > 1000 chars returns 422 validation error.

        Requirements: 5.4
        """
        long_question = "x" * 1001

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": long_question},
        )

        assert resp.status_code == 422

    async def test_question_at_max_length_succeeds(
        self, async_client, mock_analysis_service, mock_query_service
    ):
        """POST query with exactly 1000 chars passes validation.

        Requirements: 5.4
        """
        mock_analysis_service.get_session.return_value = _make_completed_session()
        mock_analysis_service.get_knowledge_model_object.return_value = MagicMock()
        mock_analysis_service.get_ir.return_value = MagicMock()
        mock_query_service.answer.return_value = _make_query_response()

        exact_length_question = "x" * 1000

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": exact_length_question},
        )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 500: Mocked LLM failure (QueryError)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestQueryFailure:
    """Query that fails due to LLM error returns 500."""

    async def test_llm_failure_returns_500_query_failed(
        self, async_client, mock_analysis_service, mock_query_service
    ):
        """POST query when LLM fails returns 500 with 'query_failed' error.

        Requirements: 5.5
        """
        mock_analysis_service.get_session.return_value = _make_completed_session()
        mock_analysis_service.get_knowledge_model_object.return_value = MagicMock()
        mock_analysis_service.get_ir.return_value = MagicMock()

        mock_query_service.answer.side_effect = QueryError(
            "LLM service unavailable"
        )

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": "What is this about?"},
        )

        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "query_failed"
        assert "message" in data
        # Should not expose internal stack traces
        assert "Traceback" not in data["message"]

    async def test_parse_failure_returns_500_with_parse_error_code(
        self, async_client, mock_analysis_service, mock_query_service
    ):
        """POST query when response parsing fails returns 500 with 'response_parse_error'.

        Requirements: 5.5
        """
        mock_analysis_service.get_session.return_value = _make_completed_session()
        mock_analysis_service.get_knowledge_model_object.return_value = MagicMock()
        mock_analysis_service.get_ir.return_value = MagicMock()

        mock_query_service.answer.side_effect = QueryError(
            "Failed to parse LLM response after retry: missing 'answer' field"
        )

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": "What is this about?"},
        )

        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "response_parse_error"
        assert "question" in data
        assert data["question"] == "What is this about?"


# ---------------------------------------------------------------------------
# Cannot-answer scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCannotAnswerScenario:
    """Query that cannot be answered returns 200 with answerable=False."""

    async def test_cannot_answer_returns_200_with_answerable_false(
        self, async_client, mock_analysis_service, mock_query_service
    ):
        """When context builder returns None (zero elements), answer is not answerable.

        Requirements: 1.3
        """
        mock_analysis_service.get_session.return_value = _make_completed_session()
        mock_analysis_service.get_knowledge_model_object.return_value = MagicMock()
        mock_analysis_service.get_ir.return_value = MagicMock()

        mock_query_service.answer.return_value = _make_cannot_answer_response()

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": "What are the deployment procedures?"},
        )

        assert resp.status_code == 200
        data = resp.json()

        assert data["answerable"] is False
        assert len(data["answer"]) > 0
        assert data["source_refs"] == []
        assert data["all_evidence_unverified"] is False
        assert data["metadata"]["prompt_version"] == "query-answering-v1"


# ---------------------------------------------------------------------------
# Edge case: KM or IR not found after session check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestKMOrIRNotFound:
    """When KM or IR is None after session check, returns 404."""

    async def test_km_none_returns_404(
        self, async_client, mock_analysis_service
    ):
        """POST query when KM object is None returns 404."""
        mock_analysis_service.get_session.return_value = _make_completed_session()
        mock_analysis_service.get_knowledge_model_object.return_value = None
        mock_analysis_service.get_ir.return_value = MagicMock()

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": "What is this about?"},
        )

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"

    async def test_ir_none_returns_404(
        self, async_client, mock_analysis_service
    ):
        """POST query when IR is None returns 404."""
        mock_analysis_service.get_session.return_value = _make_completed_session()
        mock_analysis_service.get_knowledge_model_object.return_value = MagicMock()
        mock_analysis_service.get_ir.return_value = None

        resp = await async_client.post(
            "/api/v1/documents/doc-001/query",
            json={"question": "What is this about?"},
        )

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
