# Design — Document Ingestion

## Overview

This document describes the technical design for the Document Ingestion feature. It covers the architecture, data models, API contracts, module structure, and key technical decisions required to implement the approved requirements.

The ingestion layer is the system's entry point. Its single responsibility is to accept a document, validate it, extract text, and produce a structured intermediate representation consumed by the analysis engine. It has no knowledge of the Knowledge Model, LLM interactions, or quality analysis — those belong to downstream features.

## Relevant Documentation

- #[[file:.kiro/specs/document-ingestion/requirements.md]]
- #[[file:docs/decisions/ADR-003-document-ingestion.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]

---

## Architecture

### System Context

```
┌──────────┐       ┌─────────────────────────────────────────────┐       ┌──────────────────┐
│  Client  │──────▶│          Document Ingestion Service          │──────▶│  Analysis Engine  │
│(Frontend)│◀──────│  (validate → extract → build IR → store)     │       │  (downstream)     │
└──────────┘       └─────────────────────────────────────────────┘       └──────────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │   Supabase    │
                              │  (Storage +   │
                              │   PostgreSQL) │
                              └───────────────┘
```

### Internal Module Decomposition

The ingestion layer is organized into four internal modules:

1. **Validation** — Enforces format, size, encoding, and content constraints before any processing begins.
2. **Extraction** — Transforms raw file bytes into normalized text with structural context. One adapter per format.
3. **IR Builder** — Assembles the intermediate representation from extracted content and metadata.
4. **Storage** — Handles temporary persistence of the original file and the generated IR.

### Adapter Pattern for Extraction

Each supported format is handled by an independent adapter that conforms to a shared interface:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ExtractionResult:
    """Output of a format adapter."""
    chunks: list["ContentChunk"]
    warnings: list[str]  # e.g., "Complex table skipped on page 3"

@dataclass
class ContentChunk:
    """A unit of extracted text with structural context."""
    chunk_id: str
    text: str
    structural_context: dict  # {"page": 2} or {"section": "## Requirements"}
    order: int

class FormatAdapter(ABC):
    """Contract for all format adapters."""

    @abstractmethod
    def can_handle(self, filename: str, content_type: str | None) -> bool:
        """Return True if this adapter handles the given format."""
        ...

    @abstractmethod
    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text content from raw file bytes."""
        ...
```

Three adapters implement this interface:

| Adapter | File Extensions | Library | Chunking Strategy |
|---------|----------------|---------|-------------------|
| `MarkdownAdapter` | `.md` | Built-in (regex-based heading split) | One chunk per heading section |
| `PlainTextAdapter` | `.txt` | Built-in | Single chunk, or split by detected heading patterns |
| `PdfAdapter` | `.pdf` | PyMuPDF (fitz) | One or more chunks per page |

Adding a future format (e.g., DOCX) requires only implementing a new `FormatAdapter` subclass and registering it — no changes to validation, IR builder, or downstream consumers.

---

## Data Models

### Intermediate Representation (IR)

The IR is the contract between ingestion and the analysis engine. It is format-agnostic and self-contained.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    PDF = "pdf"

class DetectedLanguage(str, Enum):
    SPANISH = "es"
    ENGLISH = "en"
    UNKNOWN = "unknown"

class ContentChunkModel(BaseModel):
    chunk_id: str = Field(description="Unique identifier for this chunk within the document")
    text: str = Field(description="Extracted text content")
    structural_context: dict = Field(
        description="Format-derived context: {'page': int} for PDF, {'section': str} for Markdown"
    )
    order: int = Field(description="Position in document reading order, 0-indexed")

class DocumentMetadata(BaseModel):
    original_filename: str
    format: DocumentFormat
    size_bytes: int
    language: DetectedLanguage
    upload_timestamp: datetime
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking issues encountered during extraction"
    )

class IntermediateRepresentation(BaseModel):
    document_id: str = Field(description="Unique identifier for this ingestion session")
    metadata: DocumentMetadata
    chunks: list[ContentChunkModel] = Field(description="Ordered content chunks")
```

### Database Schema (Supabase/PostgreSQL)

Two tables support the ingestion feature:

```sql
-- Stores metadata and IR for active sessions
CREATE TABLE documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename TEXT NOT NULL,
    format TEXT NOT NULL,  -- 'markdown' | 'plain_text' | 'pdf'
    size_bytes INTEGER NOT NULL,
    language TEXT NOT NULL DEFAULT 'unknown',  -- 'es' | 'en' | 'unknown'
    upload_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    warnings JSONB DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'processing',  -- 'processing' | 'ready' | 'failed'
    error_message TEXT,
    expires_at TIMESTAMPTZ NOT NULL,  -- session expiry for cleanup
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stores extracted chunks for a document
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL,
    text TEXT NOT NULL,
    structural_context JSONB NOT NULL,  -- {"page": 2} or {"section": "## Heading"}
    "order" INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_id)
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
```

### Temporary File Storage

The original uploaded file is stored in Supabase Storage under a path:

```
documents/{document_id}/original/{filename}
```

Files are deleted when the session expires (via `expires_at` and a scheduled cleanup function or Supabase policy).

---

## API Design

### POST /api/v1/documents/upload

Accepts a multipart file upload. Returns immediately with a document_id and status.

**Request:**
```
POST /api/v1/documents/upload
Content-Type: multipart/form-data

file: <binary>
```

**Response (202 Accepted):**
```json
{
  "document_id": "uuid-here",
  "status": "processing",
  "filename": "my-prd.md",
  "format": "markdown",
  "size_bytes": 15234
}
```

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 400 | Unsupported format | `{"error": "unsupported_format", "message": "...", "supported_formats": [".md", ".txt", ".pdf"]}` |
| 400 | File too large | `{"error": "file_too_large", "message": "...", "max_size_bytes": 1048576}` |
| 400 | Invalid encoding | `{"error": "invalid_encoding", "message": "...", "required_encoding": "utf-8"}` |
| 400 | Scanned PDF | `{"error": "scanned_pdf", "message": "..."}` |
| 422 | Extraction failed | `{"error": "extraction_failed", "message": "..."}` |

### GET /api/v1/documents/{document_id}/status

Returns the current processing status.

**Response (200 OK):**
```json
{
  "document_id": "uuid-here",
  "status": "ready",
  "filename": "my-prd.md",
  "format": "markdown",
  "language": "es",
  "chunk_count": 12,
  "warnings": ["Complex table skipped on page 3"]
}
```

Status values: `processing`, `ready`, `failed`.

### GET /api/v1/documents/{document_id}/ir

Returns the full intermediate representation. Only available when status is `ready`. Consumed by the analysis engine.

**Response (200 OK):**
```json
{
  "document_id": "uuid-here",
  "metadata": {
    "original_filename": "my-prd.md",
    "format": "markdown",
    "size_bytes": 15234,
    "language": "es",
    "upload_timestamp": "2026-07-23T10:00:00Z",
    "warnings": []
  },
  "chunks": [
    {
      "chunk_id": "chunk-001",
      "text": "# Product Requirements\n\nThis document defines...",
      "structural_context": {"section": "# Product Requirements"},
      "order": 0
    }
  ]
}
```

---

## Processing Pipeline

The upload endpoint triggers a synchronous pipeline (appropriate for files ≤10 MB):

```
1. Receive file
       │
2. Validate (format, size, encoding)
       │ ── fail ──▶ Return 400 with specific error
       │
3. Store original temporarily
       │
4. Select adapter (by extension + MIME type)
       │
5. Extract text (adapter.extract())
       │ ── fail ──▶ Mark status=failed, return 422
       │
6. Detect language
       │
7. Build IR (assemble metadata + chunks)
       │
8. Persist IR to database
       │
9. Update status = ready
       │
10. Return 202 with document_id
```

For the MVP, this pipeline is synchronous within a single request given the modest file sizes (≤10 MB). If latency becomes an issue with large PDFs, this can be made async with a background task in a future iteration without changing the API contract (the client already polls via the status endpoint).

---

## Key Technical Decisions

### Scanned PDF Detection (Req 2, AC7)

A PDF is classified as "scanned" (image-only) when PyMuPDF extracts zero or near-zero text characters across all pages while the document has renderable pages. The heuristic:

```python
def is_scanned_pdf(doc: fitz.Document) -> bool:
    total_text_length = sum(len(page.get_text()) for page in doc)
    return doc.page_count > 0 and total_text_length < 50  # threshold: <50 chars total
```

This is a pragmatic heuristic. A threshold of 50 characters accounts for PDF metadata that might appear as "text" in header/footer areas. The exact threshold can be tuned with real-world testing.

### Language Detection (Req 4)

Language detection uses a lightweight library-free approach for the MVP:

1. Sample the first 1000 characters of extracted text.
2. Use character frequency analysis and common word matching for Spanish vs. English classification.
3. If confidence is below threshold, mark as `unknown` and proceed (best-effort per Req 4, AC3).

A library like `langdetect` or `lingua` can replace this if accuracy is insufficient, but adding a dependency for two-language detection is avoidable in most cases.

**Alternative considered:** Using the LLM for language detection. Rejected because ingestion must not depend on LLM services — it should work independently even if the LLM provider is unavailable.

### Chunk Granularity

- **Markdown:** One chunk per top-level or second-level heading section. Deeply nested sections (h3+) stay within their parent chunk to avoid excessive fragmentation.
- **Plain text:** Single chunk unless the file contains lines matching common heading patterns (all-caps lines, lines followed by `===` or `---`), in which case those serve as split points.
- **PDF:** One chunk per page by default. Pages exceeding 4000 characters are split at paragraph boundaries into multiple chunks.

The 4000-character limit per chunk is informed by downstream LLM context window management — chunks that are too large reduce the analysis engine's ability to assign precise `source_ref` references.

### Session Expiration and Cleanup

Documents are assigned an `expires_at` timestamp at upload time, calculated as `upload_timestamp + configured retention duration`. The retention duration is a configurable value (e.g., environment variable or application config) that can be adjusted without code changes.

The cleanup mechanism:

1. A Supabase scheduled function (or a cron-triggered API call) periodically queries for rows where `expires_at < now()`.
2. Expired rows are deleted from `documents` (cascading to `document_chunks`).
3. Associated files in Supabase Storage are removed.

The architecture is independent of the chosen duration — any value from minutes to days works without structural changes. As a suggested default for initial deployment, 24 hours provides a reasonable balance between usability and data minimization, but this is a deployment configuration choice, not an architectural constraint.

The Knowledge Model (produced by downstream features) persists independently and is not affected by document expiration.

### Encoding Validation

For Markdown and text files, encoding is validated by attempting to decode the file content as UTF-8. If decoding fails (raises `UnicodeDecodeError`), the file is rejected. No fallback to other encodings is attempted — the requirement explicitly mandates UTF-8.

---

## File Structure

```
src/backend/
├── app/
│   ├── main.py                          # FastAPI app factory
│   ├── api/
│   │   └── v1/
│   │       └── documents.py             # Upload, status, IR endpoints
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── service.py                   # Orchestrates the ingestion pipeline
│   │   ├── validator.py                 # Format, size, encoding validation
│   │   ├── language.py                  # Language detection logic
│   │   ├── ir_builder.py               # Assembles IntermediateRepresentation
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # FormatAdapter ABC + ExtractionResult
│   │   │   ├── markdown_adapter.py     # Markdown extraction
│   │   │   ├── plaintext_adapter.py    # Plain text extraction
│   │   │   └── pdf_adapter.py          # PDF extraction via PyMuPDF
│   │   └── storage.py                  # Temporary file + IR persistence
│   ├── models/
│   │   ├── __init__.py
│   │   └── document.py                 # Pydantic models (IR, metadata, chunks)
│   └── db/
│       └── migrations/                  # SQL migrations for documents, chunks
└── tests/
    └── unit/
        └── ingestion/
            ├── test_validator.py
            ├── test_markdown_adapter.py
            ├── test_plaintext_adapter.py
            ├── test_pdf_adapter.py
            ├── test_language.py
            └── test_ir_builder.py
```

---

## Frontend Integration Points

The frontend interacts with the ingestion layer through three API calls:

1. **Upload** — `POST /api/v1/documents/upload` with the file. Shows upload progress using browser's `XMLHttpRequest` or `fetch` with progress events on the request body stream.
2. **Poll status** — `GET /api/v1/documents/{document_id}/status` at intervals (e.g., every 1 second) until status is `ready` or `failed`. Displays a processing indicator to the user.
3. **Retrieve IR** — `GET /api/v1/documents/{document_id}/ir` when ready. The frontend does not use the IR directly; it passes the document_id to the analysis feature.

Error messages from the API are user-facing and actionable (Req 6, AC4). The frontend displays them directly without transformation.

---

## Design Decisions Pending Clarification

### Upload Progress for Synchronous Processing

The current design returns 202 after the full pipeline completes (synchronous). True upload progress (bytes sent) is handled client-side. Processing progress (extraction step) is not granular — the client sees only `processing` → `ready`/`failed`. If extraction of large PDFs takes noticeable time (>3s), consider moving to an async task model in a future iteration.

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Document Upload API | API `POST /upload`, `validator.py`, error responses |
| Req 2: Text Extraction | `adapters/` module, `ExtractionResult`, scanned PDF detection |
| Req 3: Intermediate Representation | `IntermediateRepresentation` model, `ir_builder.py`, DB schema |
| Req 4: Language Detection | `language.py`, `DetectedLanguage` enum, metadata field |
| Req 5: Temporary Storage & Privacy | `storage.py`, `expires_at`, cleanup mechanism, no user metadata |
| Req 6: Upload Feedback & Status | `GET /status` endpoint, `status` field, error messages |
| Req 7: Format-Independent Processing | Adapter pattern, shared `FormatAdapter` interface, uniform IR output |
