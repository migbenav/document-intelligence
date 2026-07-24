"""Integration test fixtures for ingestion flow.

Provides a FakeStorageService that stores data in-memory so the full
pipeline can be tested without Supabase credentials.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.v1.documents import _get_ingestion_service, _get_storage_service
from app.ingestion.adapters.markdown_adapter import MarkdownAdapter
from app.ingestion.adapters.pdf_adapter import PdfAdapter
from app.ingestion.adapters.plaintext_adapter import PlainTextAdapter
from app.ingestion.ir_builder import IRBuilder
from app.ingestion.language import LanguageDetector
from app.ingestion.service import IngestionService
from app.ingestion.validator import Validator
from app.main import create_app
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    DocumentStatus,
    IntermediateRepresentation,
)


class FakeStorageService:
    """In-memory fake that implements the StorageService interface.

    Stores documents, chunks, and original files in plain dicts so that
    integration tests can exercise the full pipeline without a database.
    """

    def __init__(self) -> None:
        # document_id -> record dict
        self._documents: dict[str, dict] = {}
        # document_id -> list of chunk dicts
        self._chunks: dict[str, list[dict]] = {}
        # document_id -> file bytes
        self._files: dict[str, bytes] = {}

    async def store_original(
        self, document_id: str, file_bytes: bytes, filename: str
    ) -> None:
        self._files[document_id] = file_bytes

    async def create_document_record(
        self,
        document_id: str,
        filename: str,
        format: DocumentFormat,
        size_bytes: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._documents[document_id] = {
            "document_id": document_id,
            "original_filename": filename,
            "format": format.value,
            "size_bytes": size_bytes,
            "language": "unknown",
            "upload_timestamp": now.isoformat(),
            "warnings": [],
            "status": "processing",
            "error_message": None,
            "expires_at": (now + timedelta(hours=24)).isoformat(),
        }

    async def persist_ir(self, ir: IntermediateRepresentation) -> None:
        doc_id = ir.document_id
        if doc_id in self._documents:
            self._documents[doc_id].update(
                {
                    "language": ir.metadata.language.value,
                    "warnings": ir.metadata.warnings,
                    "status": "ready",
                }
            )
        self._chunks[doc_id] = [
            {
                "document_id": doc_id,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "structural_context": chunk.structural_context,
                "order": chunk.order,
            }
            for chunk in ir.chunks
        ]

    async def mark_failed(self, document_id: str, error_message: str) -> None:
        if document_id in self._documents:
            self._documents[document_id]["status"] = "failed"
            self._documents[document_id]["error_message"] = error_message

    async def get_status(self, document_id: str) -> DocumentStatus | None:
        row = self._documents.get(document_id)
        if row is None:
            return None

        chunk_count = None
        if row["status"] == "ready":
            chunk_count = len(self._chunks.get(document_id, []))

        return DocumentStatus(
            document_id=row["document_id"],
            status=row["status"],
            filename=row["original_filename"],
            format=row["format"],
            language=row.get("language"),
            chunk_count=chunk_count,
            warnings=row.get("warnings", []),
            error_message=row.get("error_message"),
        )

    async def get_ir(self, document_id: str) -> IntermediateRepresentation | None:
        row = self._documents.get(document_id)
        if row is None:
            return None
        if row["status"] != "ready":
            return None

        chunks_data = self._chunks.get(document_id, [])

        metadata = DocumentMetadata(
            original_filename=row["original_filename"],
            format=DocumentFormat(row["format"]),
            size_bytes=row["size_bytes"],
            language=DetectedLanguage(row["language"]),
            upload_timestamp=datetime.fromisoformat(row["upload_timestamp"]),
            warnings=row.get("warnings", []),
        )

        chunks = [
            ContentChunkModel(
                chunk_id=c["chunk_id"],
                text=c["text"],
                structural_context=c["structural_context"],
                order=c["order"],
            )
            for c in chunks_data
        ]

        return IntermediateRepresentation(
            document_id=document_id,
            metadata=metadata,
            chunks=chunks,
        )

    async def delete_expired(self) -> int:
        # Not needed for integration tests
        return 0


@pytest.fixture
def fake_storage():
    """Create a fresh FakeStorageService instance."""
    return FakeStorageService()


@pytest.fixture
def app(fake_storage):
    """Create a FastAPI app with the fake storage service wired in."""
    application = create_app()

    ingestion_service = IngestionService(
        validator=Validator(),
        adapters=[MarkdownAdapter(), PlainTextAdapter(), PdfAdapter()],
        language_detector=LanguageDetector(),
        ir_builder=IRBuilder(),
        storage_service=fake_storage,
    )

    application.dependency_overrides[_get_ingestion_service] = lambda: ingestion_service
    application.dependency_overrides[_get_storage_service] = lambda: fake_storage

    return application


@pytest_asyncio.fixture
async def async_client(app):
    """Create an httpx AsyncClient for testing the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
