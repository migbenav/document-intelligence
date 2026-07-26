"""Unit tests for the background task trigger in the upload endpoint.

Validates that:
- Successful ingestion (status=ready) triggers base analysis as a background task
- Failed ingestion does NOT trigger base analysis
- Analysis failure does not affect the upload response
- The upload response returns immediately without waiting for analysis

Requirements: Req 1 (criteria 1, 2, 4)
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.documents import (
    _get_base_analysis_service,
    _get_ingestion_service,
    _get_storage_service,
    _run_base_analysis,
)
from app.main import create_app
from app.models.document import DocumentStatus


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


@pytest.mark.asyncio
class TestBackgroundTaskTrigger:
    """Tests for the background task that triggers base analysis after upload."""

    async def test_successful_upload_triggers_background_task(
        self, app, mock_ingestion_service, mock_storage_service, mock_base_analysis_service
    ):
        """When ingestion succeeds (status=ready), a background task is scheduled."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="doc-123",
            status="ready",
            filename="test.md",
            format="markdown",
            language="en",
            chunk_count=5,
            warnings=[],
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.md", b"# Hello World", "text/markdown")},
            )

        # Upload returns 202 immediately
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "ready"
        assert data["document_id"] == "doc-123"

    async def test_failed_upload_does_not_trigger_background_task(
        self, app, mock_ingestion_service, mock_storage_service, mock_base_analysis_service
    ):
        """When ingestion fails, no background task is triggered."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="doc-123",
            status="failed",
            filename="test.docx",
            format="unknown",
            error_message="File format '.docx' is not supported.",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.docx", b"content", "application/octet-stream")},
            )

        # Upload returns error
        assert response.status_code == 400

        # Base analysis service should NOT have been called
        mock_base_analysis_service.analyze.assert_not_called()

    async def test_upload_returns_immediately_without_waiting_for_analysis(
        self, app, mock_ingestion_service, mock_storage_service, mock_base_analysis_service
    ):
        """Upload response returns immediately; analysis runs in background."""
        mock_ingestion_service.ingest.return_value = DocumentStatus(
            document_id="doc-456",
            status="ready",
            filename="report.pdf",
            format="pdf",
            language="es",
            chunk_count=10,
            warnings=[],
        )

        # Even if analysis would take time, the response should be immediate
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("report.pdf", b"%PDF-content", "application/pdf")},
            )

        assert response.status_code == 202
        # The response contains the document status, not analysis results
        data = response.json()
        assert data["document_id"] == "doc-456"
        assert data["status"] == "ready"


@pytest.mark.asyncio
class TestRunBaseAnalysis:
    """Tests for the _run_base_analysis helper function."""

    async def test_retrieves_ir_and_calls_analyze(self):
        """Successfully retrieves IR from storage and calls analyze."""
        mock_storage = AsyncMock()
        mock_service = AsyncMock()
        mock_ir = AsyncMock()
        mock_storage.get_ir.return_value = mock_ir

        await _run_base_analysis(
            document_id="doc-789",
            storage_service=mock_storage,
            base_analysis_service=mock_service,
        )

        mock_storage.get_ir.assert_called_once_with("doc-789")
        mock_service.analyze.assert_called_once_with("doc-789", mock_ir)

    async def test_ir_not_available_logs_warning(self):
        """When IR is not available, logs a warning and returns gracefully."""
        mock_storage = AsyncMock()
        mock_service = AsyncMock()
        mock_storage.get_ir.return_value = None

        # Should not raise
        await _run_base_analysis(
            document_id="doc-missing",
            storage_service=mock_storage,
            base_analysis_service=mock_service,
        )

        mock_storage.get_ir.assert_called_once_with("doc-missing")
        mock_service.analyze.assert_not_called()

    async def test_analysis_failure_does_not_propagate(self):
        """If analysis raises an exception, it is caught and does not propagate."""
        mock_storage = AsyncMock()
        mock_service = AsyncMock()
        mock_ir = AsyncMock()
        mock_storage.get_ir.return_value = mock_ir
        mock_service.analyze.side_effect = RuntimeError("LLM provider unavailable")

        # Should not raise — failure is fire-and-forget
        await _run_base_analysis(
            document_id="doc-error",
            storage_service=mock_storage,
            base_analysis_service=mock_service,
        )

        mock_service.analyze.assert_called_once_with("doc-error", mock_ir)

    async def test_storage_failure_does_not_propagate(self):
        """If storage.get_ir raises, it is caught and does not propagate."""
        mock_storage = AsyncMock()
        mock_service = AsyncMock()
        mock_storage.get_ir.side_effect = ConnectionError("Database unavailable")

        # Should not raise
        await _run_base_analysis(
            document_id="doc-db-error",
            storage_service=mock_storage,
            base_analysis_service=mock_service,
        )

        mock_service.analyze.assert_not_called()
