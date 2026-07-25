"""Integration tests for the quality analysis pipeline flow.

End-to-end tests exercising the full HTTP flow through the quality analysis API:
- POST /api/v1/documents/{id}/quality-analysis → trigger
- GET /api/v1/documents/{id}/quality-analysis → retrieve results
- Mock the LLMClient to return predictable JSON responses for each prompt type.
- Use a FakeQualityStorage (in-memory) to simulate database state transitions.

Requirements covered: 1–10 (all)
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.quality.ambiguity_detector import AmbiguityDetector
from app.analysis.quality.completeness_evaluator import CompletenessEvaluator
from app.analysis.quality.contradiction_detector import ContradictionDetector
from app.analysis.quality.finding_verifier import FindingVerifier
from app.analysis.quality.service import QualityAnalysisService
from app.analysis.quality.suggestion_generator import SuggestionGenerator
from app.analysis.service import AnalysisStorageService
from app.api.v1.quality import (
    _get_analysis_storage_service,
    _get_quality_analysis_service,
)
from app.main import create_app


# ---------------------------------------------------------------------------
# Fake LLM responses for each quality analysis type
# ---------------------------------------------------------------------------

FAKE_CONTRADICTION_RESPONSE = json.dumps(
    {
        "findings": [
            {
                "type": "contradiction",
                "description": "Section 3 says max latency is 100ms but Section 7 requires 500ms for the same API.",
                "severity": "high",
                "affected_element_ids": ["elem-001", "elem-002"],
                "source_refs": [
                    {
                        "chunk_id": "chunk-000",
                        "section": "## Performance",
                        "evidence": "All endpoints must respond within 100ms",
                    },
                    {
                        "chunk_id": "chunk-001",
                        "section": "## SLA",
                        "evidence": "SLA target is 500ms for standard endpoints",
                    },
                ],
            }
        ]
    }
)

FAKE_AMBIGUITY_RESPONSE = json.dumps(
    {
        "ambiguities": [
            {
                "id": "amb-001",
                "category": "vague_quantifier",
                "description": "The term 'quickly' is vague. It could mean <100ms or <1s depending on context.",
                "severity": "medium",
                "affected_element_ids": ["elem-001"],
                "source_ref": {
                    "chunk_id": "chunk-001",
                    "section": "## Performance",
                    "evidence": "The system should respond quickly to user requests",
                },
            }
        ]
    }
)

FAKE_COMPLETENESS_RESPONSE = json.dumps(
    {
        "assessments": [
            {
                "element_name": "criterios de éxito",
                "classification": "partial",
                "reasoning": "Success criteria are mentioned but lack specific KPIs.",
            }
        ]
    }
)

FAKE_SUGGESTION_RESPONSE = json.dumps(
    {
        "suggestions": [
            {
                "id": "sug-001",
                "description": "Define specific latency thresholds for each endpoint type.",
                "category": "consistency",
                "priority": "high",
                "related_finding_ids": ["contra-llm-00000001"],
                "source_refs": [
                    {
                        "chunk_id": "chunk-000",
                        "section": "## Performance",
                        "evidence": "All endpoints must respond within 100ms",
                    }
                ],
            },
            {
                "id": "sug-002",
                "description": "Replace 'quickly' with a measurable response time.",
                "category": "clarity",
                "priority": "medium",
                "related_finding_ids": ["amb-001"],
                "source_refs": [
                    {
                        "chunk_id": "chunk-001",
                        "section": "## Performance",
                        "evidence": "The system should respond quickly to user requests",
                    }
                ],
            },
        ]
    }
)


# ---------------------------------------------------------------------------
# Fake storage: in-memory quality analysis persistence
# ---------------------------------------------------------------------------


class FakeQualityStorage:
    """In-memory implementation of AnalysisStorageService for quality tests.

    Simulates database behavior with pre-populated completed KM sessions.
    """

    def __init__(self) -> None:
        self._documents: dict[str, dict] = {}
        self._chunks: dict[str, list[dict]] = {}
        self._sessions: dict[str, dict] = {}  # session_id -> session row
        self._doc_sessions: dict[str, str] = {}  # document_id -> session_id

    def add_document(
        self,
        document_id: str,
        *,
        status: str = "ready",
        original_filename: str = "test.md",
        doc_format: str = "markdown",
        size_bytes: int = 2048,
        language: str = "en",
    ) -> None:
        """Add a document record for testing."""
        self._documents[document_id] = {
            "document_id": document_id,
            "status": status,
            "original_filename": original_filename,
            "format": doc_format,
            "size_bytes": size_bytes,
            "language": language,
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "warnings": [],
        }

    def add_chunks(self, document_id: str, chunks: list[dict]) -> None:
        """Add IR chunks for a document."""
        self._chunks[document_id] = chunks

    def add_completed_session(
        self,
        document_id: str,
        knowledge_model: dict,
        confirmed_type: str = "prd",
    ) -> str:
        """Add a pre-completed analysis session (KM ready).

        Returns the session_id.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": session_id,
            "document_id": document_id,
            "status": "completed",
            "suggested_type": confirmed_type,
            "suggested_type_justification": "Test justification",
            "confirmed_type": confirmed_type,
            "knowledge_model": knowledge_model,
            "extraction_metadata": {
                "prompt_version": "extraction-v1",
                "model_id": "gemini/gemini-2.5-flash-preview-05-20",
                "temperature": 0.1,
                "element_count": len(knowledge_model.get("elements", [])),
                "relationship_count": 0,
                "verification_rate": 1.0,
                "extracted_at": now,
            },
            "error_message": None,
            "prompt_version": "extraction-v1",
            "model_id": "gemini/gemini-2.5-flash-preview-05-20",
            "quality_status": None,
            "quality_analysis": None,
            "quality_error_message": None,
            "quality_started_at": None,
            "quality_completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self._sessions[session_id] = row
        self._doc_sessions[document_id] = session_id
        return session_id

    def get_document(self, document_id: str) -> dict | None:
        return self._documents.get(document_id)

    def get_ir(self, document_id: str) -> list[dict] | None:
        chunks = self._chunks.get(document_id)
        if not chunks:
            return None
        return chunks

    def create_session(self, document_id: str) -> dict:
        """Not used for quality tests but satisfies the interface."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": session_id,
            "document_id": document_id,
            "status": "inferring_type",
            "created_at": now,
            "updated_at": now,
        }
        self._sessions[session_id] = row
        self._doc_sessions[document_id] = session_id
        return row

    def update_session(self, session_id: str, **fields) -> dict:
        row = self._sessions[session_id]
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        row.update(fields)
        return row

    def get_session_by_document(self, document_id: str) -> dict | None:
        session_id = self._doc_sessions.get(document_id)
        if session_id is None:
            return None
        return self._sessions.get(session_id)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

DEFAULT_CHUNKS = [
    {
        "document_id": "doc-001",
        "chunk_id": "chunk-000",
        "text": "All endpoints must respond within 100ms under standard load.",
        "structural_context": {"section": "## Performance"},
        "order": 0,
    },
    {
        "document_id": "doc-001",
        "chunk_id": "chunk-001",
        "text": "The system should respond quickly to user requests. SLA target is 500ms for standard endpoints.",
        "structural_context": {"section": "## SLA"},
        "order": 1,
    },
    {
        "document_id": "doc-001",
        "chunk_id": "chunk-002",
        "text": "Success criteria: user satisfaction above 90%. The platform processes documents in batch.",
        "structural_context": {"section": "## Success Criteria"},
        "order": 2,
    },
]

DEFAULT_KM = {
    "document_id": "doc-001",
    "document_type": "prd",
    "elements": [
        {
            "id": "elem-001",
            "type": "restriccion",
            "name": "Performance Constraint",
            "content": "All endpoints must respond within 100ms.",
            "source_ref": {
                "document_id": "doc-001",
                "chunk_id": "chunk-000",
                "page": None,
                "section": "## Performance",
                "evidence": "All endpoints must respond within 100ms",
            },
            "relations": [
                {
                    "target_id": "elem-002",
                    "type": "contradicts",
                    "description": "100ms contradicts the 500ms SLA target",
                }
            ],
            "verified": True,
        },
        {
            "id": "elem-002",
            "type": "restriccion",
            "name": "SLA Target",
            "content": "SLA target is 500ms for standard endpoints.",
            "source_ref": {
                "document_id": "doc-001",
                "chunk_id": "chunk-001",
                "page": None,
                "section": "## SLA",
                "evidence": "SLA target is 500ms for standard endpoints",
            },
            "relations": [
                {
                    "target_id": "elem-001",
                    "type": "contradicts",
                    "description": "500ms SLA contradicts 100ms performance constraint",
                }
            ],
            "verified": True,
        },
    ],
    "extraction_metadata": {
        "prompt_version": "extraction-v1",
        "model_id": "gemini/gemini-2.5-flash-preview-05-20",
        "temperature": 0.1,
        "element_count": 2,
        "relationship_count": 2,
        "verification_rate": 1.0,
        "extracted_at": "2025-07-01T12:00:00Z",
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_storage():
    """Create a FakeQualityStorage with a ready document and completed KM."""
    storage = FakeQualityStorage()
    storage.add_document("doc-001", status="ready")
    storage.add_chunks("doc-001", DEFAULT_CHUNKS)
    storage.add_completed_session("doc-001", DEFAULT_KM, confirmed_type="prd")
    return storage


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient that bypasses credential validation."""
    with patch.object(LLMClient, "__init__", lambda self: None):
        client = LLMClient()
        client.primary_model = "gemini/gemini-2.5-flash-preview-05-20"
        client.light_model = "groq/llama-3.3-70b-versatile"
        client.fallback_model = "groq/llama-3.3-70b-versatile"
        client._acompletion = AsyncMock()
        client._transient_error_types = ()
        client._auth_error_type = None
        client.call = AsyncMock()
        return client


@pytest.fixture
def quality_service(fake_storage, mock_llm_client):
    """Create a real QualityAnalysisService with mocked LLM and fake storage."""
    contradiction_detector = ContradictionDetector(llm_client=mock_llm_client)
    ambiguity_detector = AmbiguityDetector(llm_client=mock_llm_client)
    completeness_evaluator = CompletenessEvaluator(llm_client=mock_llm_client)
    suggestion_generator = SuggestionGenerator(llm_client=mock_llm_client)
    finding_verifier = FindingVerifier()

    return QualityAnalysisService(
        contradiction_detector=contradiction_detector,
        ambiguity_detector=ambiguity_detector,
        completeness_evaluator=completeness_evaluator,
        suggestion_generator=suggestion_generator,
        finding_verifier=finding_verifier,
        storage=fake_storage,
    )


@pytest.fixture
def app(quality_service, fake_storage):
    """Create a FastAPI app with quality analysis service wired in."""
    application = create_app()
    application.dependency_overrides[_get_quality_analysis_service] = (
        lambda: quality_service
    )
    application.dependency_overrides[_get_analysis_storage_service] = (
        lambda: fake_storage
    )
    return application


@pytest_asyncio.fixture
async def async_client(app):
    """Create an httpx AsyncClient for testing the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# End-to-end happy path: POST trigger → poll → retrieve results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestQualityAnalysisHappyPath:
    """Full flow: POST trigger → GET retrieve → verify structure."""

    async def test_full_flow_trigger_and_retrieve(
        self, app, fake_storage, mock_llm_client
    ):
        """E2E: completed KM → POST trigger → retrieve results → verify structure."""
        # Setup LLM mock to return responses for each pipeline step:
        # 1. Contradiction detection (LLM call)
        # 2. Ambiguity detection (LLM call)
        # 3. Completeness evaluation (LLM call for partial assessment)
        # 4. Suggestion generation (LLM call)
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_CONTRADICTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_AMBIGUITY_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_COMPLETENESS_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_SUGGESTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        # Step 1: Trigger quality analysis via POST (verifies HTTP layer)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["document_id"] == "doc-001"
        assert data["status"] == "analyzing"

        # The POST triggers a background task that will consume mock calls.
        # We need to let the background task complete. FastAPI's TestClient
        # with httpx may not automatically run background tasks, so we wait
        # a moment and then verify the result via GET.
        # Since background tasks may not run in test, we run the analysis
        # directly (the POST already validated the HTTP contract).
        # Reset the quality_status so run_analysis can proceed.
        session_id = fake_storage._doc_sessions["doc-001"]
        fake_storage._sessions[session_id]["quality_status"] = None
        fake_storage._sessions[session_id]["quality_analysis"] = None

        # Re-setup mock responses (POST background task may have consumed some)
        mock_llm_client.call.reset_mock()
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_CONTRADICTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_AMBIGUITY_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_COMPLETENESS_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_SUGGESTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        # Run analysis directly to simulate background task completion
        quality_svc = app.dependency_overrides[_get_quality_analysis_service]()
        await quality_svc.run_analysis("doc-001")

        # Step 2: GET should now return 200 with completed results
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 200
        data = resp.json()

        # Verify top-level structure
        assert data["document_id"] == "doc-001"
        assert data["status"] == "completed"
        assert "inconsistencies" in data
        assert "missing_elements" in data
        assert "suggestions" in data
        assert "metadata" in data

        # Verify inconsistencies contain both structural + LLM contradictions
        # and the ambiguity finding
        inconsistencies = data["inconsistencies"]
        assert len(inconsistencies) >= 2  # At least 1 structural + 1 LLM + 1 ambiguity

        # Check structural contradiction (from explicit relationship)
        structural = [i for i in inconsistencies if i.get("from_explicit_relationship")]
        assert len(structural) >= 1
        assert structural[0]["type"] == "contradiction"
        assert structural[0]["severity"] == "high"
        assert len(structural[0]["source_refs"]) >= 2
        assert len(structural[0]["affected_element_ids"]) >= 2

        # Check ambiguity finding
        ambiguities = [i for i in inconsistencies if i["type"] == "ambiguity"]
        assert len(ambiguities) >= 1
        assert ambiguities[0]["severity"] == "medium"
        assert len(ambiguities[0]["source_refs"]) >= 1

        # Verify suggestions structure
        suggestions = data["suggestions"]
        assert len(suggestions) >= 1
        for sug in suggestions:
            assert "id" in sug
            assert "description" in sug
            assert sug["category"] in ("structure", "clarity", "completeness", "consistency")
            assert sug["priority"] in ("high", "medium", "low")
            assert "source_refs" in sug

        # Verify metadata structure (Req 5.7)
        metadata = data["metadata"]
        assert "prompt_versions" in metadata
        assert "model_id" in metadata
        assert "temperature" in metadata
        assert "document_type" in metadata
        assert metadata["document_type"] == "prd"
        assert "started_at" in metadata
        assert "completed_at" in metadata
        assert "finding_counts" in metadata
        counts = metadata["finding_counts"]
        assert "contradictions" in counts
        assert "ambiguities" in counts
        assert "missing_elements" in counts
        assert "suggestions" in counts


# ---------------------------------------------------------------------------
# Error scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestErrorScenarios:
    """Tests for error conditions: 404, 409, 500."""

    async def test_document_not_found_post_returns_404(self, async_client):
        """POST for non-existent document returns 404."""
        resp = await async_client.post(
            "/api/v1/documents/nonexistent-doc/quality-analysis"
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "nonexistent-doc" in data["message"]

    async def test_document_not_found_get_returns_404(self, async_client):
        """GET for non-existent document returns 404."""
        resp = await async_client.get(
            "/api/v1/documents/nonexistent-doc/quality-analysis"
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "nonexistent-doc" in data["message"]

    async def test_km_not_completed_post_returns_409(
        self, app, fake_storage
    ):
        """POST when KM is not completed returns 409."""
        # Add a document with a session in "extracting" state
        fake_storage.add_document("doc-pending", status="ready")
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        fake_storage._sessions[session_id] = {
            "id": session_id,
            "document_id": "doc-pending",
            "status": "extracting",
            "quality_status": None,
            "created_at": now,
            "updated_at": now,
        }
        fake_storage._doc_sessions["doc-pending"] = session_id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/documents/doc-pending/quality-analysis"
            )

        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "km_not_completed"
        assert "extracting" in data["message"]

    async def test_km_not_completed_get_returns_409(
        self, app, fake_storage
    ):
        """GET when KM is not completed returns 409."""
        fake_storage.add_document("doc-pending", status="ready")
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        fake_storage._sessions[session_id] = {
            "id": session_id,
            "document_id": "doc-pending",
            "status": "extracting",
            "quality_status": None,
            "created_at": now,
            "updated_at": now,
        }
        fake_storage._doc_sessions["doc-pending"] = session_id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/documents/doc-pending/quality-analysis"
            )

        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "km_not_completed"

    async def test_analysis_in_progress_post_returns_409(
        self, app, fake_storage
    ):
        """POST when analysis is already in progress returns 409."""
        # Set quality_status to analyzing
        session_id = fake_storage._doc_sessions["doc-001"]
        fake_storage._sessions[session_id]["quality_status"] = "analyzing_contradictions"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "analysis_in_progress"
        assert "already running" in data["message"]

    async def test_analysis_failed_get_returns_500(
        self, app, fake_storage
    ):
        """GET when analysis has failed returns 500 with error details."""
        session_id = fake_storage._doc_sessions["doc-001"]
        fake_storage._sessions[session_id]["quality_status"] = "failed"
        fake_storage._sessions[session_id]["quality_error_message"] = (
            "LLM service unavailable during ambiguity detection"
        )
        fake_storage._sessions[session_id]["quality_analysis"] = {
            "error_phase": "analyzing_ambiguities",
            "status": "failed",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "analysis_failed"
        assert "LLM service unavailable" in data["message"]
        assert data["phase"] == "analyzing_ambiguities"


# ---------------------------------------------------------------------------
# Idempotent retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIdempotentRetrieval:
    """GET returns same results without re-triggering analysis (Req 5.8)."""

    async def test_get_returns_same_results_without_retrigger(
        self, app, fake_storage, mock_llm_client
    ):
        """Multiple GETs return identical JSON without calling LLM again."""
        # Setup LLM responses for the pipeline
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_CONTRADICTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_AMBIGUITY_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_COMPLETENESS_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_SUGGESTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        # Run analysis directly
        quality_svc = app.dependency_overrides[_get_quality_analysis_service]()
        await quality_svc.run_analysis("doc-001")

        # GET twice — should return identical results
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )
            resp2 = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()

        # LLM was called exactly 4 times (once per pipeline step, no re-trigger)
        assert mock_llm_client.call.call_count == 4


# ---------------------------------------------------------------------------
# Re-trigger after completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetriggerAfterCompletion:
    """POST after completed analysis resets and re-runs (Req 6.6)."""

    async def test_post_after_completion_resets_and_reruns(
        self, app, fake_storage, mock_llm_client
    ):
        """POST after completion returns 202 and allows re-analysis."""
        # First run: complete the analysis
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_CONTRADICTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_AMBIGUITY_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_COMPLETENESS_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_SUGGESTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        quality_svc = app.dependency_overrides[_get_quality_analysis_service]()
        await quality_svc.run_analysis("doc-001")

        # Verify it's completed
        session = fake_storage.get_session_by_document("doc-001")
        assert session["quality_status"] == "completed"

        # POST again to re-trigger — should return 202
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "analyzing"

        # Now re-run analysis (simulating background task)
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_CONTRADICTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_AMBIGUITY_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_COMPLETENESS_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_SUGGESTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        await quality_svc.run_analysis("doc-001")

        # GET should return fresh completed results
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Timeout behavior with slow mock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTimeoutBehavior:
    """Pipeline timeout marks analysis as failed (Req 6.7)."""

    async def test_slow_llm_triggers_timeout(
        self, app, fake_storage, mock_llm_client
    ):
        """When LLM takes too long, analysis is marked failed with timeout."""
        # Make the first LLM call slow (exceeds the pipeline timeout)
        async def slow_llm_call(*args, **kwargs):
            await asyncio.sleep(200)  # Way beyond the 120s timeout
            return LLMResponse(
                content=FAKE_CONTRADICTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            )

        mock_llm_client.call.side_effect = slow_llm_call

        quality_svc = app.dependency_overrides[_get_quality_analysis_service]()

        # Override the pipeline timeout to a small value for testing
        from app.analysis.quality import service as quality_service_module

        original_timeout = quality_service_module.PIPELINE_TIMEOUT_SECONDS
        quality_service_module.PIPELINE_TIMEOUT_SECONDS = 0.1  # 100ms for testing

        try:
            with pytest.raises(asyncio.TimeoutError):
                await quality_svc.run_analysis("doc-001")
        finally:
            quality_service_module.PIPELINE_TIMEOUT_SECONDS = original_timeout

        # Session should be marked as failed with timeout message
        session = fake_storage.get_session_by_document("doc-001")
        assert session["quality_status"] == "failed"
        assert "timed out" in session["quality_error_message"].lower()

        # GET should return 500
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "analysis_failed"
        assert "timed out" in data["message"].lower()


# ---------------------------------------------------------------------------
# In-progress polling: GET returns 202 with current phase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInProgressPolling:
    """GET during analysis returns 202 with current phase (Req 5.3)."""

    async def test_get_during_analysis_returns_202(self, app, fake_storage):
        """GET while quality_status is a phase returns 202."""
        phases = [
            "analyzing_contradictions",
            "analyzing_ambiguities",
            "analyzing_completeness",
            "generating_suggestions",
        ]

        session_id = fake_storage._doc_sessions["doc-001"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for phase in phases:
                fake_storage._sessions[session_id]["quality_status"] = phase

                resp = await client.get(
                    "/api/v1/documents/doc-001/quality-analysis"
                )

                assert resp.status_code == 202, f"Expected 202 for phase {phase}"
                data = resp.json()
                assert data["document_id"] == "doc-001"
                assert data["status"] == phase


# ---------------------------------------------------------------------------
# Response structure validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResponseStructure:
    """Validates response body structure matches the API contract."""

    async def test_completed_response_has_all_required_fields(
        self, app, fake_storage, mock_llm_client
    ):
        """Completed response includes all fields from the design doc."""
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_CONTRADICTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_AMBIGUITY_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_COMPLETENESS_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
            LLMResponse(
                content=FAKE_SUGGESTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        quality_svc = app.dependency_overrides[_get_quality_analysis_service]()
        await quality_svc.run_analysis("doc-001")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )

        assert resp.status_code == 200
        data = resp.json()

        # Top-level fields
        assert set(data.keys()) >= {
            "document_id",
            "status",
            "inconsistencies",
            "missing_elements",
            "suggestions",
            "metadata",
        }

        # Inconsistency fields
        for inc in data["inconsistencies"]:
            assert set(inc.keys()) >= {
                "id",
                "type",
                "description",
                "severity",
                "affected_element_ids",
                "source_refs",
                "involves_unverified_elements",
                "all_evidence_unverified",
                "from_explicit_relationship",
            }
            assert inc["type"] in ("contradiction", "ambiguity")
            assert inc["severity"] in ("high", "medium", "low")
            # Source refs structure
            for ref in inc["source_refs"]:
                assert "document_id" in ref
                assert "chunk_id" in ref
                assert "evidence" in ref
                assert "evidence_verified" in ref

        # Missing elements fields
        for me in data["missing_elements"]:
            assert set(me.keys()) >= {
                "id",
                "classification",
                "expected_element",
                "description",
                "severity",
                "schema_reference",
            }
            assert me["classification"] in ("missing", "partial")
            assert me["severity"] in ("high", "medium", "low")

        # Suggestion fields
        for sug in data["suggestions"]:
            assert set(sug.keys()) >= {
                "id",
                "description",
                "category",
                "priority",
                "related_finding_ids",
                "source_refs",
            }
            assert sug["category"] in (
                "structure", "clarity", "completeness", "consistency"
            )
            assert sug["priority"] in ("high", "medium", "low")

        # Metadata fields (Req 5.7)
        metadata = data["metadata"]
        assert set(metadata.keys()) >= {
            "prompt_versions",
            "model_id",
            "temperature",
            "document_type",
            "started_at",
            "completed_at",
            "finding_counts",
        }
        # Verify prompt_versions has all analysis types
        pv = metadata["prompt_versions"]
        assert "contradiction_detection" in pv
        assert "ambiguity_detection" in pv
        assert "completeness_evaluation" in pv
        assert "suggestion_generation" in pv

    async def test_error_response_format_consistency(
        self, app, fake_storage
    ):
        """All error responses follow {"error": "code", "message": "..."} format."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 404 error
            resp = await client.get(
                "/api/v1/documents/nonexistent/quality-analysis"
            )
            data = resp.json()
            assert "error" in data
            assert "message" in data
            assert isinstance(data["error"], str)
            assert isinstance(data["message"], str)

            # 409 error (KM not completed)
            fake_storage.add_document("doc-km-pending", status="ready")
            sid = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            fake_storage._sessions[sid] = {
                "id": sid,
                "document_id": "doc-km-pending",
                "status": "extracting",
                "quality_status": None,
                "created_at": now,
                "updated_at": now,
            }
            fake_storage._doc_sessions["doc-km-pending"] = sid

            resp = await client.post(
                "/api/v1/documents/doc-km-pending/quality-analysis"
            )
            data = resp.json()
            assert "error" in data
            assert "message" in data

            # 500 error (analysis failed)
            session_id = fake_storage._doc_sessions["doc-001"]
            fake_storage._sessions[session_id]["quality_status"] = "failed"
            fake_storage._sessions[session_id]["quality_error_message"] = "Test error"
            fake_storage._sessions[session_id]["quality_analysis"] = {
                "status": "failed",
                "error_phase": "analyzing_contradictions",
            }

            resp = await client.get(
                "/api/v1/documents/doc-001/quality-analysis"
            )
            data = resp.json()
            assert "error" in data
            assert "message" in data
