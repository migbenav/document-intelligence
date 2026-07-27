"""Integration tests for the on-demand analysis API endpoints.

End-to-end tests exercising the full HTTP flow through the on-demand analyses API:
- POST /api/v1/documents/{id}/analyses/{type} -> trigger analysis
- GET /api/v1/documents/{id}/analyses -> get all statuses
- GET /api/v1/documents/{id}/analyses/{type} -> get single result

Tests use httpx AsyncClient with mocked LLM (via dependency overrides)
and in-memory fake services to simulate storage behavior.

Requirements covered: Req 7 (criteria 1-9)
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.on_demand.conclusions_analyzer import ConclusionsAnalyzer
from app.analysis.on_demand.index_analyzer import IndexAnalyzer
from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
)
from app.analysis.on_demand.questions_analyzer import QuestionsAnalyzer
from app.analysis.on_demand.relations_analyzer import RelationsAnalyzer
from app.analysis.on_demand.service import OnDemandAnalysisService
from app.analysis.on_demand.storage import OnDemandAnalysisStorage
from app.api.v1.analyses import (
    _get_on_demand_analysis_service,
    _get_storage_service,
)
from app.main import create_app
from app.models.document import DocumentStatus


# ---------------------------------------------------------------------------
# Fake LLM responses
# ---------------------------------------------------------------------------

FAKE_INDEX_RESULT = json.dumps(
    {
        "tree": [
            {
                "id": "node-1",
                "title": "Introduction",
                "level": 1,
                "role": "describes",
                "question_answered": "What is the purpose of this document?",
                "source_ref": {
                    "chunk_ids": ["chunk-001"],
                    "text_excerpt": "This document describes the procurement process.",
                    "section": "Introduction",
                },
                "children": [
                    {
                        "id": "node-1-1",
                        "title": "Scope",
                        "level": 2,
                        "role": "defines",
                        "question_answered": "What does this document cover?",
                        "source_ref": {
                            "chunk_ids": ["chunk-002"],
                            "text_excerpt": "Covers all procurement activities.",
                            "section": "Scope",
                        },
                        "children": [],
                    }
                ],
            },
            {
                "id": "node-2",
                "title": "Procedures",
                "level": 1,
                "role": "establishes",
                "question_answered": "How are purchases managed?",
                "source_ref": {
                    "chunk_ids": ["chunk-003"],
                    "text_excerpt": "All purchases must follow this procedure.",
                    "section": "Procedures",
                },
                "children": [],
            },
        ]
    }
)

FAKE_RELATIONS_RESULT = json.dumps(
    {
        "relations": [
            {
                "source_section": "Introduction",
                "target_section": "Procedures",
                "type": "complements",
                "description": "The introduction sets context for the procedures.",
                "source_ref": {
                    "chunk_ids": ["chunk-001", "chunk-003"],
                    "text_excerpt": "This document describes the procurement process.",
                    "section": "Introduction",
                },
            }
        ]
    }
)

FAKE_QUESTIONS_RESULT = json.dumps(
    {
        "document_questions": [
            {
                "question": "What is the procurement process?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["chunk-001"],
                    "text_excerpt": "This document describes the procurement process.",
                    "section": "Introduction",
                },
            }
        ],
        "section_questions": [
            {
                "question": "How are purchases requested?",
                "level": "section",
                "section_title": "Procedures",
                "source_ref": {
                    "chunk_ids": ["chunk-003"],
                    "text_excerpt": "All purchases must follow this procedure.",
                    "section": "Procedures",
                },
            }
        ],
    }
)

FAKE_CONCLUSIONS_RESULT = json.dumps(
    {
        "observations": [
            {
                "category": "coherence",
                "description": "All sections are consistent with the document purpose.",
                "suggestion": "Consider adding a glossary section before procedures.",
                "section_ref": "Procedures",
                "source_ref": {
                    "chunk_ids": ["chunk-003"],
                    "text_excerpt": "All purchases must follow this procedure.",
                    "section": "Procedures",
                },
            }
        ]
    }
)


# ---------------------------------------------------------------------------
# Fake StorageService — mimics ingestion storage
# ---------------------------------------------------------------------------


class FakeIngestionStorage:
    """In-memory implementation of StorageService for testing.

    Only implements get_status and get_ir methods used by the analyses router
    and the OnDemandAnalysisService.
    """

    def __init__(self) -> None:
        self._documents: dict[str, DocumentStatus] = {}
        self._ir_data: dict[str, object] = {}

    def add_document(self, document_id: str, *, status: str = "ready") -> None:
        """Add a document record to the fake storage."""
        self._documents[document_id] = DocumentStatus(
            document_id=document_id,
            status=status,
            filename="test.md",
            format="markdown",
            language="es",
            chunk_count=3,
            warnings=[],
            error_message=None,
        )

    def add_ir(self, document_id: str, ir: object) -> None:
        """Add an IR record for a document."""
        self._ir_data[document_id] = ir

    async def get_status(self, document_id: str) -> DocumentStatus | None:
        """Return document status or None."""
        return self._documents.get(document_id)

    async def get_ir(self, document_id: str):
        """Return IR or None."""
        return self._ir_data.get(document_id)


# ---------------------------------------------------------------------------
# Fake OnDemandAnalysisStorage — in-memory persistence
# ---------------------------------------------------------------------------


class FakeOnDemandStorage:
    """In-memory implementation of OnDemandAnalysisStorage for testing."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], AnalysisRecord] = {}

    async def get_result(
        self, document_id: str, analysis_type: AnalysisType
    ) -> AnalysisRecord | None:
        return self._records.get((document_id, analysis_type.value))

    async def save_result(self, record: AnalysisRecord) -> None:
        self._records[(record.document_id, record.analysis_type.value)] = record

    async def get_all_statuses(self, document_id: str) -> dict[str, dict]:
        statuses: dict[str, dict] = {}
        for analysis_type in AnalysisType:
            key = (document_id, analysis_type.value)
            if key in self._records:
                rec = self._records[key]
                statuses[analysis_type.value] = {
                    "status": rec.status.value,
                    "updated_at": rec.updated_at.isoformat()
                    if isinstance(rec.updated_at, datetime)
                    else str(rec.updated_at),
                }
            else:
                statuses[analysis_type.value] = {
                    "status": AnalysisStatus.NOT_STARTED.value,
                    "updated_at": None,
                }
        return statuses

    async def mark_all_outdated(self, document_id: str) -> None:
        for key, record in self._records.items():
            if key[0] == document_id:
                # Create a new record with outdated status
                self._records[key] = AnalysisRecord(
                    id=record.id,
                    document_id=record.document_id,
                    analysis_type=record.analysis_type,
                    status=AnalysisStatus.OUTDATED,
                    result=record.result,
                    model_id=record.model_id,
                    prompt_version=record.prompt_version,
                    error_message=record.error_message,
                    created_at=record.created_at,
                    updated_at=datetime.now(timezone.utc),
                )


# ---------------------------------------------------------------------------
# Fake IR object
# ---------------------------------------------------------------------------


class FakeChunk:
    """Simulates a single IR chunk."""

    def __init__(self, chunk_id: str, text: str, section: str, order: int) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.structural_context = {"section": section}
        self.order = order


class FakeIR:
    """Simulates an IntermediateRepresentation for testing."""

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        self.chunks = [
            FakeChunk("chunk-001", "This document describes the procurement process.", "Introduction", 0),
            FakeChunk("chunk-002", "Covers all procurement activities.", "Scope", 1),
            FakeChunk("chunk-003", "All purchases must follow this procedure.", "Procedures", 2),
        ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOC_ID = "doc-test-001"


@pytest.fixture
def fake_ingestion_storage():
    """Create fake ingestion storage with a ready document + IR."""
    storage = FakeIngestionStorage()
    storage.add_document(DOC_ID, status="ready")
    storage.add_ir(DOC_ID, FakeIR(DOC_ID))
    return storage


@pytest.fixture
def fake_analysis_storage():
    """Create empty fake on-demand analysis storage."""
    return FakeOnDemandStorage()


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
def on_demand_service(fake_analysis_storage, fake_ingestion_storage, mock_llm_client):
    """Build a real OnDemandAnalysisService with mocked LLM and fake storage."""
    index_analyzer = IndexAnalyzer(llm_client=mock_llm_client)
    relations_analyzer = RelationsAnalyzer(llm_client=mock_llm_client)
    questions_analyzer = QuestionsAnalyzer(llm_client=mock_llm_client)
    conclusions_analyzer = ConclusionsAnalyzer(llm_client=mock_llm_client)

    return OnDemandAnalysisService(
        index_analyzer=index_analyzer,
        relations_analyzer=relations_analyzer,
        questions_analyzer=questions_analyzer,
        conclusions_analyzer=conclusions_analyzer,
        storage=fake_analysis_storage,
        ingestion_storage=fake_ingestion_storage,
    )


@pytest.fixture
def app(on_demand_service, fake_ingestion_storage):
    """Create a FastAPI app with on-demand analysis dependencies wired in."""
    application = create_app()
    application.dependency_overrides[_get_on_demand_analysis_service] = (
        lambda: on_demand_service
    )
    application.dependency_overrides[_get_storage_service] = (
        lambda: fake_ingestion_storage
    )
    return application


@pytest_asyncio.fixture
async def client(app):
    """Create an httpx AsyncClient for testing the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# POST trigger: returns 200 with result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPostTriggerSuccess:
    """POST /analyses/{type} triggers analysis and returns 200."""

    async def test_post_trigger_returns_200_with_result(
        self, client, mock_llm_client
    ):
        """POST build_index triggers LLM call and returns completed result."""
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_INDEX_RESULT,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        resp = await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis_type"] == "build_index"
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert "tree" in data["result"]
        assert len(data["result"]["tree"]) == 2
        assert data["result"]["tree"][0]["title"] == "Introduction"
        assert data["document_id"] == DOC_ID
        assert mock_llm_client.call.call_count == 1

    async def test_post_trigger_all_types(self, app, mock_llm_client):
        """POST succeeds for all four analysis types."""
        type_responses = {
            "build_index": FAKE_INDEX_RESULT,
            "section_relations": FAKE_RELATIONS_RESULT,
            "questions_answered": FAKE_QUESTIONS_RESULT,
            "conclusions": FAKE_CONCLUSIONS_RESULT,
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            for analysis_type, response_json in type_responses.items():
                mock_llm_client.call.reset_mock()
                mock_llm_client.call.return_value = LLMResponse(
                    content=response_json,
                    model_id="gemini/gemini-2.5-flash-preview-05-20",
                )

                resp = await c.post(
                    f"/api/v1/documents/{DOC_ID}/analyses/{analysis_type}"
                )

                assert resp.status_code == 200, (
                    f"Expected 200 for {analysis_type}, got {resp.status_code}"
                )
                data = resp.json()
                assert data["analysis_type"] == analysis_type
                assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# POST trigger: idempotent (second call returns cached)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPostTriggerIdempotency:
    """POST on already-completed analysis returns cached result (Req 7.3)."""

    async def test_second_call_returns_cached_without_llm(
        self, client, mock_llm_client
    ):
        """Second POST returns same result without making another LLM call."""
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_INDEX_RESULT,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        # First call triggers LLM
        resp1 = await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index"
        )
        assert resp1.status_code == 200
        assert mock_llm_client.call.call_count == 1

        # Second call returns cached
        resp2 = await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index"
        )
        assert resp2.status_code == 200

        # LLM was called only once (idempotency)
        assert mock_llm_client.call.call_count == 1

        # Results are identical
        assert resp1.json()["result"] == resp2.json()["result"]
        assert resp1.json()["status"] == "completed"
        assert resp2.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# POST trigger: 404 for non-existent document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPostTrigger404:
    """POST returns 404 when document does not exist (Req 7.4)."""

    async def test_post_nonexistent_document_returns_404(self, client):
        """POST for a non-existent document_id returns 404."""
        resp = await client.post(
            "/api/v1/documents/nonexistent-doc/analyses/build_index"
        )

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "document_not_found"
        assert "nonexistent-doc" in data["message"]


# ---------------------------------------------------------------------------
# POST trigger: 409 for document without IR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPostTrigger409:
    """POST returns 409 when document IR is not available (Req 7.5)."""

    async def test_post_document_without_ir_returns_409(
        self, app, fake_ingestion_storage, mock_llm_client
    ):
        """POST returns 409 when the document exists but has no IR."""
        # Add a document without IR
        fake_ingestion_storage.add_document("doc-no-ir", status="ready")
        # Note: no IR added for "doc-no-ir"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/documents/doc-no-ir/analyses/build_index"
            )

        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "document_not_ready"
        assert "doc-no-ir" in data["message"]


# ---------------------------------------------------------------------------
# POST trigger: 502 on LLM failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPostTrigger502:
    """POST returns 502 when LLM call fails (Req 7.6)."""

    async def test_post_llm_failure_returns_502(self, client, mock_llm_client):
        """POST returns 502 when the LLM raises an exception."""
        mock_llm_client.call.side_effect = RuntimeError("LLM service unavailable")

        resp = await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index"
        )

        assert resp.status_code == 502
        data = resp.json()
        assert data["error"] == "analysis_failed"
        assert "LLM service unavailable" in data["message"]

    async def test_post_timeout_returns_502(self, client, mock_llm_client):
        """POST returns 502 when the LLM call times out."""
        import asyncio

        mock_llm_client.call.side_effect = asyncio.TimeoutError()

        resp = await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index"
        )

        assert resp.status_code == 502
        data = resp.json()
        assert data["error"] == "analysis_failed"


# ---------------------------------------------------------------------------
# GET all statuses: correct summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetAllStatuses:
    """GET /analyses returns status summary for all 4 types (Req 7.7)."""

    async def test_get_all_statuses_empty(self, client):
        """GET returns all 4 types as not_started when nothing executed."""
        resp = await client.get(f"/api/v1/documents/{DOC_ID}/analyses")

        assert resp.status_code == 200
        data = resp.json()

        assert "build_index" in data
        assert "section_relations" in data
        assert "questions_answered" in data
        assert "conclusions" in data

        for analysis_type in data.values():
            assert analysis_type["status"] == "not_started"
            assert analysis_type["updated_at"] is None

    async def test_get_all_statuses_after_execution(self, client, mock_llm_client):
        """GET reflects completed status after POST trigger."""
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_INDEX_RESULT,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        # Trigger one analysis
        await client.post(f"/api/v1/documents/{DOC_ID}/analyses/build_index")

        # GET shows mixed statuses
        resp = await client.get(f"/api/v1/documents/{DOC_ID}/analyses")

        assert resp.status_code == 200
        data = resp.json()
        assert data["build_index"]["status"] == "completed"
        assert data["build_index"]["updated_at"] is not None
        assert data["section_relations"]["status"] == "not_started"
        assert data["questions_answered"]["status"] == "not_started"
        assert data["conclusions"]["status"] == "not_started"

    async def test_get_all_statuses_404_for_nonexistent_document(self, client):
        """GET returns 404 when document does not exist."""
        resp = await client.get("/api/v1/documents/nonexistent-doc/analyses")

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "document_not_found"


# ---------------------------------------------------------------------------
# GET single: completed result, not_started result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetSingleResult:
    """GET /analyses/{type} returns stored result or not_started (Req 7.8)."""

    async def test_get_single_not_started(self, client):
        """GET returns not_started when analysis was never executed."""
        resp = await client.get(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis_type"] == "build_index"
        assert data["status"] == "not_started"
        assert data["result"] is None

    async def test_get_single_completed(self, client, mock_llm_client):
        """GET returns full result after analysis is completed."""
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_INDEX_RESULT,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        # First trigger the analysis
        await client.post(f"/api/v1/documents/{DOC_ID}/analyses/build_index")

        # Then GET the result
        resp = await client.get(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis_type"] == "build_index"
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert "tree" in data["result"]
        assert data["document_id"] == DOC_ID

    async def test_get_single_404_for_nonexistent_document(self, client):
        """GET returns 404 when document does not exist."""
        resp = await client.get(
            "/api/v1/documents/nonexistent-doc/analyses/build_index"
        )

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "document_not_found"

    async def test_get_single_questions_answered(self, client, mock_llm_client):
        """GET returns questions_answered result after trigger."""
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_QUESTIONS_RESULT,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/questions_answered"
        )

        resp = await client.get(
            f"/api/v1/documents/{DOC_ID}/analyses/questions_answered"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis_type"] == "questions_answered"
        assert data["status"] == "completed"
        assert "document_questions" in data["result"]
        assert "section_questions" in data["result"]


# ---------------------------------------------------------------------------
# Preference headers respected (Req 7.9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPreferenceHeaders:
    """Endpoints respect user preferences headers (Req 7.9)."""

    async def test_accept_language_header_propagated(
        self, client, mock_llm_client
    ):
        """Accept-Language header affects the analysis execution."""
        mock_llm_client.call.return_value = LLMResponse(
            content=FAKE_INDEX_RESULT,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        resp = await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/build_index",
            headers={"Accept-Language": "en"},
        )

        assert resp.status_code == 200

        # Verify the LLM was called (preferences don't change the mock response,
        # but we confirm the endpoint processed headers without error)
        assert mock_llm_client.call.call_count == 1

    async def test_invalid_analysis_type_returns_422(self, client):
        """Invalid analysis_type in URL returns 422 (FastAPI validation)."""
        resp = await client.post(
            f"/api/v1/documents/{DOC_ID}/analyses/invalid_type"
        )

        assert resp.status_code == 422
