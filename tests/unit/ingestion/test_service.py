"""Unit tests for the IngestionService pipeline orchestrator."""

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.adapters.base import ContentChunk, ExtractionResult, FormatAdapter
from app.ingestion.ir_builder import IRBuilder
from app.ingestion.language import LanguageDetector
from app.ingestion.service import IngestionService
from app.ingestion.storage import StorageService
from app.ingestion.validator import ValidationResult, Validator
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    DocumentStatus,
    IntermediateRepresentation,
)


# --- Helpers / Fixtures ---


class FakeMarkdownAdapter(FormatAdapter):
    """A fake adapter that handles .md files."""

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        return filename.endswith(".md")

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        return ExtractionResult(
            chunks=[
                ContentChunk(
                    chunk_id="chunk-000",
                    text="# Hello\n\nSome content.",
                    structural_context={"section": "# Hello"},
                    order=0,
                ),
            ],
            warnings=[],
        )


class FailingAdapter(FormatAdapter):
    """An adapter that always raises during extraction."""

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        return filename.endswith(".md")

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        raise RuntimeError("PDF is corrupted")


class NoMatchAdapter(FormatAdapter):
    """An adapter that never matches any file."""

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        return False

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        return ExtractionResult(chunks=[], warnings=[])


@pytest.fixture
def mock_storage() -> StorageService:
    """Create a StorageService with all async methods mocked."""
    storage = MagicMock(spec=StorageService)
    storage.create_document_record = AsyncMock()
    storage.store_original = AsyncMock()
    storage.persist_ir = AsyncMock()
    storage.mark_failed = AsyncMock()
    return storage


@pytest.fixture
def validator() -> Validator:
    return Validator()


@pytest.fixture
def language_detector() -> LanguageDetector:
    return LanguageDetector()


@pytest.fixture
def ir_builder() -> IRBuilder:
    return IRBuilder()


@pytest.fixture
def service(mock_storage, validator, language_detector, ir_builder) -> IngestionService:
    """Default service with a FakeMarkdownAdapter."""
    return IngestionService(
        validator=validator,
        adapters=[FakeMarkdownAdapter()],
        language_detector=language_detector,
        ir_builder=ir_builder,
        storage_service=mock_storage,
    )


# --- Tests ---


class TestSuccessfulIngestion:
    """Tests for the happy path of the ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_ingest_markdown_returns_ready_status(self, service, mock_storage):
        content = b"# Hello\n\nSome content here."
        result = await service.ingest(content, "readme.md", "text/markdown")

        assert result.status == "ready"
        assert result.filename == "readme.md"
        assert result.format == "markdown"
        assert result.chunk_count == 1
        assert result.warnings == []
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_ingest_assigns_uuid(self, service, mock_storage):
        content = b"# Hello\n\nSome content here."
        result = await service.ingest(content, "readme.md", None)

        # document_id should be a valid UUID string
        import uuid

        parsed = uuid.UUID(result.document_id)
        assert str(parsed) == result.document_id

    @pytest.mark.asyncio
    async def test_ingest_creates_document_record(self, service, mock_storage):
        content = b"# Hello\n\nSome content here."
        result = await service.ingest(content, "readme.md", None)

        mock_storage.create_document_record.assert_called_once_with(
            document_id=result.document_id,
            filename="readme.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=len(content),
        )

    @pytest.mark.asyncio
    async def test_ingest_stores_original(self, service, mock_storage):
        content = b"# Hello\n\nSome content here."
        result = await service.ingest(content, "readme.md", None)

        mock_storage.store_original.assert_called_once_with(
            document_id=result.document_id,
            file_bytes=content,
            filename="readme.md",
        )

    @pytest.mark.asyncio
    async def test_ingest_persists_ir(self, service, mock_storage):
        content = b"# Hello\n\nSome content here."
        await service.ingest(content, "readme.md", None)

        mock_storage.persist_ir.assert_called_once()
        ir = mock_storage.persist_ir.call_args[0][0]
        assert isinstance(ir, IntermediateRepresentation)
        assert ir.metadata.format == DocumentFormat.MARKDOWN
        assert len(ir.chunks) == 1

    @pytest.mark.asyncio
    async def test_ingest_detects_language(self, service, mock_storage):
        """Language detection runs on extracted chunk text."""
        content = b"# Hello\n\nThe project is a system for managing documents and files."
        result = await service.ingest(content, "readme.md", None)

        # The fake adapter returns fixed text, so language depends on that
        # "# Hello\n\nSome content." is too short for confident detection
        # but the service should still complete successfully
        assert result.status == "ready"
        assert result.language is not None


class TestValidationFailure:
    """Tests for validation short-circuit behavior."""

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_failed(self, service, mock_storage):
        content = b"some content"
        result = await service.ingest(content, "image.png", None)

        assert result.status == "failed"
        assert "not supported" in result.error_message
        assert result.format == "unknown"

    @pytest.mark.asyncio
    async def test_validation_failure_does_not_store(self, service, mock_storage):
        """Validation failures should not create records or store files."""
        content = b"some content"
        await service.ingest(content, "image.png", None)

        mock_storage.create_document_record.assert_not_called()
        mock_storage.store_original.assert_not_called()
        mock_storage.persist_ir.assert_not_called()

    @pytest.mark.asyncio
    async def test_file_too_large_returns_failed(self, service, mock_storage):
        # 1 MB + 1 byte for .md files
        content = b"x" * (1_048_576 + 1)
        result = await service.ingest(content, "big.md", None)

        assert result.status == "failed"
        assert "size" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_invalid_encoding_returns_failed(self, service, mock_storage):
        # Invalid UTF-8 bytes
        content = b"\xff\xfe invalid utf-8 \x80\x81"
        result = await service.ingest(content, "bad.txt", None)

        assert result.status == "failed"
        assert "utf-8" in result.error_message.lower()


class TestExtractionFailure:
    """Tests for extraction error handling."""

    @pytest.mark.asyncio
    async def test_extraction_exception_marks_failed(self, mock_storage, validator, language_detector, ir_builder):
        service = IngestionService(
            validator=validator,
            adapters=[FailingAdapter()],
            language_detector=language_detector,
            ir_builder=ir_builder,
            storage_service=mock_storage,
        )

        content = b"# Hello\n\nContent"
        result = await service.ingest(content, "readme.md", None)

        assert result.status == "failed"
        assert "Extraction failed" in result.error_message
        mock_storage.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_matching_adapter_marks_failed(self, mock_storage, validator, language_detector, ir_builder):
        service = IngestionService(
            validator=validator,
            adapters=[NoMatchAdapter()],
            language_detector=language_detector,
            ir_builder=ir_builder,
            storage_service=mock_storage,
        )

        content = b"# Hello\n\nContent"
        result = await service.ingest(content, "readme.md", None)

        assert result.status == "failed"
        assert "No adapter available" in result.error_message
        mock_storage.mark_failed.assert_called_once()


class TestAdapterSelection:
    """Tests for adapter selection logic."""

    @pytest.mark.asyncio
    async def test_selects_correct_adapter_by_filename(self, mock_storage, validator, language_detector, ir_builder):
        """When multiple adapters exist, the matching one is selected."""

        class TxtAdapter(FormatAdapter):
            def can_handle(self, filename, content_type):
                return filename.endswith(".txt")

            def extract(self, file_bytes, filename):
                return ExtractionResult(
                    chunks=[
                        ContentChunk(
                            chunk_id="chunk-000",
                            text="Plain text content here.",
                            structural_context={"section": "(document)"},
                            order=0,
                        )
                    ],
                    warnings=[],
                )

        service = IngestionService(
            validator=validator,
            adapters=[FakeMarkdownAdapter(), TxtAdapter()],
            language_detector=language_detector,
            ir_builder=ir_builder,
            storage_service=mock_storage,
        )

        content = b"Plain text content here."
        result = await service.ingest(content, "notes.txt", "text/plain")

        assert result.status == "ready"
        assert result.format == "plain_text"

    @pytest.mark.asyncio
    async def test_content_type_passed_to_adapter(self, mock_storage, validator, language_detector, ir_builder):
        """Content type is forwarded to adapter's can_handle."""

        class ContentTypeAdapter(FormatAdapter):
            def can_handle(self, filename, content_type):
                return content_type == "text/markdown"

            def extract(self, file_bytes, filename):
                return ExtractionResult(
                    chunks=[
                        ContentChunk(
                            chunk_id="chunk-000",
                            text="Content.",
                            structural_context={"section": "(preamble)"},
                            order=0,
                        )
                    ],
                    warnings=[],
                )

        service = IngestionService(
            validator=validator,
            adapters=[ContentTypeAdapter()],
            language_detector=language_detector,
            ir_builder=ir_builder,
            storage_service=mock_storage,
        )

        content = b"# Doc content"
        result = await service.ingest(content, "file.md", "text/markdown")

        assert result.status == "ready"


class TestWarningsHandling:
    """Tests for extraction warnings propagation."""

    @pytest.mark.asyncio
    async def test_warnings_propagated_to_status(self, mock_storage, validator, language_detector, ir_builder):
        class WarningAdapter(FormatAdapter):
            def can_handle(self, filename, content_type):
                return filename.endswith(".md")

            def extract(self, file_bytes, filename):
                return ExtractionResult(
                    chunks=[
                        ContentChunk(
                            chunk_id="chunk-000",
                            text="Some text.",
                            structural_context={"section": "# Title"},
                            order=0,
                        )
                    ],
                    warnings=["Complex table skipped on page 3"],
                )

        service = IngestionService(
            validator=validator,
            adapters=[WarningAdapter()],
            language_detector=language_detector,
            ir_builder=ir_builder,
            storage_service=mock_storage,
        )

        content = b"# Some text"
        result = await service.ingest(content, "doc.md", None)

        assert result.status == "ready"
        assert "Complex table skipped on page 3" in result.warnings
