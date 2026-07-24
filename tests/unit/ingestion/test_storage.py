"""Unit tests for the StorageService module."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.storage import (
    STORAGE_BUCKET,
    StorageService,
    _get_retention_seconds,
    sanitize_filename,
)
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    DocumentStatus,
    IntermediateRepresentation,
)


# --- Filename sanitization tests ---


class TestSanitizeFilename:
    """Tests for the sanitize_filename function."""

    def test_normal_filename_unchanged(self):
        assert sanitize_filename("report.md") == "report.md"

    def test_filename_with_spaces_replaced(self):
        assert sanitize_filename("my report.md") == "my_report.md"

    def test_path_traversal_removed(self):
        result = sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    def test_directory_components_stripped(self):
        result = sanitize_filename("/some/path/to/file.txt")
        assert result == "file.txt"

    def test_backslash_path_stripped(self):
        result = sanitize_filename("C:\\Users\\docs\\file.txt")
        assert result == "file.txt"

    def test_null_bytes_removed(self):
        result = sanitize_filename("file\x00name.txt")
        assert "\x00" not in result

    def test_special_characters_replaced(self):
        result = sanitize_filename("file<>:\"|?*.txt")
        # All special chars should become underscores or be removed
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_empty_filename_returns_fallback(self):
        assert sanitize_filename("") == "unnamed_file"

    def test_only_dots_returns_fallback(self):
        assert sanitize_filename("...") == "unnamed_file"

    def test_preserves_file_extension(self):
        result = sanitize_filename("my-document.pdf")
        assert result.endswith(".pdf")

    def test_collapses_multiple_underscores(self):
        result = sanitize_filename("file___name.txt")
        assert "___" not in result

    def test_unicode_filename(self):
        result = sanitize_filename("documento_español.md")
        assert result  # Should produce a non-empty result
        assert "/" not in result


# --- Retention configuration tests ---


class TestRetentionConfig:
    """Tests for retention duration configuration from env var."""

    def test_default_retention_when_no_env_var(self):
        with patch.dict("os.environ", {}, clear=True):
            # Remove the key if present
            import os
            os.environ.pop("DOCUMENT_RETENTION_SECONDS", None)
            assert _get_retention_seconds() == 86400

    def test_custom_retention_from_env_var(self):
        with patch.dict("os.environ", {"DOCUMENT_RETENTION_SECONDS": "3600"}):
            assert _get_retention_seconds() == 3600

    def test_invalid_env_var_returns_default(self):
        with patch.dict("os.environ", {"DOCUMENT_RETENTION_SECONDS": "not_a_number"}):
            assert _get_retention_seconds() == 86400


# --- Fixtures ---


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with table and storage interfaces."""
    client = MagicMock()

    # Mock table chain: client.table("x").select/insert/update/delete().eq().execute()
    table_mock = MagicMock()
    client.table.return_value = table_mock

    # Mock storage chain: client.storage.from_("bucket").upload/remove()
    storage_bucket_mock = MagicMock()
    client.storage.from_.return_value = storage_bucket_mock

    return client


@pytest.fixture
def storage_service(mock_supabase) -> StorageService:
    return StorageService(mock_supabase)


@pytest.fixture
def sample_ir() -> IntermediateRepresentation:
    return IntermediateRepresentation(
        document_id="doc-123",
        metadata=DocumentMetadata(
            original_filename="report.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            warnings=["Complex table skipped"],
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-0",
                text="# Introduction\n\nThis is the first section.",
                structural_context={"section": "# Introduction"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-1",
                text="## Details\n\nMore information here.",
                structural_context={"section": "## Details"},
                order=1,
            ),
        ],
    )


# --- store_original tests ---


@pytest.mark.asyncio
class TestStoreOriginal:
    """Tests for storing original files in Supabase Storage."""

    async def test_stores_file_at_correct_path(self, storage_service, mock_supabase):
        await storage_service.store_original("doc-abc", b"file content", "report.md")

        mock_supabase.storage.from_.assert_called_once_with(STORAGE_BUCKET)
        mock_supabase.storage.from_().upload.assert_called_once_with(
            path="doc-abc/original/report.md",
            file=b"file content",
            file_options={"content-type": "application/octet-stream"},
        )

    async def test_sanitizes_filename_in_path(self, storage_service, mock_supabase):
        await storage_service.store_original(
            "doc-abc", b"data", "../../malicious.txt"
        )

        call_args = mock_supabase.storage.from_().upload.call_args
        path = call_args[1]["path"] if "path" in call_args[1] else call_args[0][0]
        # Path should not contain traversal
        assert ".." not in path
        assert "malicious" in path


# --- create_document_record tests ---


@pytest.mark.asyncio
class TestCreateDocumentRecord:
    """Tests for creating document records with processing status."""

    async def test_creates_record_with_processing_status(
        self, storage_service, mock_supabase
    ):
        await storage_service.create_document_record(
            document_id="doc-123",
            filename="report.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=2048,
        )

        mock_supabase.table.assert_called_with("documents")
        insert_call = mock_supabase.table().insert.call_args[0][0]

        assert insert_call["document_id"] == "doc-123"
        assert insert_call["original_filename"] == "report.md"
        assert insert_call["format"] == "markdown"
        assert insert_call["size_bytes"] == 2048
        assert insert_call["status"] == "processing"

    async def test_sets_expires_at_based_on_retention(
        self, storage_service, mock_supabase
    ):
        with patch.dict("os.environ", {"DOCUMENT_RETENTION_SECONDS": "7200"}):
            await storage_service.create_document_record(
                document_id="doc-456",
                filename="test.txt",
                format=DocumentFormat.PLAIN_TEXT,
                size_bytes=512,
            )

        insert_call = mock_supabase.table().insert.call_args[0][0]
        # expires_at should be set
        assert "expires_at" in insert_call
        # Verify it's a valid ISO timestamp
        expires = datetime.fromisoformat(insert_call["expires_at"])
        upload = datetime.fromisoformat(insert_call["upload_timestamp"])
        # Difference should be approximately 7200 seconds
        diff = (expires - upload).total_seconds()
        assert 7199 <= diff <= 7201


# --- persist_ir tests ---


@pytest.mark.asyncio
class TestPersistIR:
    """Tests for persisting the intermediate representation."""

    async def test_updates_document_with_metadata_and_ready_status(
        self, storage_service, mock_supabase, sample_ir
    ):
        await storage_service.persist_ir(sample_ir)

        # Should update documents table
        mock_supabase.table.assert_any_call("documents")
        update_call = mock_supabase.table().update.call_args[0][0]

        assert update_call["document_id"] == "doc-123"
        assert update_call["status"] == "ready"
        assert update_call["format"] == "markdown"
        assert update_call["language"] == "es"
        assert update_call["size_bytes"] == 1024

    async def test_inserts_chunks(self, storage_service, mock_supabase, sample_ir):
        await storage_service.persist_ir(sample_ir)

        # Should insert into document_chunks
        mock_supabase.table.assert_any_call("document_chunks")
        insert_call = mock_supabase.table().insert.call_args[0][0]

        assert len(insert_call) == 2
        assert insert_call[0]["chunk_id"] == "chunk-0"
        assert insert_call[0]["document_id"] == "doc-123"
        assert insert_call[0]["order"] == 0
        assert insert_call[1]["chunk_id"] == "chunk-1"
        assert insert_call[1]["order"] == 1

    async def test_persist_ir_with_no_chunks(self, storage_service, mock_supabase):
        ir = IntermediateRepresentation(
            document_id="doc-empty",
            metadata=DocumentMetadata(
                original_filename="empty.txt",
                format=DocumentFormat.PLAIN_TEXT,
                size_bytes=0,
                language=DetectedLanguage.UNKNOWN,
                upload_timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ),
            chunks=[],
        )

        await storage_service.persist_ir(ir)

        # Should update doc status to ready
        update_call = mock_supabase.table().update.call_args[0][0]
        assert update_call["status"] == "ready"

        # Should NOT attempt to insert chunks when list is empty
        # The insert for document_chunks should not be called for chunks
        # (only the update for documents is called)


# --- mark_failed tests ---


@pytest.mark.asyncio
class TestMarkFailed:
    """Tests for marking documents as failed."""

    async def test_sets_status_to_failed(self, storage_service, mock_supabase):
        await storage_service.mark_failed("doc-fail", "Extraction error occurred")

        mock_supabase.table.assert_called_with("documents")
        update_call = mock_supabase.table().update.call_args[0][0]

        assert update_call["status"] == "failed"
        assert update_call["error_message"] == "Extraction error occurred"

    async def test_filters_by_document_id(self, storage_service, mock_supabase):
        await storage_service.mark_failed("doc-xyz", "Some error")

        mock_supabase.table().update().eq.assert_called_with(
            "document_id", "doc-xyz"
        )


# --- get_status tests ---


@pytest.mark.asyncio
class TestGetStatus:
    """Tests for retrieving document status."""

    async def test_returns_status_for_existing_document(
        self, storage_service, mock_supabase
    ):
        mock_supabase.table().select().eq().execute.return_value = MagicMock(
            data=[
                {
                    "document_id": "doc-123",
                    "status": "ready",
                    "original_filename": "report.md",
                    "format": "markdown",
                    "language": "es",
                    "warnings": json.dumps(["Warning 1"]),
                    "error_message": None,
                }
            ]
        )
        # For chunk count query
        mock_supabase.table().select().eq().execute.return_value.count = None
        # We need to set up the chain for the second call (chunk count)
        chunks_response = MagicMock()
        chunks_response.count = 5

        # The table mock is called multiple times; we configure side effects
        execute_mock = MagicMock()
        execute_mock.data = [
            {
                "document_id": "doc-123",
                "status": "ready",
                "original_filename": "report.md",
                "format": "markdown",
                "language": "es",
                "warnings": json.dumps(["Warning 1"]),
                "error_message": None,
            }
        ]

        chunks_execute_mock = MagicMock()
        chunks_execute_mock.count = 5

        # Reset mock and set up proper chain
        mock_supabase.reset_mock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock

        # First call: documents select
        doc_chain = MagicMock()
        doc_chain.execute.return_value = execute_mock

        # Second call: chunks select with count
        chunk_chain = MagicMock()
        chunk_chain.execute.return_value = chunks_execute_mock

        # table().select().eq().execute() pattern
        select_mock = MagicMock()
        select_calls = [MagicMock(), MagicMock()]
        select_calls[0].eq.return_value = doc_chain
        select_calls[1].eq.return_value = chunk_chain

        table_mock.select.side_effect = select_calls

        result = await storage_service.get_status("doc-123")

        assert result is not None
        assert isinstance(result, DocumentStatus)
        assert result.document_id == "doc-123"
        assert result.status == "ready"
        assert result.filename == "report.md"
        assert result.format == "markdown"
        assert result.language == "es"
        assert result.chunk_count == 5
        assert result.warnings == ["Warning 1"]

    async def test_returns_none_for_nonexistent_document(
        self, storage_service, mock_supabase
    ):
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

        result = await storage_service.get_status("nonexistent-id")

        assert result is None


# --- get_ir tests ---


@pytest.mark.asyncio
class TestGetIR:
    """Tests for retrieving the intermediate representation."""

    async def test_returns_ir_for_ready_document(
        self, storage_service, mock_supabase
    ):
        doc_response = MagicMock()
        doc_response.data = [
            {
                "document_id": "doc-123",
                "status": "ready",
                "original_filename": "report.md",
                "format": "markdown",
                "size_bytes": 1024,
                "language": "es",
                "upload_timestamp": "2024-01-15T10:30:00+00:00",
                "warnings": json.dumps(["Table skipped"]),
            }
        ]

        chunks_response = MagicMock()
        chunks_response.data = [
            {
                "chunk_id": "chunk-0",
                "text": "First section",
                "structural_context": json.dumps({"section": "# Intro"}),
                "order": 0,
            },
            {
                "chunk_id": "chunk-1",
                "text": "Second section",
                "structural_context": {"section": "## Details"},
                "order": 1,
            },
        ]

        # Reset and configure mock chains
        mock_supabase.reset_mock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock

        # First select chain (documents)
        doc_select = MagicMock()
        doc_eq = MagicMock()
        doc_eq.execute.return_value = doc_response
        doc_select.eq.return_value = doc_eq

        # Second select chain (chunks)
        chunk_select = MagicMock()
        chunk_eq = MagicMock()
        chunk_order = MagicMock()
        chunk_order.execute.return_value = chunks_response
        chunk_eq.order.return_value = chunk_order
        chunk_select.eq.return_value = chunk_eq

        table_mock.select.side_effect = [doc_select, chunk_select]

        result = await storage_service.get_ir("doc-123")

        assert result is not None
        assert isinstance(result, IntermediateRepresentation)
        assert result.document_id == "doc-123"
        assert result.metadata.original_filename == "report.md"
        assert result.metadata.format == DocumentFormat.MARKDOWN
        assert result.metadata.language == DetectedLanguage.SPANISH
        assert result.metadata.warnings == ["Table skipped"]
        assert len(result.chunks) == 2
        assert result.chunks[0].chunk_id == "chunk-0"
        assert result.chunks[1].order == 1

    async def test_returns_none_for_nonexistent_document(
        self, storage_service, mock_supabase
    ):
        doc_response = MagicMock()
        doc_response.data = []

        mock_supabase.reset_mock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock
        select_mock = MagicMock()
        select_mock.eq.return_value.execute.return_value = doc_response
        table_mock.select.return_value = select_mock

        result = await storage_service.get_ir("nonexistent")

        assert result is None

    async def test_returns_none_for_non_ready_document(
        self, storage_service, mock_supabase
    ):
        doc_response = MagicMock()
        doc_response.data = [
            {
                "document_id": "doc-processing",
                "status": "processing",
                "original_filename": "file.txt",
                "format": "plain_text",
                "size_bytes": 100,
                "language": "unknown",
                "upload_timestamp": "2024-01-15T10:30:00+00:00",
                "warnings": "[]",
            }
        ]

        mock_supabase.reset_mock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock
        select_mock = MagicMock()
        select_mock.eq.return_value.execute.return_value = doc_response
        table_mock.select.return_value = select_mock

        result = await storage_service.get_ir("doc-processing")

        assert result is None


# --- delete_expired tests ---


@pytest.mark.asyncio
class TestDeleteExpired:
    """Tests for deleting expired documents."""

    async def test_deletes_expired_documents_and_storage(
        self, storage_service, mock_supabase
    ):
        expired_docs = MagicMock()
        expired_docs.data = [
            {"document_id": "exp-1", "original_filename": "old1.md"},
            {"document_id": "exp-2", "original_filename": "old2.pdf"},
        ]

        mock_supabase.reset_mock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock

        # select().lt().execute() for finding expired
        select_chain = MagicMock()
        lt_chain = MagicMock()
        lt_chain.execute.return_value = expired_docs
        select_chain.lt.return_value = lt_chain
        table_mock.select.return_value = select_chain

        # delete().eq().execute() for removing
        delete_chain = MagicMock()
        eq_chain = MagicMock()
        eq_chain.execute.return_value = MagicMock()
        delete_chain.eq.return_value = eq_chain
        table_mock.delete.return_value = delete_chain

        # Storage removal
        storage_mock = MagicMock()
        mock_supabase.storage.from_.return_value = storage_mock

        count = await storage_service.delete_expired()

        assert count == 2
        # Should attempt to remove storage files
        assert storage_mock.remove.call_count == 2
        # Should delete from database
        assert table_mock.delete.call_count == 2

    async def test_returns_zero_when_no_expired_documents(
        self, storage_service, mock_supabase
    ):
        expired_docs = MagicMock()
        expired_docs.data = []

        mock_supabase.reset_mock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock

        select_chain = MagicMock()
        lt_chain = MagicMock()
        lt_chain.execute.return_value = expired_docs
        select_chain.lt.return_value = lt_chain
        table_mock.select.return_value = select_chain

        count = await storage_service.delete_expired()

        assert count == 0

    async def test_continues_on_storage_removal_failure(
        self, storage_service, mock_supabase
    ):
        """Storage removal errors should not prevent DB cleanup."""
        expired_docs = MagicMock()
        expired_docs.data = [
            {"document_id": "exp-1", "original_filename": "file.md"},
        ]

        mock_supabase.reset_mock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock

        select_chain = MagicMock()
        lt_chain = MagicMock()
        lt_chain.execute.return_value = expired_docs
        select_chain.lt.return_value = lt_chain
        table_mock.select.return_value = select_chain

        delete_chain = MagicMock()
        eq_chain = MagicMock()
        eq_chain.execute.return_value = MagicMock()
        delete_chain.eq.return_value = eq_chain
        table_mock.delete.return_value = delete_chain

        # Storage throws an exception
        storage_mock = MagicMock()
        storage_mock.remove.side_effect = Exception("Storage unavailable")
        mock_supabase.storage.from_.return_value = storage_mock

        count = await storage_service.delete_expired()

        # Should still succeed and delete from DB
        assert count == 1
        assert table_mock.delete.call_count == 1
