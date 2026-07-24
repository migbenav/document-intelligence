"""Pydantic v2 models for the document ingestion layer.

These models define the intermediate representation (IR), API response shapes,
and shared enums used across the ingestion pipeline.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DocumentFormat(str, Enum):
    """Supported document formats for ingestion."""

    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    PDF = "pdf"


class DetectedLanguage(str, Enum):
    """Languages detectable by the ingestion pipeline."""

    SPANISH = "es"
    ENGLISH = "en"
    UNKNOWN = "unknown"


class ContentChunkModel(BaseModel):
    """A unit of extracted text with structural context."""

    chunk_id: str = Field(description="Unique identifier for this chunk within the document")
    text: str = Field(description="Extracted text content")
    structural_context: dict = Field(
        description="Format-derived context: {'page': int} for PDF, {'section': str} for Markdown"
    )
    order: int = Field(description="Position in document reading order, 0-indexed")


class DocumentMetadata(BaseModel):
    """Document-level metadata populated during ingestion."""

    original_filename: str = Field(description="Original name of the uploaded file")
    format: DocumentFormat = Field(description="Detected document format")
    size_bytes: int = Field(description="Size of the uploaded file in bytes")
    language: DetectedLanguage = Field(description="Detected dominant language")
    upload_timestamp: datetime = Field(description="Timestamp when the document was uploaded")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking issues encountered during extraction",
    )


class IntermediateRepresentation(BaseModel):
    """The format-agnostic intermediate representation produced by the ingestion layer.

    This is the contract between ingestion and the analysis engine. The analysis
    engine operates exclusively on this structure, with no knowledge of the
    original file format.
    """

    document_id: str = Field(description="Unique identifier for this ingestion session")
    metadata: DocumentMetadata = Field(description="Document-level metadata")
    chunks: list[ContentChunkModel] = Field(description="Ordered content chunks")


class DocumentStatus(BaseModel):
    """Response model for POST /upload and GET /status endpoints."""

    document_id: str = Field(description="Unique document identifier")
    status: str = Field(description="processing | ready | failed")
    filename: str = Field(description="Original filename")
    format: str = Field(description="Detected format as string")
    language: str | None = Field(default=None, description="Detected language code")
    chunk_count: int | None = Field(default=None, description="Number of chunks extracted")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking issues encountered during processing",
    )
    error_message: str | None = Field(default=None, description="Error details when status is failed")


class ValidationErrorResponse(BaseModel):
    """Error response format for 400/422 responses."""

    error: str = Field(
        description="Error code: unsupported_format, file_too_large, invalid_encoding, scanned_pdf, extraction_failed"
    )
    message: str = Field(description="Human-readable error message")
    supported_formats: list[str] | None = Field(
        default=None, description="List of supported file extensions"
    )
    max_size_bytes: int | None = Field(default=None, description="Maximum allowed file size")
    required_encoding: str | None = Field(
        default=None, description="Required file encoding"
    )
