"""Unit tests for the document card API endpoints.

Tests GET /api/v1/documents/{document_id}/card and
POST /api/v1/documents/{document_id}/card/retry-llm using
mocked dependencies.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
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


def _make_card(
    document_id: str = "550e8400-e29b-41d4-a716-446655440000",
    status: str = "completed",
    summary: str | None = "A test document summary.",
    classification: DocumentClassification | None = DocumentClassification.NORMATIVE,
) -> DocumentCard:
    """Create a sample DocumentCard for tests."""
    return DocumentCard(
        id="660e8400-e29b-41d4-a716-446655440001",
        document_id=document_id,
        title="Test Document",
        summary=summary,
        classification=classification,
        organization_type=OrganizationType.HEADED_SECTIONS,
        statistics=DocumentCardStatistics(
            total_chunks=10,
            sections_detected=3,
            hierarchy_levels=2,
            has_existing_index=False,
        ),
        file_metadata=FileMetadata(
            size_bytes=5000,
            format="markdown",
            language="en",
        ),
        status=status,
        outdated=False,
        model_id="groq/llama-3.3-70b-versatile",
        prompt_version="base-analysis-v1",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, 0, 0, 4, tzinfo=timezone.utc),
    )


# --- GET /api/v1/documents/{document_id}/card ---


@pytest.mark.asyncio
class TestGetDocumentCard:
    """Tests for GET /api/v1/documents/{document_id}/card."""

    async def test_existing_card_returns_200(
        self, app, mock_base_analysis_storage, mock_storage_service
    ):
        """A document with an existing card returns 200 with the full card."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id=doc_id, status="ready", filename="test.md", format="markdown"
        )
        mock_base_analysis_storage.get_card.return_value = _make_card(document_id=doc_id)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == doc_id
        assert data["title"] == "Test Document"
        assert data["summary"] == "A test document summary."
        assert data["classification"] == "normative"
        assert data["organization_type"] == "headed_sections"
        assert data["statistics"]["total_chunks"] == 10
        assert data["file_metadata"]["size_bytes"] == 5000
        assert data["status"] == "completed"

    async def test_document_not_found_returns_404(
        self, app, mock_base_analysis_storage, mock_storage_service
    ):
        """A non-existent document returns 404 with document_not_found."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "document_not_found"

    async def test_card_not_found_returns_404(
        self, app, mock_base_analysis_storage, mock_storage_service
    ):
        """A document that exists but has no card returns 404 with card_not_found."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id=doc_id, status="ready", filename="test.md", format="markdown"
        )
        mock_base_analysis_storage.get_card.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "card_not_found"

    async def test_invalid_uuid_returns_404(self, app, mock_storage_service):
        """An invalid UUID format returns 404 with document_not_found."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/not-a-uuid/card")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "document_not_found"

    async def test_partial_card_returns_200(
        self, app, mock_base_analysis_storage, mock_storage_service
    ):
        """A partial card (LLM failed) is still returned with 200."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id=doc_id, status="ready", filename="test.md", format="markdown"
        )
        mock_base_analysis_storage.get_card.return_value = _make_card(
            document_id=doc_id,
            status="partial",
            summary=None,
            classification=None,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/documents/{doc_id}/card")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert data["summary"] is None
        assert data["classification"] is None
        assert data["title"] == "Test Document"


# --- POST /api/v1/documents/{document_id}/card/retry-llm ---


@pytest.mark.asyncio
class TestRetryLlm:
    """Tests for POST /api/v1/documents/{document_id}/card/retry-llm."""

    async def test_successful_retry_returns_200(
        self, app, mock_base_analysis_service, mock_base_analysis_storage, mock_storage_service
    ):
        """A successful LLM retry returns 200 with the updated card."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        partial_card = _make_card(
            document_id=doc_id, status="partial", summary=None, classification=None
        )
        updated_card = _make_card(document_id=doc_id, status="completed")

        mock_base_analysis_storage.get_card.return_value = partial_card
        mock_storage_service.get_ir.return_value = IntermediateRepresentation(
            document_id=doc_id,
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=5000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                warnings=[],
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-000",
                    text="# Hello",
                    structural_context={"section": "Hello"},
                    order=0,
                )
            ],
        )
        mock_base_analysis_service.retry_llm.return_value = updated_card

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["summary"] == "A test document summary."

    async def test_card_not_found_returns_404(
        self, app, mock_base_analysis_storage, mock_storage_service
    ):
        """No card exists returns 404 with card_not_found."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_base_analysis_storage.get_card.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "card_not_found"

    async def test_card_already_complete_returns_409(
        self, app, mock_base_analysis_storage, mock_storage_service
    ):
        """A card with status 'completed' returns 409."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_base_analysis_storage.get_card.return_value = _make_card(
            document_id=doc_id, status="completed"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "card_already_complete"

    async def test_invalid_uuid_returns_404(self, app):
        """An invalid UUID format returns 404 with card_not_found."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/not-a-uuid/card/retry-llm"
            )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "card_not_found"

    async def test_failed_llm_card_allows_retry(
        self, app, mock_base_analysis_service, mock_base_analysis_storage, mock_storage_service
    ):
        """A card with status 'failed_llm' can be retried."""
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        failed_card = _make_card(
            document_id=doc_id, status="failed_llm", summary=None, classification=None
        )
        updated_card = _make_card(document_id=doc_id, status="completed")

        mock_base_analysis_storage.get_card.return_value = failed_card
        mock_storage_service.get_ir.return_value = IntermediateRepresentation(
            document_id=doc_id,
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=5000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                warnings=[],
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-000",
                    text="# Hello",
                    structural_context={"section": "Hello"},
                    order=0,
                )
            ],
        )
        mock_base_analysis_service.retry_llm.return_value = updated_card

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v1/documents/{doc_id}/card/retry-llm")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
