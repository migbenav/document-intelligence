"""Integration tests for the analysis pipeline flow.

End-to-end tests exercising the full HTTP flow through the analysis API:
- Mock the AnalysisStorageService to provide controlled data without Supabase.
- Mock the LLMClient._acompletion to return controlled LLM JSON responses.
- Keep the actual AnalysisService, ExtractionService, TypeInferenceService,
  and VerificationService logic real.

Requirements covered: 1-10 (all)
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.extraction import ExtractionService
from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.service import AnalysisService, AnalysisStorageService
from app.analysis.type_inference import TypeInferenceService
from app.analysis.verification import VerificationService
from app.api.v1.analysis import _get_analysis_service
from app.main import create_app


# ---------------------------------------------------------------------------
# Fixtures: fake LLM responses
# ---------------------------------------------------------------------------

FAKE_TYPE_INFERENCE_RESPONSE = json.dumps(
    {
        "document_type": "prd",
        "justification": "The document contains user stories and acceptance criteria typical of a PRD.",
    }
)

FAKE_LOW_CONFIDENCE_INFERENCE_RESPONSE = json.dumps(
    {
        "document_type": "generic",
        "justification": "The document does not fit any specific category with sufficient confidence.",
    }
)

FAKE_EXTRACTION_RESPONSE = json.dumps(
    {
        "elements": [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "System Purpose",
                "content": "Build an intelligent document analysis platform.",
                "source_ref": {
                    "chunk_id": "chunk-000",
                    "section": "# Introduction",
                    "evidence": "Build an intelligent document analysis platform",
                },
                "relations": [
                    {
                        "target_id": "elem-002",
                        "type": "depends_on",
                        "description": "Purpose depends on actors",
                    }
                ],
            },
            {
                "id": "elem-002",
                "type": "actor",
                "name": "Developer",
                "content": "A software developer using the system.",
                "source_ref": {
                    "chunk_id": "chunk-001",
                    "section": "# Actors",
                    "evidence": "A software developer using the system",
                },
                "relations": [
                    {
                        "target_id": "elem-003",
                        "type": "participates_in",
                        "description": "Developer participates in the process",
                    }
                ],
            },
            {
                "id": "elem-003",
                "type": "proceso",
                "name": "Document Analysis",
                "content": "The process of analyzing documents to extract knowledge.",
                "source_ref": {
                    "chunk_id": "chunk-001",
                    "section": "# Actors",
                    "evidence": "The process of analyzing documents to extract knowledge",
                },
                "relations": [
                    {
                        "target_id": "elem-004",
                        "type": "constrains",
                        "description": "Process is constrained by rules",
                    }
                ],
            },
            {
                "id": "elem-004",
                "type": "regla",
                "name": "Privacy Rule",
                "content": "Only minimum necessary information is sent to AI.",
                "source_ref": {
                    "chunk_id": "chunk-002",
                    "section": "# Rules",
                    "evidence": "Only minimum necessary information is sent to AI",
                },
                "relations": [
                    {
                        "target_id": "elem-003",
                        "type": "contradicts",
                        "description": "Rule contradicts the open analysis process",
                    }
                ],
            },
        ]
    }
)

FAKE_UNPARSEABLE_RESPONSE = "This is not JSON at all, just plain text garbage."


# ---------------------------------------------------------------------------
# Fake storage: in-memory analysis session persistence
# ---------------------------------------------------------------------------


class FakeAnalysisStorage:
    """In-memory implementation of AnalysisStorageService interface.

    Simulates database behavior without requiring Supabase.
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
        size_bytes: int = 1024,
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

    def get_document(self, document_id: str) -> dict | None:
        return self._documents.get(document_id)

    def get_ir(self, document_id: str) -> list[dict] | None:
        chunks = self._chunks.get(document_id)
        if not chunks:
            return None
        return chunks

    def create_session(self, document_id: str) -> dict:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": session_id,
            "document_id": document_id,
            "status": "inferring_type",
            "suggested_type": None,
            "suggested_type_justification": None,
            "confirmed_type": None,
            "knowledge_model": None,
            "extraction_metadata": None,
            "error_message": None,
            "prompt_version": None,
            "model_id": None,
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
# Fixtures
# ---------------------------------------------------------------------------

DEFAULT_CHUNKS = [
    {
        "document_id": "doc-001",
        "chunk_id": "chunk-000",
        "text": "Build an intelligent document analysis platform that processes documents.",
        "structural_context": {"section": "# Introduction"},
        "order": 0,
    },
    {
        "document_id": "doc-001",
        "chunk_id": "chunk-001",
        "text": "A software developer using the system. The process of analyzing documents to extract knowledge.",
        "structural_context": {"section": "# Actors"},
        "order": 1,
    },
    {
        "document_id": "doc-001",
        "chunk_id": "chunk-002",
        "text": "Only minimum necessary information is sent to AI. Privacy rules apply.",
        "structural_context": {"section": "# Rules"},
        "order": 2,
    },
]


@pytest.fixture
def fake_storage():
    """Create a FakeAnalysisStorage with a ready document pre-loaded."""
    storage = FakeAnalysisStorage()
    storage.add_document("doc-001", status="ready")
    storage.add_chunks("doc-001", DEFAULT_CHUNKS)
    return storage


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient that bypasses credential validation and litellm."""
    with patch.object(LLMClient, "__init__", lambda self: None):
        client = LLMClient()
        client.primary_model = "gemini/gemini-2.5-flash-preview-05-20"
        client.light_model = "groq/llama-3.3-70b-versatile"
        client.fallback_model = "groq/llama-3.3-70b-versatile"
        client._acompletion = AsyncMock()
        client._transient_error_types = ()
        client._auth_error_type = None
        # Default: type inference then extraction
        client.call = AsyncMock()
        return client


@pytest.fixture
def analysis_service(fake_storage, mock_llm_client):
    """Create a real AnalysisService with mocked storage and LLM."""
    type_inference = TypeInferenceService(llm_client=mock_llm_client)
    extraction = ExtractionService(llm_client=mock_llm_client)
    verification = VerificationService()

    return AnalysisService(
        type_inference_service=type_inference,
        extraction_service=extraction,
        verification_service=verification,
        storage=fake_storage,
    )


@pytest.fixture
def app(analysis_service):
    """Create a FastAPI app with the analysis service wired in."""
    application = create_app()
    application.dependency_overrides[_get_analysis_service] = lambda: analysis_service
    return application


@pytest_asyncio.fixture
async def async_client(app):
    """Create an httpx AsyncClient for testing the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Happy path: full analysis flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHappyPathAnalysisFlow:
    """Full flow: analyze → verify type → confirm → get KM → verify structure."""

    async def test_full_flow(self, async_client, mock_llm_client):
        """End-to-end happy path verifying KM structure and metadata."""
        # Setup mock LLM responses:
        # 1st call = type inference (light model)
        # 2nd call = extraction (primary model)
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_TYPE_INFERENCE_RESPONSE,
                model_id="groq/llama-3.3-70b-versatile",
            ),
            LLMResponse(
                content=FAKE_EXTRACTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        # Step 1: Initiate analysis
        resp = await async_client.post("/api/v1/documents/doc-001/analyze")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "awaiting_confirmation"
        assert data["suggested_type"] == "prd"
        assert data["suggested_type_justification"] is not None
        assert len(data["suggested_type_justification"]) > 0

        # Step 2: Confirm type
        resp = await async_client.post(
            "/api/v1/documents/doc-001/confirm-type",
            json={"document_type": "prd"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["confirmed_type"] == "prd"

        # Step 3: Retrieve Knowledge Model
        resp = await async_client.get("/api/v1/documents/doc-001/knowledge-model")
        assert resp.status_code == 200
        km = resp.json()

        # Verify KM structure
        assert km["document_id"] == "doc-001"
        assert km["document_type"] == "prd"
        assert len(km["elements"]) >= 1

        # Property 3: Evidence Grounding — each element has source_ref with non-empty evidence
        for element in km["elements"]:
            assert "source_ref" in element
            assert element["source_ref"]["evidence"] is not None
            assert len(element["source_ref"]["evidence"]) > 0

        # Property 4: Relationship Integrity — no dangling target_ids
        element_ids = {e["id"] for e in km["elements"]}
        for element in km["elements"]:
            for rel in element.get("relations", []):
                assert rel["target_id"] in element_ids, (
                    f"Dangling reference: {rel['target_id']} not in {element_ids}"
                )

        # Req 6.4: Contradicts relations are bidirectional
        contradicts_pairs = set()
        for element in km["elements"]:
            for rel in element.get("relations", []):
                if rel["type"] == "contradicts":
                    contradicts_pairs.add((element["id"], rel["target_id"]))

        for source_id, target_id in contradicts_pairs:
            reverse_exists = any(
                rel["target_id"] == source_id and rel["type"] == "contradicts"
                for e in km["elements"]
                if e["id"] == target_id
                for rel in e.get("relations", [])
            )
            assert reverse_exists, (
                f"Contradicts from {source_id} -> {target_id} has no reverse"
            )

        # ExtractionMetadata present with required fields
        meta = km["extraction_metadata"]
        assert "prompt_version" in meta
        assert len(meta["prompt_version"]) > 0
        assert "model_id" in meta
        assert len(meta["model_id"]) > 0
        assert "verification_rate" in meta
        assert 0.0 <= meta["verification_rate"] <= 1.0
        assert "element_count" in meta
        assert "relationship_count" in meta
        assert "temperature" in meta
        assert "extracted_at" in meta


# ---------------------------------------------------------------------------
# Error scenario tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDocumentNotFound:
    """Analyzing a non-existent document returns 404."""

    async def test_analyze_not_found(self, async_client):
        resp = await async_client.post("/api/v1/documents/nonexistent-id/analyze")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"


@pytest.mark.asyncio
class TestDocumentNotReady:
    """Analyzing a document not in 'ready' status returns 409."""

    async def test_analyze_not_ready(self, async_client, fake_storage):
        fake_storage.add_document("doc-processing", status="processing")
        resp = await async_client.post("/api/v1/documents/doc-processing/analyze")
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "not_ready"


@pytest.mark.asyncio
class TestAnalysisAlreadyExists:
    """Analyzing a document that already has a session returns 409."""

    async def test_analyze_already_exists(self, async_client, mock_llm_client):
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_TYPE_INFERENCE_RESPONSE,
            model_id="groq/llama-3.3-70b-versatile",
        )

        # First analysis
        resp = await async_client.post("/api/v1/documents/doc-001/analyze")
        assert resp.status_code == 202

        # Second analysis on same document
        resp = await async_client.post("/api/v1/documents/doc-001/analyze")
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "analysis_exists"


@pytest.mark.asyncio
class TestInvalidDocumentType:
    """Confirming with an invalid type returns 400 with valid_types list."""

    async def test_invalid_type_returns_400(self, async_client, mock_llm_client):
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_TYPE_INFERENCE_RESPONSE,
            model_id="groq/llama-3.3-70b-versatile",
        )

        # Initiate analysis first
        resp = await async_client.post("/api/v1/documents/doc-001/analyze")
        assert resp.status_code == 202

        # Confirm with invalid type
        resp = await async_client.post(
            "/api/v1/documents/doc-001/confirm-type",
            json={"document_type": "invalid_type"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "invalid_document_type"
        assert "valid_types" in data
        assert sorted(data["valid_types"]) == [
            "generic",
            "policy_process",
            "prd",
            "technical_spec",
        ]


@pytest.mark.asyncio
class TestConfirmOnWrongState:
    """Confirming type when session is not in awaiting_confirmation returns 409."""

    async def test_confirm_on_completed_session(self, async_client, mock_llm_client):
        # Setup full flow to completion
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_TYPE_INFERENCE_RESPONSE,
                model_id="groq/llama-3.3-70b-versatile",
            ),
            LLMResponse(
                content=FAKE_EXTRACTION_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        # Complete the analysis
        await async_client.post("/api/v1/documents/doc-001/analyze")
        await async_client.post(
            "/api/v1/documents/doc-001/confirm-type",
            json={"document_type": "prd"},
        )

        # Try to confirm again on completed session
        resp = await async_client.post(
            "/api/v1/documents/doc-001/confirm-type",
            json={"document_type": "technical_spec"},
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "invalid_session_state"


@pytest.mark.asyncio
class TestGetKMBeforeCompletion:
    """Getting KM before analysis is completed returns 409."""

    async def test_km_before_completion(self, async_client, mock_llm_client):
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_TYPE_INFERENCE_RESPONSE,
            model_id="groq/llama-3.3-70b-versatile",
        )

        # Initiate analysis (session is in awaiting_confirmation)
        await async_client.post("/api/v1/documents/doc-001/analyze")

        # Try to get KM
        resp = await async_client.get("/api/v1/documents/doc-001/knowledge-model")
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "not_completed"
        assert "awaiting_confirmation" in data["message"]


# ---------------------------------------------------------------------------
# Evidence verification tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEvidenceVerification:
    """Evidence verification correctly marks verified/unverified elements."""

    async def test_verification_marks_elements(self, async_client, mock_llm_client):
        """Elements with evidence matching IR text are verified, others are not."""
        # Create extraction response where one element has evidence that
        # does NOT match any chunk text
        extraction_with_unverified = json.dumps(
            {
                "elements": [
                    {
                        "id": "elem-v1",
                        "type": "proposito",
                        "name": "Purpose",
                        "content": "Build a platform.",
                        "source_ref": {
                            "chunk_id": "chunk-000",
                            "section": "# Introduction",
                            # This evidence exists in chunk-000
                            "evidence": "Build an intelligent document analysis platform",
                        },
                        "relations": [],
                    },
                    {
                        "id": "elem-v2",
                        "type": "concepto",
                        "name": "Nonexistent Concept",
                        "content": "Some concept not in the document.",
                        "source_ref": {
                            "chunk_id": "chunk-000",
                            "section": "# Introduction",
                            # This evidence does NOT exist anywhere in the IR
                            "evidence": "This text does not appear anywhere in any chunk at all xyz123",
                        },
                        "relations": [],
                    },
                ]
            }
        )

        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_TYPE_INFERENCE_RESPONSE,
                model_id="groq/llama-3.3-70b-versatile",
            ),
            LLMResponse(
                content=extraction_with_unverified,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        # Run full flow
        await async_client.post("/api/v1/documents/doc-001/analyze")
        await async_client.post(
            "/api/v1/documents/doc-001/confirm-type",
            json={"document_type": "prd"},
        )

        resp = await async_client.get("/api/v1/documents/doc-001/knowledge-model")
        assert resp.status_code == 200
        km = resp.json()

        # Find elements by id
        elements_by_id = {e["id"]: e for e in km["elements"]}

        # elem-v1 should be verified (evidence found in chunk-000)
        assert elements_by_id["elem-v1"]["verified"] is True

        # elem-v2 should NOT be verified (evidence not in any chunk)
        assert elements_by_id["elem-v2"]["verified"] is False

        # verification_rate should reflect this (1 out of 2 = 0.5)
        assert km["extraction_metadata"]["verification_rate"] == 0.5


# ---------------------------------------------------------------------------
# Complete parse failure → failed session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestParseFailure:
    """Complete LLM parse failure results in failed session with cleanup."""

    async def test_parse_failure_marks_session_failed(
        self, app, mock_llm_client, fake_storage
    ):
        """When extraction LLM response is unparseable, session becomes failed."""
        mock_llm_client.call.side_effect = [
            LLMResponse(
                content=FAKE_TYPE_INFERENCE_RESPONSE,
                model_id="groq/llama-3.3-70b-versatile",
            ),
            LLMResponse(
                content=FAKE_UNPARSEABLE_RESPONSE,
                model_id="gemini/gemini-2.5-flash-preview-05-20",
            ),
        ]

        # Use raise_server_exceptions=False so 500 errors are returned as responses
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Initiate analysis (succeeds)
            resp = await client.post("/api/v1/documents/doc-001/analyze")
            assert resp.status_code == 202

            # Confirm type — extraction will fail due to unparseable response
            resp = await client.post(
                "/api/v1/documents/doc-001/confirm-type",
                json={"document_type": "prd"},
            )
            # The endpoint re-raises the exception; FastAPI returns 500
            assert resp.status_code == 500

        # Session should be marked as failed with cleanup
        session = fake_storage.get_session_by_document("doc-001")
        assert session is not None
        assert session["status"] == "failed"
        assert session["error_message"] is not None
        assert "failed" in session["error_message"].lower() or "parse" in session["error_message"].lower()
        # Partial KM should be cleaned up (Req 8.4)
        assert session["knowledge_model"] is None


# ---------------------------------------------------------------------------
# Low-confidence type inference → None document_type with "generic" suggestion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLowConfidenceInference:
    """Low-confidence inference returns None document_type with 'generic' suggestion."""

    async def test_low_confidence_returns_generic(
        self, async_client, mock_llm_client
    ):
        """When LLM reports low confidence, suggested_type is 'generic'."""
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_LOW_CONFIDENCE_INFERENCE_RESPONSE,
            model_id="groq/llama-3.3-70b-versatile",
        )

        resp = await async_client.post("/api/v1/documents/doc-001/analyze")
        assert resp.status_code == 202
        data = resp.json()

        # suggested_type should be "generic" (Req 3.3)
        assert data["suggested_type"] == "generic"
        # Justification should be present
        assert data["suggested_type_justification"] is not None
        assert len(data["suggested_type_justification"]) > 0
