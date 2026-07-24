"""Unit tests for document ingestion Pydantic models.

Verifies model instantiation, JSON serialization matching API response format,
enum values, and optional field behavior.
"""

import json
from datetime import datetime, timezone

from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    DocumentStatus,
    IntermediateRepresentation,
    ValidationErrorResponse,
)


class TestDocumentFormatEnum:
    """Tests for DocumentFormat enum values."""

    def test_markdown_value(self):
        assert DocumentFormat.MARKDOWN == "markdown"
        assert DocumentFormat.MARKDOWN.value == "markdown"

    def test_plain_text_value(self):
        assert DocumentFormat.PLAIN_TEXT == "plain_text"
        assert DocumentFormat.PLAIN_TEXT.value == "plain_text"

    def test_pdf_value(self):
        assert DocumentFormat.PDF == "pdf"
        assert DocumentFormat.PDF.value == "pdf"

    def test_all_formats_covered(self):
        values = {f.value for f in DocumentFormat}
        assert values == {"markdown", "plain_text", "pdf"}


class TestDetectedLanguageEnum:
    """Tests for DetectedLanguage enum values."""

    def test_spanish_value(self):
        assert DetectedLanguage.SPANISH == "es"
        assert DetectedLanguage.SPANISH.value == "es"

    def test_english_value(self):
        assert DetectedLanguage.ENGLISH == "en"
        assert DetectedLanguage.ENGLISH.value == "en"

    def test_unknown_value(self):
        assert DetectedLanguage.UNKNOWN == "unknown"
        assert DetectedLanguage.UNKNOWN.value == "unknown"


class TestContentChunkModel:
    """Tests for ContentChunkModel instantiation and serialization."""

    def test_instantiation(self):
        chunk = ContentChunkModel(
            chunk_id="chunk-001",
            text="# Product Requirements\n\nThis document defines...",
            structural_context={"section": "# Product Requirements"},
            order=0,
        )
        assert chunk.chunk_id == "chunk-001"
        assert chunk.text == "# Product Requirements\n\nThis document defines..."
        assert chunk.structural_context == {"section": "# Product Requirements"}
        assert chunk.order == 0

    def test_json_serialization(self):
        chunk = ContentChunkModel(
            chunk_id="chunk-001",
            text="# Product Requirements\n\nThis document defines...",
            structural_context={"section": "# Product Requirements"},
            order=0,
        )
        data = chunk.model_dump()
        assert data == {
            "chunk_id": "chunk-001",
            "text": "# Product Requirements\n\nThis document defines...",
            "structural_context": {"section": "# Product Requirements"},
            "order": 0,
        }

    def test_pdf_structural_context(self):
        chunk = ContentChunkModel(
            chunk_id="chunk-003",
            text="Page content here",
            structural_context={"page": 2},
            order=2,
        )
        data = chunk.model_dump()
        assert data["structural_context"] == {"page": 2}


class TestDocumentMetadata:
    """Tests for DocumentMetadata instantiation and serialization."""

    def test_instantiation_with_defaults(self):
        metadata = DocumentMetadata(
            original_filename="my-prd.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=15234,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert metadata.original_filename == "my-prd.md"
        assert metadata.format == DocumentFormat.MARKDOWN
        assert metadata.size_bytes == 15234
        assert metadata.language == DetectedLanguage.SPANISH
        assert metadata.warnings == []

    def test_instantiation_with_warnings(self):
        metadata = DocumentMetadata(
            original_filename="report.pdf",
            format=DocumentFormat.PDF,
            size_bytes=5000000,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc),
            warnings=["Complex table skipped on page 3"],
        )
        assert metadata.warnings == ["Complex table skipped on page 3"]

    def test_json_serialization_matches_api_format(self):
        metadata = DocumentMetadata(
            original_filename="my-prd.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=15234,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc),
            warnings=[],
        )
        data = json.loads(metadata.model_dump_json())
        assert data["original_filename"] == "my-prd.md"
        assert data["format"] == "markdown"
        assert data["size_bytes"] == 15234
        assert data["language"] == "es"
        assert data["warnings"] == []
        # Timestamp should serialize as ISO 8601
        assert "2026-07-23" in data["upload_timestamp"]


class TestIntermediateRepresentation:
    """Tests for IntermediateRepresentation and its JSON serialization."""

    def _make_ir(self) -> IntermediateRepresentation:
        return IntermediateRepresentation(
            document_id="uuid-here",
            metadata=DocumentMetadata(
                original_filename="my-prd.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=15234,
                language=DetectedLanguage.SPANISH,
                upload_timestamp=datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc),
                warnings=[],
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="# Product Requirements\n\nThis document defines...",
                    structural_context={"section": "# Product Requirements"},
                    order=0,
                )
            ],
        )

    def test_instantiation(self):
        ir = self._make_ir()
        assert ir.document_id == "uuid-here"
        assert ir.metadata.original_filename == "my-prd.md"
        assert len(ir.chunks) == 1
        assert ir.chunks[0].chunk_id == "chunk-001"

    def test_json_serialization_matches_api_format(self):
        """Verify JSON output matches the IR response format from design.md."""
        ir = self._make_ir()
        data = json.loads(ir.model_dump_json())

        assert data["document_id"] == "uuid-here"
        assert data["metadata"]["original_filename"] == "my-prd.md"
        assert data["metadata"]["format"] == "markdown"
        assert data["metadata"]["size_bytes"] == 15234
        assert data["metadata"]["language"] == "es"
        assert data["metadata"]["upload_timestamp"] == "2026-07-23T10:00:00Z"
        assert data["metadata"]["warnings"] == []
        assert len(data["chunks"]) == 1
        assert data["chunks"][0]["chunk_id"] == "chunk-001"
        assert data["chunks"][0]["text"] == "# Product Requirements\n\nThis document defines..."
        assert data["chunks"][0]["structural_context"] == {"section": "# Product Requirements"}
        assert data["chunks"][0]["order"] == 0

    def test_multiple_chunks_ordering(self):
        ir = IntermediateRepresentation(
            document_id="doc-123",
            metadata=DocumentMetadata(
                original_filename="report.pdf",
                format=DocumentFormat.PDF,
                size_bytes=5000000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-000",
                    text="Page 1 content",
                    structural_context={"page": 1},
                    order=0,
                ),
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="Page 2 content",
                    structural_context={"page": 2},
                    order=1,
                ),
            ],
        )
        data = ir.model_dump()
        assert len(data["chunks"]) == 2
        assert data["chunks"][0]["order"] == 0
        assert data["chunks"][1]["order"] == 1


class TestDocumentStatus:
    """Tests for DocumentStatus API response model."""

    def test_minimal_status_processing(self):
        status = DocumentStatus(
            document_id="uuid-here",
            status="processing",
            filename="my-prd.md",
            format="markdown",
        )
        assert status.language is None
        assert status.chunk_count is None
        assert status.warnings == []
        assert status.error_message is None

    def test_ready_status_json_matches_api_format(self):
        """Verify JSON output matches the status response from design.md."""
        status = DocumentStatus(
            document_id="uuid-here",
            status="ready",
            filename="my-prd.md",
            format="markdown",
            language="es",
            chunk_count=12,
            warnings=["Complex table skipped on page 3"],
        )
        data = json.loads(status.model_dump_json(exclude_none=True))
        assert data == {
            "document_id": "uuid-here",
            "status": "ready",
            "filename": "my-prd.md",
            "format": "markdown",
            "language": "es",
            "chunk_count": 12,
            "warnings": ["Complex table skipped on page 3"],
        }

    def test_failed_status_with_error(self):
        status = DocumentStatus(
            document_id="uuid-here",
            status="failed",
            filename="broken.pdf",
            format="pdf",
            error_message="Scanned PDF detected — no selectable text",
        )
        data = status.model_dump(exclude_none=True)
        assert data["status"] == "failed"
        assert data["error_message"] == "Scanned PDF detected — no selectable text"


class TestValidationErrorResponse:
    """Tests for ValidationErrorResponse model."""

    def test_unsupported_format_error(self):
        err = ValidationErrorResponse(
            error="unsupported_format",
            message="File format .docx is not supported.",
            supported_formats=[".md", ".txt", ".pdf"],
        )
        data = json.loads(err.model_dump_json(exclude_none=True))
        assert data == {
            "error": "unsupported_format",
            "message": "File format .docx is not supported.",
            "supported_formats": [".md", ".txt", ".pdf"],
        }

    def test_file_too_large_error(self):
        err = ValidationErrorResponse(
            error="file_too_large",
            message="File exceeds the maximum size of 1 MB for text files.",
            max_size_bytes=1048576,
        )
        data = json.loads(err.model_dump_json(exclude_none=True))
        assert data == {
            "error": "file_too_large",
            "message": "File exceeds the maximum size of 1 MB for text files.",
            "max_size_bytes": 1048576,
        }

    def test_invalid_encoding_error(self):
        err = ValidationErrorResponse(
            error="invalid_encoding",
            message="File must be encoded in UTF-8.",
            required_encoding="utf-8",
        )
        data = json.loads(err.model_dump_json(exclude_none=True))
        assert data == {
            "error": "invalid_encoding",
            "message": "File must be encoded in UTF-8.",
            "required_encoding": "utf-8",
        }

    def test_scanned_pdf_error_minimal(self):
        err = ValidationErrorResponse(
            error="scanned_pdf",
            message="Scanned PDFs without selectable text are not supported.",
        )
        data = json.loads(err.model_dump_json(exclude_none=True))
        assert data == {
            "error": "scanned_pdf",
            "message": "Scanned PDFs without selectable text are not supported.",
        }

    def test_optional_fields_are_none_by_default(self):
        err = ValidationErrorResponse(
            error="extraction_failed",
            message="Could not extract text from the document.",
        )
        assert err.supported_formats is None
        assert err.max_size_bytes is None
        assert err.required_encoding is None
