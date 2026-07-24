"""Ingestion pipeline orchestrator.

Coordinates validation, extraction, language detection, IR assembly,
and storage to process an uploaded document end-to-end.
"""

import uuid
from datetime import datetime, timezone

from app.ingestion.adapters.base import FormatAdapter
from app.ingestion.ir_builder import IRBuilder
from app.ingestion.language import LanguageDetector
from app.ingestion.storage import StorageService
from app.ingestion.validator import ValidationResult, Validator
from app.models.document import (
    ContentChunkModel,
    DocumentMetadata,
    DocumentStatus,
)


class IngestionService:
    """Orchestrates the full document ingestion pipeline.

    Pipeline steps:
        1. Generate UUID
        2. Validate file (format, size, encoding)
        3. Create document record (status=processing)
        4. Store original file
        5. Select adapter and extract text
        6. Detect language (first 1000 chars)
        7. Build intermediate representation
        8. Persist IR (sets status=ready)

    Validation failures short-circuit immediately.
    Extraction failures mark the document as failed.
    """

    def __init__(
        self,
        validator: Validator,
        adapters: list[FormatAdapter],
        language_detector: LanguageDetector,
        ir_builder: IRBuilder,
        storage_service: StorageService,
    ) -> None:
        """Initialize with all pipeline dependencies.

        Args:
            validator: Validates format, size, and encoding.
            adapters: List of format adapters to select from.
            language_detector: Detects document language.
            ir_builder: Assembles the intermediate representation.
            storage_service: Handles persistence of files and IR.
        """
        self._validator = validator
        self._adapters = adapters
        self._language_detector = language_detector
        self._ir_builder = ir_builder
        self._storage = storage_service

    async def ingest(
        self, file_bytes: bytes, filename: str, content_type: str | None
    ) -> DocumentStatus:
        """Process an uploaded document through the full ingestion pipeline.

        Args:
            file_bytes: Raw bytes of the uploaded file.
            filename: Original filename.
            content_type: MIME type from the upload (may be None).

        Returns:
            DocumentStatus reflecting the final state of ingestion.
        """
        # 1. Generate unique document ID
        document_id = str(uuid.uuid4())

        # 2. Validate
        validation: ValidationResult = self._validator.validate(file_bytes, filename)

        if not validation.valid:
            # Short-circuit: return failed status without persisting
            return DocumentStatus(
                document_id=document_id,
                status="failed",
                filename=filename,
                format="unknown",
                error_message=validation.error_message,
            )

        detected_format = validation.detected_format
        size_bytes = len(file_bytes)

        # 3. Create document record (status=processing)
        await self._storage.create_document_record(
            document_id=document_id,
            filename=filename,
            format=detected_format,
            size_bytes=size_bytes,
        )

        # 4. Store original file
        await self._storage.store_original(
            document_id=document_id,
            file_bytes=file_bytes,
            filename=filename,
        )

        # 5. Select adapter and extract
        adapter = self._select_adapter(filename, content_type)

        if adapter is None:
            error_msg = f"No adapter available for file: {filename}"
            await self._storage.mark_failed(document_id, error_msg)
            return DocumentStatus(
                document_id=document_id,
                status="failed",
                filename=filename,
                format=detected_format.value,
                error_message=error_msg,
            )

        try:
            extraction_result = adapter.extract(file_bytes, filename)
        except Exception as exc:
            error_msg = f"Extraction failed: {exc}"
            await self._storage.mark_failed(document_id, error_msg)
            return DocumentStatus(
                document_id=document_id,
                status="failed",
                filename=filename,
                format=detected_format.value,
                error_message=error_msg,
            )

        # 6. Detect language (first 1000 chars of concatenated chunk text)
        concatenated_text = " ".join(chunk.text for chunk in extraction_result.chunks)
        text_sample = concatenated_text[:1000]
        detected_language = self._language_detector.detect(text_sample)

        # 7. Convert ContentChunk dataclass instances to ContentChunkModel Pydantic models
        chunk_models = [
            ContentChunkModel(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                structural_context=chunk.structural_context,
                order=chunk.order,
            )
            for chunk in extraction_result.chunks
        ]

        # Build metadata
        metadata = DocumentMetadata(
            original_filename=filename,
            format=detected_format,
            size_bytes=size_bytes,
            language=detected_language,
            upload_timestamp=datetime.now(timezone.utc),
            warnings=extraction_result.warnings,
        )

        # Build IR
        ir = self._ir_builder.build(
            document_id=document_id,
            metadata=metadata,
            chunks=chunk_models,
        )

        # 8. Persist IR (sets status=ready)
        await self._storage.persist_ir(ir)

        return DocumentStatus(
            document_id=document_id,
            status="ready",
            filename=filename,
            format=detected_format.value,
            language=detected_language.value,
            chunk_count=len(chunk_models),
            warnings=extraction_result.warnings,
        )

    def _select_adapter(
        self, filename: str, content_type: str | None
    ) -> FormatAdapter | None:
        """Find the first adapter that can handle the given file.

        Args:
            filename: Original filename.
            content_type: MIME type (may be None).

        Returns:
            A FormatAdapter instance, or None if no adapter matches.
        """
        for adapter in self._adapters:
            if adapter.can_handle(filename, content_type):
                return adapter
        return None
