"""Integration tests for the base analysis card API flow.

End-to-end tests exercising the full HTTP flow through the document card API:
- GET /api/v1/documents/{document_id}/card
- POST /api/v1/documents/{document_id}/card/retry-llm

These tests validate the interaction between the API layer, service layer,
and response serialization. External services (Supabase, LLM) are mocked
while routing and serialization remain real.

Requirements covered: Req 7 (criteria 1-6).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.v1.card import (
    _get_base_analysis_service,
    _get_base_analysis_storage,
    _get_storage_service,
)
from app.main import create_app
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    DocumentStatus,
    IntermediateRepresentation,
)
from app.models.document_card import (
    DocumentCard,
    DocumentCardStatistics,
    DocumentClassification,
    FileMetadata,
    OrganizationType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(
    document_id: str = "550e8400-e29b-41d4-a716-446655440000",
    status: str = "completed",
    summary: str | None = "Este documento establece las normas de convivencia para propiedades horizontales. Define responsabilidades de propietarios y administración.",
    classification: DocumentClassification | None = DocumentClassification.NORMATIVE,
    model_id: str | None = "groq/llama-3.3-70b-versatile",
    prompt_version: str | None = "base-analysis-v1",
) -> DocumentCard:
    """Create a sample DocumentCard for tests."""
    return DocumentCard(
        id="660e8400-e29b-41d4-a716-446655440001",
        document_id=document_id,
        title="Reglamento de Propiedad Horizontal",
        summary=summary,
        classification=classification,
        organization_type=OrganizationType.NUMBERED_ARTICLES,
        statistics=DocumentCardStatistics(
            total_chunks=45,
            sections_detected=12,
            hierarchy_levels=3,
            has_existing_index=True,
        ),
        file_metadata=FileMetadata(
            size_bytes=234500,
            format="pdf",
            language="es",
        ),
        status=status,
        outdated=False,
        model_id=model_id,
        prompt_version=prompt_version,
        created_at=datetime(2025, 7, 26, 10, 30, 0, tzinfo=timezone.utc),
        updated_at=datetime(2025, 7, 26, 10, 30, 4, tzinfo=timezone.utc),
    )


def _make_ir(document_id: str = "550e8400-e29b-41d4-a716-446655440000") -> IntermediateRepresentation:
    """Create a minimal IR for retry-llm tests."""
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
        ],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_base_analysis_service():
    """Create a mock BaseAnalysisService."""
    return AsyncMock()


@pytest.fixture
def mock_base_analysis_storage():
    """Create a mock BaseAnalysisStorage."""
    return AsyncMock()


@pytest.fixture
def mock_storage_service():
    """Create a mock StorageService (ingestion)."""
    return AsyncMock()


@pytest.fixture
def app(mock_base_analysis_service, mock_base_analysis_storage, mock_storage_service):
    """Create a test FastAPI app with mocked dependencies."""
    test_app = create_app()
    test_app.dependency_overrides[_get_base_analysis_service] = (
        lambda: mock_base_analysis_service
    )
    test_app.dependency_overrides[_get_base_analysis_storage] = (
        lambda: mock_base_analysis_storage
    )
    test_app.dependency_overrides[_get_storage_service] = lambda: mock_storage_service
    return test_app


@pytest_asyncio.fixture
async def async_client(app):
    """Create an httpx AsyncClient for testing the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# GET /api/v1/documents/{document_id}/card — Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetCardIntegration:
    """Integration tests for GET /api/v1/documents/{document_id}/card.

    Validates the full request → service → response flow including
    JSON response shape and correct status codes.
    """

    async def test_existing_completed_card_returns_200_with_full_shape(
        self, async_client, mock_base_analysis_storage, mock_storage_service
    ):
        """Req 7.1: A document with an existing completed card returns 200 with full JSON shape."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id=doc_id, status="ready", filename="reglamento.pdf", format="pdf"
        )
        mock_base_analysis_storage.get_card.return_value = _make_card(document_id=doc_id)

        response = await async_client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 200
        data = response.json()

        # Verify full JSON response shape matches Req 4.2
        assert data["id"] == "660e8400-e29b-41d4-a716-446655440001"
        assert data["document_id"] == doc_id
        assert data["title"] == "Reglamento de Propiedad Horizontal"
        assert data["summary"] is not None
        assert len(data["summary"]) > 0
        assert data["classification"] == "normative"
        assert data["organization_type"] == "numbered_articles"
        assert data["status"] == "completed"
        assert data["outdated"] is False
        assert data["model_id"] == "groq/llama-3.3-70b-versatile"
        assert data["prompt_version"] == "base-analysis-v1"
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

        # Verify nested statistics shape
        stats = data["statistics"]
        assert stats["total_chunks"] == 45
        assert stats["sections_detected"] == 12
        assert stats["hierarchy_levels"] == 3
        assert stats["has_existing_index"] is True

        # Verify nested file_metadata shape
        meta = data["file_metadata"]
        assert meta["size_bytes"] == 234500
        assert meta["format"] == "pdf"
        assert meta["language"] == "es"

    async def test_card_not_found_returns_404_with_error_code(
        self, async_client, mock_base_analysis_storage, mock_storage_service
    ):
        """Req 7.2: Document exists but no card → 404 with card_not_found error code."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id=doc_id, status="ready", filename="doc.md", format="markdown"
        )
        mock_base_analysis_storage.get_card.return_value = None

        response = await async_client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "card_not_found"
        assert "message" in data
        assert doc_id in data["message"]

    async def test_document_not_found_returns_404_with_error_code(
        self, async_client, mock_base_analysis_storage, mock_storage_service
    ):
        """Req 7.3: Non-existent document → 404 with document_not_found error code."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = None

        response = await async_client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "document_not_found"
        assert "message" in data

    async def test_partial_card_returns_200_with_nullable_fields(
        self, async_client, mock_base_analysis_storage, mock_storage_service
    ):
        """A partial card (LLM failed) returns 200 with null summary/classification."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id=doc_id, status="ready", filename="doc.md", format="markdown"
        )
        mock_base_analysis_storage.get_card.return_value = _make_card(
            document_id=doc_id,
            status="partial",
            summary=None,
            classification=None,
            model_id=None,
            prompt_version=None,
        )

        response = await async_client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert data["summary"] is None
        assert data["classification"] is None
        assert data["model_id"] is None
        assert data["prompt_version"] is None
        # Local fields are still present
        assert data["title"] == "Reglamento de Propiedad Horizontal"
        assert data["organization_type"] == "numbered_articles"
        assert data["statistics"]["total_chunks"] == 45
        assert data["file_metadata"]["size_bytes"] == 234500


# ---------------------------------------------------------------------------
# POST /api/v1/documents/{document_id}/card/retry-llm — Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetryLlmIntegration:
    """Integration tests for POST /api/v1/documents/{document_id}/card/retry-llm.

    Validates the full request → service → response flow for LLM retry,
    including correct status codes and error shapes.
    """

    async def test_retry_on_partial_card_returns_200_with_updated_card(
        self, async_client, mock_base_analysis_service, mock_base_analysis_storage, mock_storage_service
    ):
        """Req 7.4: Retry on partial card succeeds → 200 with updated completed card."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        partial_card = _make_card(
            document_id=doc_id,
            status="partial",
            summary=None,
            classification=None,
            model_id=None,
            prompt_version=None,
        )
        updated_card = _make_card(document_id=doc_id, status="completed")

        mock_base_analysis_storage.get_card.return_value = partial_card
        mock_storage_service.get_ir.return_value = _make_ir(doc_id)
        mock_base_analysis_service.retry_llm.return_value = updated_card

        response = await async_client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["summary"] is not None
        assert data["classification"] == "normative"
        assert data["model_id"] == "groq/llama-3.3-70b-versatile"
        assert data["prompt_version"] == "base-analysis-v1"
        # Verify service was called correctly
        mock_base_analysis_service.retry_llm.assert_called_once()

    async def test_retry_on_completed_card_returns_409(
        self, async_client, mock_base_analysis_storage, mock_storage_service
    ):
        """Req 7.5: Retry on completed card → 409 with card_already_complete error code."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_base_analysis_storage.get_card.return_value = _make_card(
            document_id=doc_id, status="completed"
        )

        response = await async_client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "card_already_complete"
        assert "message" in data
        assert "completed" in data["message"]

    async def test_retry_with_no_card_returns_404(
        self, async_client, mock_base_analysis_storage, mock_storage_service
    ):
        """Req 7.6: Retry when no card exists → 404 with card_not_found error code."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_base_analysis_storage.get_card.return_value = None

        response = await async_client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "card_not_found"
        assert "message" in data

    async def test_retry_on_failed_llm_card_returns_200(
        self, async_client, mock_base_analysis_service, mock_base_analysis_storage, mock_storage_service
    ):
        """A card with status 'failed_llm' can be retried and returns 200 on success."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        failed_card = _make_card(
            document_id=doc_id,
            status="failed_llm",
            summary=None,
            classification=None,
            model_id=None,
            prompt_version=None,
        )
        updated_card = _make_card(document_id=doc_id, status="completed")

        mock_base_analysis_storage.get_card.return_value = failed_card
        mock_storage_service.get_ir.return_value = _make_ir(doc_id)
        mock_base_analysis_service.retry_llm.return_value = updated_card

        response = await async_client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["summary"] is not None
        assert data["classification"] == "normative"

    async def test_retry_invalid_uuid_returns_404(self, async_client):
        """An invalid UUID format in retry-llm returns 404 with card_not_found."""
        response = await async_client.post(
            "/api/v1/documents/not-a-valid-uuid/card/retry-llm"
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "card_not_found"

    async def test_retry_response_includes_all_card_fields(
        self, async_client, mock_base_analysis_service, mock_base_analysis_storage, mock_storage_service
    ):
        """After successful retry, response includes the complete card JSON shape."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        partial_card = _make_card(
            document_id=doc_id,
            status="partial",
            summary=None,
            classification=None,
            model_id=None,
            prompt_version=None,
        )
        updated_card = _make_card(document_id=doc_id, status="completed")

        mock_base_analysis_storage.get_card.return_value = partial_card
        mock_storage_service.get_ir.return_value = _make_ir(doc_id)
        mock_base_analysis_service.retry_llm.return_value = updated_card

        response = await async_client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present in the response
        required_fields = [
            "id", "document_id", "title", "summary", "classification",
            "organization_type", "statistics", "file_metadata", "status",
            "outdated", "model_id", "prompt_version", "created_at", "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

        # Verify nested objects have expected keys
        assert "total_chunks" in data["statistics"]
        assert "sections_detected" in data["statistics"]
        assert "hierarchy_levels" in data["statistics"]
        assert "has_existing_index" in data["statistics"]
        assert "size_bytes" in data["file_metadata"]
        assert "format" in data["file_metadata"]
        assert "language" in data["file_metadata"]
