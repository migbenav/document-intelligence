"""Temporary file and IR persistence to Supabase.

Handles storing original uploaded files in Supabase Storage and persisting
the intermediate representation to PostgreSQL. Manages document lifecycle
including expiration and cleanup.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    DocumentStatus,
    IntermediateRepresentation,
)

# Default retention: 24 hours
_DEFAULT_RETENTION_SECONDS = 86400

STORAGE_BUCKET = "documents"

# MIME type mapping for supported document formats
_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}


def _get_content_type(filename: str) -> str:
    """Determine the MIME content-type from a filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    return _MIME_TYPES.get(ext, "application/octet-stream")


def _get_retention_seconds() -> int:
    """Read retention duration from environment variable."""
    raw = os.environ.get("DOCUMENT_RETENTION_SECONDS")
    if raw is None:
        return _DEFAULT_RETENTION_SECONDS
    try:
        return int(raw)
    except (ValueError, TypeError):
        return _DEFAULT_RETENTION_SECONDS


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage.

    Removes path traversal sequences, replaces dangerous characters,
    and ensures the result is a safe, flat filename compatible with
    Supabase Storage (ASCII-only keys).
    """
    # Remove any directory components (path traversal prevention)
    filename = os.path.basename(filename)

    # Replace backslashes
    filename = filename.replace("\\", "_")

    # Remove null bytes
    filename = filename.replace("\x00", "")

    # Replace sequences of dots that could be traversal (.. or more)
    filename = re.sub(r"\.{2,}", ".", filename)

    # Replace characters that are dangerous in file paths/URLs
    # Keep only ASCII alphanumeric, dots, hyphens, underscores
    filename = re.sub(r"[^a-zA-Z0-9.\-_]", "_", filename)

    # Collapse multiple underscores
    filename = re.sub(r"_+", "_", filename)

    # Strip leading/trailing underscores and dots
    filename = filename.strip("_.")

    # Fallback if filename is empty after sanitization
    if not filename:
        filename = "unnamed_file"

    return filename


class StorageService:
    """Manages temporary file storage and IR persistence in Supabase.

    No user metadata (user_id, account info, session cookies) is attached
    to any stored record.
    """

    def __init__(self, supabase_client) -> None:
        """Initialize with a Supabase client instance.

        Args:
            supabase_client: An initialized Supabase client for DB and Storage access.
        """
        self._client = supabase_client

    async def store_original(
        self, document_id: str, file_bytes: bytes, filename: str
    ) -> None:
        """Store the original file temporarily in Supabase Storage.

        Files are stored at: documents/{document_id}/original/{sanitized_filename}

        Args:
            document_id: Unique document identifier.
            file_bytes: Raw file content bytes.
            filename: Original filename (will be sanitized).
        """
        safe_name = sanitize_filename(filename)
        path = f"{document_id}/original/{safe_name}"

        # Determine content-type from filename extension
        content_type = _get_content_type(filename)

        self._client.storage.from_(STORAGE_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )

    async def create_document_record(
        self,
        document_id: str,
        filename: str,
        format: DocumentFormat,
        size_bytes: int,
    ) -> None:
        """Create a document record with status=processing.

        Args:
            document_id: Unique document identifier.
            filename: Original filename.
            format: Detected document format.
            size_bytes: File size in bytes.
        """
        retention = _get_retention_seconds()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=retention)

        record = {
            "document_id": document_id,
            "original_filename": filename,
            "format": format.value,
            "size_bytes": size_bytes,
            "status": "processing",
            "upload_timestamp": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        self._client.table("documents").insert(record).execute()

    async def persist_ir(self, ir: IntermediateRepresentation) -> None:
        """Persist the intermediate representation to the database.

        Inserts the document record (or updates if created via create_document_record)
        and all chunks, then sets status=ready.

        Args:
            ir: The complete intermediate representation to persist.
        """
        # Upsert the document record with full metadata and status=ready
        doc_record = {
            "document_id": ir.document_id,
            "original_filename": ir.metadata.original_filename,
            "format": ir.metadata.format.value,
            "size_bytes": ir.metadata.size_bytes,
            "language": ir.metadata.language.value,
            "upload_timestamp": ir.metadata.upload_timestamp.isoformat(),
            "warnings": json.dumps(ir.metadata.warnings),
            "status": "ready",
        }

        self._client.table("documents").update(doc_record).eq(
            "document_id", ir.document_id
        ).execute()

        # Insert all chunks
        if ir.chunks:
            chunk_records = [
                {
                    "document_id": ir.document_id,
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "structural_context": json.dumps(chunk.structural_context),
                    "order": chunk.order,
                }
                for chunk in ir.chunks
            ]

            self._client.table("document_chunks").insert(chunk_records).execute()

    async def mark_failed(
        self, document_id: str, error_message: str
    ) -> None:
        """Mark a document as failed with an error message.

        Args:
            document_id: The document to mark as failed.
            error_message: Human-readable error description.
        """
        self._client.table("documents").update(
            {"status": "failed", "error_message": error_message}
        ).eq("document_id", document_id).execute()

    async def get_status(self, document_id: str) -> DocumentStatus | None:
        """Get the current status of a document.

        Args:
            document_id: The document to query.

        Returns:
            DocumentStatus if found, None otherwise.
        """
        result = (
            self._client.table("documents")
            .select("*")
            .eq("document_id", document_id)
            .execute()
        )

        if not result.data:
            return None

        row = result.data[0]

        # Get chunk count if status is ready
        chunk_count = None
        if row["status"] == "ready":
            chunks_result = (
                self._client.table("document_chunks")
                .select("id", count="exact")
                .eq("document_id", document_id)
                .execute()
            )
            chunk_count = chunks_result.count

        warnings = row.get("warnings", [])
        if isinstance(warnings, str):
            warnings = json.loads(warnings)

        return DocumentStatus(
            document_id=row["document_id"],
            status=row["status"],
            filename=row["original_filename"],
            format=row["format"],
            language=row.get("language"),
            chunk_count=chunk_count,
            warnings=warnings,
            error_message=row.get("error_message"),
        )

    async def get_ir(
        self, document_id: str
    ) -> IntermediateRepresentation | None:
        """Retrieve the full intermediate representation from the database.

        Args:
            document_id: The document to retrieve.

        Returns:
            IntermediateRepresentation if found and status is ready, None otherwise.
        """
        # Fetch document record
        doc_result = (
            self._client.table("documents")
            .select("*")
            .eq("document_id", document_id)
            .execute()
        )

        if not doc_result.data:
            return None

        row = doc_result.data[0]

        if row["status"] != "ready":
            return None

        # Fetch chunks ordered by position
        chunks_result = (
            self._client.table("document_chunks")
            .select("*")
            .eq("document_id", document_id)
            .order("order")
            .execute()
        )

        warnings = row.get("warnings", [])
        if isinstance(warnings, str):
            warnings = json.loads(warnings)

        metadata = DocumentMetadata(
            original_filename=row["original_filename"],
            format=DocumentFormat(row["format"]),
            size_bytes=row["size_bytes"],
            language=DetectedLanguage(row["language"]),
            upload_timestamp=datetime.fromisoformat(row["upload_timestamp"]),
            warnings=warnings,
        )

        chunks = [
            ContentChunkModel(
                chunk_id=c["chunk_id"],
                text=c["text"],
                structural_context=(
                    json.loads(c["structural_context"])
                    if isinstance(c["structural_context"], str)
                    else c["structural_context"]
                ),
                order=c["order"],
            )
            for c in chunks_result.data
        ]

        return IntermediateRepresentation(
            document_id=document_id,
            metadata=metadata,
            chunks=chunks,
        )

    async def delete_expired(self) -> int:
        """Delete all expired documents and their associated storage files.

        Queries for documents where expires_at < now(), removes storage files,
        then deletes the database records (CASCADE removes chunks).

        Returns:
            Count of deleted documents.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Find expired documents
        result = (
            self._client.table("documents")
            .select("document_id, original_filename")
            .lt("expires_at", now)
            .execute()
        )

        if not result.data:
            return 0

        deleted_count = 0

        for row in result.data:
            doc_id = row["document_id"]
            filename = sanitize_filename(row["original_filename"])
            storage_path = f"{doc_id}/original/{filename}"

            # Remove file from storage (best-effort)
            try:
                self._client.storage.from_(STORAGE_BUCKET).remove([storage_path])
            except Exception:
                # Storage removal is best-effort; DB cleanup proceeds regardless
                pass

            # Delete document record (CASCADE removes chunks)
            self._client.table("documents").delete().eq(
                "document_id", doc_id
            ).execute()

            deleted_count += 1

        return deleted_count
