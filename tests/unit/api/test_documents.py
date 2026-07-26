"""Unit tests for the document API endpoints.

Tests the upload, status, and IR retrieval endpoints using
mocked IngestionService and StorageService dependencies.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.documents import (
    _get_base_analysis_service,
    _get_ingestion_service,
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


@pytest.fixture
def mock_ingestion_service():
    """Create a mock IngestionService."""
    return AsyncMock()


@pytest.fixture
def mock_storage_service():
    """Create a mock StorageService."""
    return AsyncMock()


@pytest.fixture
def mock_base_analysis_service():
    """Create a mock BaseAnalysisService."""
    return AsyncMock()


@pytest.fixture
def app(mock_ingestion_service, mock_storage_service, mock_base_analysis_service):
    """Create a test FastAPI app with mocked dependencies."""
    test_app = create_app()
    test_app.dependency_overrides[_get_ingestion_service] = lambda: mock_ingestion_service
    test_app.dependency_overrides[_get_storage_service] = lambda: mock_storage_service
    test_app.dependency_overrides[_get_base_analysis_service] = lambda: mock_base_analysis_service
    return test_app


# --- Upload endpoint tests ---


@pytest.mark.asyncio
class TestUploadEndpoint:
    """Tests for POST /api/v1/documents/upload."""

    async def test_successful_upload_returns_202(
        self, app, mock_ingestion_service
    ):
        """A valid file upload returns 202 with DocumentStatus."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="abc-123",
            status="processing",
            filename="test.md",
            format="markdown",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.md", b"# Hello World", "text/markdown")},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["document_id"] == "abc-123"
        assert data["status"] == "processing"
        assert data["filename"] == "test.md"
        assert data["format"] == "markdown"

    async def test_successful_upload_with_ready_status(
        self, app, mock_ingestion_service
    ):
        """Upload that completes immediately returns 202 with ready status."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="abc-123",
            status="ready",
            filename="test.md",
            format="markdown",
            language="en",
            chunk_count=3,
            warnings=[],
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.md", b"# Hello", "text/markdown")},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "ready"
        assert data["language"] == "en"
        assert data["chunk_count"] == 3

    async def test_unsupported_format_returns_400(
        self, app, mock_ingestion_service
    ):
        """Uploading an unsupported format returns 400 with error details."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="abc-123",
            status="failed",
            filename="test.docx",
            format="unknown",
            error_message=(
                "File format '.docx' is not supported. "
                "Please upload a file with one of these extensions: .md, .txt, .pdf"
            ),
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.docx", b"content", "application/vnd.openxmlformats")},
            )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "unsupported_format"
        assert "not supported" in data["message"]
        assert data["supported_formats"] == [".md", ".txt", ".pdf"]

    async def test_file_too_large_returns_400(
        self, app, mock_ingestion_service
    ):
        """Uploading a file that exceeds size limits returns 400."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="abc-123",
            status="failed",
            filename="huge.md",
            format="unknown",
            error_message=(
                "File exceeds the maximum allowed size of 1 MB "
                "for .md files. Please reduce the file size and try again."
            ),
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("huge.md", b"x" * 100, "text/markdown")},
            )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "file_too_large"
        assert "max_size_bytes" in data

    async def test_invalid_encoding_returns_400(
        self, app, mock_ingestion_service
    ):
        """Uploading a non-UTF-8 file returns 400 with encoding info."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="abc-123",
            status="failed",
            filename="bad.txt",
            format="unknown",
            error_message=(
                "File is not valid UTF-8 encoded text. "
                "Please save the file with UTF-8 encoding and try again."
            ),
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("bad.txt", b"\xff\xfe", "text/plain")},
            )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_encoding"
        assert data["required_encoding"] == "utf-8"

    async def test_extraction_failure_returns_422(
        self, app, mock_ingestion_service
    ):
        """An extraction failure returns 422."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="abc-123",
            status="failed",
            filename="corrupt.pdf",
            format="pdf",
            error_message="Extraction failed: could not parse PDF structure",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("corrupt.pdf", b"%PDF-1.4", "application/pdf")},
            )

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "extraction_failed"
        assert "message" in data

    async def test_scanned_pdf_returns_400(
        self, app, mock_ingestion_service
    ):
        """A scanned PDF returns 400 with scanned_pdf error."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="abc-123",
            status="failed",
            filename="scanned.pdf",
            format="pdf",
            error_message="This appears to be a scanned PDF with no extractable text.",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("scanned.pdf", b"%PDF-1.4", "application/pdf")},
            )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "scanned_pdf"


# --- Status endpoint tests ---


@pytest.mark.asyncio
class TestStatusEndpoint:
    """Tests for GET /api/v1/documents/{document_id}/status."""

    async def test_existing_document_returns_200(
        self, app, mock_storage_service
    ):
        """An existing document returns its status."""
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id="doc-001",
            status="ready",
            filename="report.md",
            format="markdown",
            language="en",
            chunk_count=5,
            warnings=[],
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-001/status")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc-001"
        assert data["status"] == "ready"
        assert data["chunk_count"] == 5

    async def test_nonexistent_document_returns_404(
        self, app, mock_storage_service
    ):
        """A non-existent document returns 404."""
        mock_storage_service.get_status.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/nonexistent-id/status")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"

    async def test_processing_document_returns_200(
        self, app, mock_storage_service
    ):
        """A document still processing returns 200 with processing status."""
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id="doc-002",
            status="processing",
            filename="big.pdf",
            format="pdf",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-002/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"


# --- IR endpoint tests ---


@pytest.mark.asyncio
class TestIREndpoint:
    """Tests for GET /api/v1/documents/{document_id}/ir."""

    async def test_ready_document_returns_ir(
        self, app, mock_storage_service
    ):
        """A ready document returns its full IR."""
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id="doc-001",
            status="ready",
            filename="report.md",
            format="markdown",
            language="en",
            chunk_count=1,
        )

        mock_storage_service.get_ir.return_value = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="report.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1024,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                warnings=[],
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-000",
                    text="# Hello World\n\nSome content.",
                    structural_context={"section": "# Hello World"},
                    order=0,
                )
            ],
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-001/ir")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc-001"
        assert data["metadata"]["original_filename"] == "report.md"
        assert len(data["chunks"]) == 1
        assert data["chunks"][0]["chunk_id"] == "chunk-000"

    async def test_nonexistent_document_returns_404(
        self, app, mock_storage_service
    ):
        """A non-existent document returns 404."""
        mock_storage_service.get_status.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/nonexistent-id/ir")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"

    async def test_processing_document_returns_409(
        self, app, mock_storage_service
    ):
        """A document still processing returns 409 conflict."""
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id="doc-002",
            status="processing",
            filename="big.pdf",
            format="pdf",
        )
        mock_storage_service.get_ir.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-002/ir")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "not_ready"
        assert "processing" in data["message"]

    async def test_failed_document_returns_409(
        self, app, mock_storage_service
    ):
        """A failed document returns 409 conflict."""
        mock_storage_service.get_status.return_value = DocumentStatus(
            document_id="doc-003",
            status="failed",
            filename="bad.pdf",
            format="pdf",
            error_message="Extraction failed",
        )
        mock_storage_service.get_ir.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/documents/doc-003/ir")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "not_ready"
        assert "failed" in data["message"]
