"""End-to-end integration tests for the base analysis pipeline.

Tests the full flow: upload document → ingestion → background analysis → GET /card.
External services (LLM, Supabase) are mocked, but the real LocalAnalyzer,
LLMAnalyzer, BaseAnalysisService, and API routing are exercised.

The key challenge is that BackgroundTasks in FastAPI run after the response is sent.
In tests with httpx AsyncClient (ASGI transport), background tasks execute before
the response is returned, so we can directly call GET /card after upload.

Requirements covered: Req 1 (criteria 1, 2), Req 5 (criterion 4).
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.base_analysis.llm_analyzer import LLMAnalyzer
from app.analysis.base_analysis.local_analyzer import LocalAnalyzer
from app.analysis.base_analysis.service import BaseAnalysisService
from app.analysis.base_analysis.storage import BaseAnalysisStorage
from app.analysis.llm_client import LLMClient, LLMResponse, LLMTransientError
from app.api.v1.card import (
    _get_base_analysis_service,
    _get_base_analysis_storage,
    _get_storage_service as _get_card_storage_service,
)
from app.api.v1.documents import (
    _get_base_analysis_service as _get_documents_base_analysis_service,
    _get_ingestion_service,
    _get_storage_service,
)
from app.ingestion.service import IngestionService
from app.ingestion.storage import StorageService
from app.main import create_app
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    DocumentStatus,
    IntermediateRepresentation,
)
from app.models.document_card import DocumentCard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ir(document_id: str = "550e8400-e29b-41d4-a716-446655440000") -> IntermediateRepresentation:
    """Create a realistic IR for end-to-end tests."""
    return IntermediateRepresentation(
        document_id=document_id,
        metadata=DocumentMetadata(
            original_filename="reglamento.pdf",
            format=DocumentFormat.PDF,
            size_bytes=234500,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 7, 26, 10, 29, 0, tzinfo=timezone.utc),
            warnings=[],
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-000",
                text="Artículo 1. Disposiciones generales del reglamento de propiedad horizontal.",
                structural_context={"section": "Disposiciones Generales", "level": 1},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-001",
                text="Artículo 2. Derechos y obligaciones de los propietarios.",
                structural_context={"section": "Derechos y Obligaciones", "level": 1},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="chunk-002",
                text="Artículo 3. Administración de la propiedad horizontal.",
                structural_context={"section": "Administración", "level": 1},
                order=2,
            ),
            ContentChunkModel(
                chunk_id="chunk-003",
                text="Artículo 4. Cuotas de administración y mantenimiento.",
                structural_context={"section": "Cuotas", "level": 1},
                order=3,
            ),
            ContentChunkModel(
                chunk_id="chunk-004",
                text="Artículo 5. Resolución de conflictos entre propietarios.",
                structural_context={"section": "Conflictos", "level": 1},
                order=4,
            ),
        ],
    )


class InMemoryBaseAnalysisStorage:
    """In-memory storage for DocumentCard, simulating Supabase persistence.

    Allows the real BaseAnalysisService to persist cards during tests,
    and the card API to retrieve them via GET /card.
    """

    def __init__(self):
        self._cards: dict[str, DocumentCard] = {}

    async def get_card(self, document_id: str) -> DocumentCard | None:
        return self._cards.get(document_id)

    async def upsert_card(self, card: DocumentCard) -> None:
        self._cards[card.document_id] = card

    async def mark_outdated(self, document_id: str) -> None:
        if document_id in self._cards:
            existing = self._cards[document_id]
            self._cards[document_id] = existing.model_copy(update={"outdated": True})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ir():
    """Create a sample IR for tests."""
    return _make_ir()


@pytest.fixture
def mock_llm_client_success():
    """Create a mock LLM client that returns valid JSON for summary + classification."""
    mock_client = AsyncMock(spec=LLMClient)
    mock_client.call.return_value = LLMResponse(
        content=json.dumps({
            "summary": "Este documento establece las normas de convivencia para propiedades horizontales. Define responsabilidades de propietarios y administración.",
            "classification": "normative",
        }),
        model_id="groq/llama-3.3-70b-versatile",
    )
    return mock_client


@pytest.fixture
def mock_llm_client_failure():
    """Create a mock LLM client that raises a timeout error."""
    mock_client = AsyncMock(spec=LLMClient)
    mock_client.call.side_effect = asyncio.TimeoutError("LLM timeout after 10s")
    return mock_client


@pytest.fixture
def in_memory_storage():
    """Create an in-memory storage that works like the real BaseAnalysisStorage."""
    return InMemoryBaseAnalysisStorage()


@pytest.fixture
def mock_ingestion_service(sample_ir):
    """Create a mock IngestionService that simulates successful ingestion."""
    mock_service = AsyncMock(spec=IngestionService)
    # Simulate a successful ingestion that returns status=ready
    mock_service.ingest.return_value = DocumentStatus(
        document_id=sample_ir.document_id,
        status="ready",
        filename="reglamento.pdf",
        format="pdf",
        language="es",
        chunk_count=5,
        warnings=[],
    )
    return mock_service


@pytest.fixture
def mock_storage_service(sample_ir):
    """Create a mock StorageService that returns the IR."""
    mock_service = AsyncMock(spec=StorageService)
    # get_ir returns the test IR (used by background task)
    mock_service.get_ir.return_value = sample_ir
    # get_status returns a ready status (used by GET /card endpoint)
    mock_service.get_status.return_value = DocumentStatus(
        document_id=sample_ir.document_id,
        status="ready",
        filename="reglamento.pdf",
        format="pdf",
        language="es",
        chunk_count=5,
        warnings=[],
    )
    return mock_service


@pytest.fixture
def app_success(
    mock_ingestion_service,
    mock_storage_service,
    mock_llm_client_success,
    in_memory_storage,
):
    """Create a test app with real analyzers and mocked LLM (success case)."""
    test_app = create_app()

    # Real analyzers with mocked LLM client
    local_analyzer = LocalAnalyzer()
    llm_analyzer = LLMAnalyzer(llm_client=mock_llm_client_success)
    base_analysis_service = BaseAnalysisService(
        local_analyzer=local_analyzer,
        llm_analyzer=llm_analyzer,
        storage=in_memory_storage,
    )

    # Override dependencies
    test_app.dependency_overrides[_get_ingestion_service] = lambda: mock_ingestion_service
    test_app.dependency_overrides[_get_storage_service] = lambda: mock_storage_service
    test_app.dependency_overrides[_get_documents_base_analysis_service] = lambda: base_analysis_service
    test_app.dependency_overrides[_get_base_analysis_service] = lambda: base_analysis_service
    test_app.dependency_overrides[_get_base_analysis_storage] = lambda: in_memory_storage
    test_app.dependency_overrides[_get_card_storage_service] = lambda: mock_storage_service

    return test_app


@pytest.fixture
def app_llm_failure(
    mock_ingestion_service,
    mock_storage_service,
    mock_llm_client_failure,
    in_memory_storage,
):
    """Create a test app with real analyzers and mocked LLM (failure case)."""
    test_app = create_app()

    # Real analyzers with failing LLM client
    local_analyzer = LocalAnalyzer()
    llm_analyzer = LLMAnalyzer(llm_client=mock_llm_client_failure)
    base_analysis_service = BaseAnalysisService(
        local_analyzer=local_analyzer,
        llm_analyzer=llm_analyzer,
        storage=in_memory_storage,
    )

    # Override dependencies
    test_app.dependency_overrides[_get_ingestion_service] = lambda: mock_ingestion_service
    test_app.dependency_overrides[_get_storage_service] = lambda: mock_storage_service
    test_app.dependency_overrides[_get_documents_base_analysis_service] = lambda: base_analysis_service
    test_app.dependency_overrides[_get_base_analysis_service] = lambda: base_analysis_service
    test_app.dependency_overrides[_get_base_analysis_storage] = lambda: in_memory_storage
    test_app.dependency_overrides[_get_card_storage_service] = lambda: mock_storage_service

    return test_app


@pytest_asyncio.fixture
async def client_success(app_success):
    """Create an httpx AsyncClient for the success case app."""
    transport = ASGITransport(app=app_success)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def client_llm_failure(app_llm_failure):
    """Create an httpx AsyncClient for the LLM failure case app."""
    transport = ASGITransport(app=app_llm_failure)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# End-to-End Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestE2EBaseAnalysisSuccess:
    """E2E test: upload → background analysis (LLM success) → GET /card returns completed card.

    Validates Requirements: Req 1 (criteria 1, 2), Req 5 (criterion 4).
    """

    async def test_upload_triggers_analysis_and_card_is_available(
        self, client_success, sample_ir
    ):
        """Upload document → background analysis completes → GET /card returns completed card.

        Req 1.1: Base analysis triggers automatically after successful ingestion.
        Req 1.2: Analysis executes asynchronously (upload returns immediately).
        Req 5.4: Upload does not block waiting for analysis.
        """
        doc_id = sample_ir.document_id

        # Step 1: Upload a document (POST /upload)
        upload_response = await client_success.post(
            "/api/v1/documents/upload",
            files={"file": ("reglamento.pdf", b"fake pdf content", "application/pdf")},
        )

        # Upload returns 202 immediately (Req 1.2, Req 5.4)
        assert upload_response.status_code == 202
        upload_data = upload_response.json()
        assert upload_data["status"] == "ready"
        assert upload_data["document_id"] == doc_id

        # Step 2: Background task should have run (ASGI transport executes tasks inline).
        # Step 3: GET /card should return the completed card.
        card_response = await client_success.get(
            f"/api/v1/documents/{doc_id}/card"
        )

        assert card_response.status_code == 200
        card_data = card_response.json()

        # Verify card is completed with all fields populated
        assert card_data["document_id"] == doc_id
        assert card_data["status"] == "completed"

        # LLM-derived fields are present
        assert card_data["summary"] is not None
        assert "normas de convivencia" in card_data["summary"]
        assert card_data["classification"] == "normative"
        assert card_data["model_id"] == "groq/llama-3.3-70b-versatile"
        assert card_data["prompt_version"] == "base-analysis-v2"

        # Local processing fields are present
        assert card_data["title"] == "Disposiciones Generales"
        assert card_data["organization_type"] == "numbered_articles"
        assert card_data["outdated"] is False

        # Statistics
        stats = card_data["statistics"]
        assert stats["total_chunks"] == 5
        assert stats["sections_detected"] == 5
        assert stats["hierarchy_levels"] == 1
        assert stats["has_existing_index"] is False

        # File metadata
        meta = card_data["file_metadata"]
        assert meta["size_bytes"] == 234500
        assert meta["format"] == "pdf"
        assert meta["language"] == "es"

        # Timestamps are present
        assert card_data["created_at"] is not None
        assert card_data["updated_at"] is not None


@pytest.mark.asyncio
class TestE2EBaseAnalysisLLMFailure:
    """E2E test: upload → background analysis (LLM failure) → GET /card returns partial card.

    Validates Requirements: Req 1 (criteria 1, 2, 4), Req 5 (criteria 2, 3, 4).
    """

    async def test_upload_with_llm_failure_produces_partial_card(
        self, client_llm_failure, sample_ir
    ):
        """Upload document → LLM times out → GET /card returns partial card with local data.

        Req 1.4: Analysis failure does not affect document status.
        Req 5.2: LLM timeout → partial card persisted.
        Req 5.3: Partial card contains all local processing results.
        """
        doc_id = sample_ir.document_id

        # Step 1: Upload a document (POST /upload)
        upload_response = await client_llm_failure.post(
            "/api/v1/documents/upload",
            files={"file": ("reglamento.pdf", b"fake pdf content", "application/pdf")},
        )

        # Upload returns 202 immediately even though LLM will fail
        assert upload_response.status_code == 202
        upload_data = upload_response.json()
        assert upload_data["status"] == "ready"
        assert upload_data["document_id"] == doc_id

        # Step 2: Background task ran with LLM failure → partial card created.
        # Step 3: GET /card should return the partial card.
        card_response = await client_llm_failure.get(
            f"/api/v1/documents/{doc_id}/card"
        )

        assert card_response.status_code == 200
        card_data = card_response.json()

        # Verify card is partial
        assert card_data["document_id"] == doc_id
        assert card_data["status"] == "partial"

        # LLM-derived fields are null (LLM failed)
        assert card_data["summary"] is None
        assert card_data["classification"] is None
        assert card_data["model_id"] is None
        assert card_data["prompt_version"] is None

        # Local processing fields are still present and correct (Req 5.3)
        assert card_data["title"] == "Disposiciones Generales"
        assert card_data["organization_type"] == "numbered_articles"
        assert card_data["outdated"] is False

        # Statistics are complete
        stats = card_data["statistics"]
        assert stats["total_chunks"] == 5
        assert stats["sections_detected"] == 5
        assert stats["hierarchy_levels"] == 1
        assert stats["has_existing_index"] is False

        # File metadata is complete
        meta = card_data["file_metadata"]
        assert meta["size_bytes"] == 234500
        assert meta["format"] == "pdf"
        assert meta["language"] == "es"

        # Timestamps are present
        assert card_data["created_at"] is not None
        assert card_data["updated_at"] is not None
