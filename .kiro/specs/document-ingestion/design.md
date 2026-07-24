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

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `api/v1/documents.py` | HTTP layer — receives uploads, returns responses | REST endpoints | `IngestionService` |
| `IngestionService` | Orchestrates the full pipeline (validate → extract → detect language → build IR → persist) | `ingest(file_bytes, filename, content_type) → DocumentStatus` | `Validator`, `FormatAdapter`, `LanguageDetector`, `IRBuilder`, `StorageService` |
| `Validator` | Enforces pre-processing constraints | `validate(file_bytes, filename) → ValidationResult` | — |
| `FormatAdapter` (ABC) | Extracts text from a specific format | `extract(file_bytes, filename) → ExtractionResult` | Format-specific libraries |
| `MarkdownAdapter` | Markdown extraction | Implements `FormatAdapter` | — |
| `PlainTextAdapter` | Plain text extraction | Implements `FormatAdapter` | — |
| `PdfAdapter` | PDF extraction | Implements `FormatAdapter` | PyMuPDF |
| `LanguageDetector` | Classifies document language | `detect(text_sample) → DetectedLanguage` | — |
| `IRBuilder` | Assembles final IR from parts | `build(doc_id, metadata, chunks) → IntermediateRepresentation` | — |
| `StorageService` | Persists original file and IR to Supabase | `store_original(doc_id, file_bytes, filename)`, `persist_ir(ir)`, `delete_expired()` | supabase-py |

### Key Interfaces

```python
# --- Validation ---
@dataclass
class ValidationResult:
    valid: bool
    error_code: str | None = None   # e.g., "unsupported_format", "file_too_large"
    error_message: str | None = None
    detected_format: DocumentFormat | None = None

class Validator:
    def validate(self, file_bytes: bytes, filename: str) -> ValidationResult: ...

# --- Extraction (adapter contract, defined in Architecture section) ---
class FormatAdapter(ABC):
    def can_handle(self, filename: str, content_type: str | None) -> bool: ...
    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult: ...

# --- Language Detection ---
class LanguageDetector:
    def detect(self, text_sample: str) -> DetectedLanguage: ...

# --- IR Assembly ---
class IRBuilder:
    def build(
        self,
        document_id: str,
        metadata: DocumentMetadata,
        chunks: list[ContentChunkModel],
    ) -> IntermediateRepresentation: ...

# --- Storage ---
class StorageService:
    async def store_original(self, document_id: str, file_bytes: bytes, filename: str) -> None: ...
    async def persist_ir(self, ir: IntermediateRepresentation) -> None: ...
    async def delete_expired(self) -> int: ...  # returns count of deleted documents
    async def get_ir(self, document_id: str) -> IntermediateRepresentation | None: ...
    async def get_status(self, document_id: str) -> DocumentStatus | None: ...

# --- Orchestrator ---
@dataclass
class DocumentStatus:
    document_id: str
    status: str  # "processing" | "ready" | "failed"
    filename: str
    format: str
    language: str | None = None
    chunk_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None

class IngestionService:
    async def ingest(self, file_bytes: bytes, filename: str, content_type: str | None) -> DocumentStatus: ...
```

### Interaction Flow

```
documents.py (API)
      │
      ▼
IngestionService.ingest()
      │
      ├── Validator.validate()          → fail? return 400
      │
      ├── StorageService.store_original()
      │
      ├── adapter = select_adapter(format)
      │   └── adapter.extract()         → fail? mark failed, return 422
      │
      ├── LanguageDetector.detect()
      │
      ├── IRBuilder.build()
      │
      └── StorageService.persist_ir()   → update status = ready
```

---

## Correctness Properties

These invariants must hold for the ingestion layer to be considered correct:

### Property 1: Format Fidelity

The intermediate representation contains all extractable text from the original document. No text content is silently dropped — any skipped content (complex tables, images) is recorded in the `warnings` array.

**Validates: Requirements 2.4, 2.5, 2.6**

### Property 2: Structural Preservation

Chunk ordering in the IR matches the reading order of the original document. `chunk.order` values are strictly sequential (0, 1, 2, ...) with no gaps.

**Validates: Requirements 3.3**

### Property 3: Chunk Completeness

The concatenation of all `chunk.text` values (in order) equals the full extracted text of the document. No text exists between chunks that is not captured.

**Validates: Requirements 2.1, 2.2, 2.3, 3.3**

### Property 4: Metadata Accuracy

`size_bytes` equals the actual byte length of the uploaded file. `format` matches the actual file content (not just the extension). `language` reflects the dominant language of the extracted text.

**Validates: Requirements 1.1, 1.2, 1.3, 3.2, 4.1, 4.2**

### Property 5: Isolation Guarantee

The `IntermediateRepresentation` output is identical in structure regardless of source format. No field is conditionally present based on format — only the values within `structural_context` differ.

**Validates: Requirements 7.3, 7.4**

### Property 6: Idempotent Validation

Uploading the same file twice produces two independent documents with different `document_id` values but structurally equivalent IR content.

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 7: Cleanup Completeness

When `delete_expired()` runs, all associated data is removed — the `documents` row, all `document_chunks` rows (via CASCADE), and the original file in storage. No orphaned data remains.

**Validates: Requirements 5.2**

### Property 8: Privacy Boundary

At no point does the ingestion layer attach, store, or forward user identity, account information, or usage history alongside document data.

**Validates: Requirements 5.4**

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

## Error Handling

Errors are categorized by origin and handled at the appropriate layer:

| Error Type | Origin | Response | User Message |
|-----------|--------|----------|--------------|
| Unsupported format | Validation | 400 | Lists supported formats |
| File too large | Validation | 400 | States limit for the detected format |
| Invalid encoding | Validation | 400 | Specifies UTF-8 requirement |
| Scanned PDF | Extraction (pre-check) | 400 | Explains OCR is not supported |
| Corrupted/unreadable PDF | Extraction | 422 | Suggests re-exporting the PDF |
| Extraction partial failure | Extraction | Success with warnings | Warnings array in IR metadata |
| Database write failure | Storage | 500 | Generic "processing failed, try again" |
| Storage upload failure | Storage | 500 | Generic "processing failed, try again" |

Design principles:
- Validation errors (4xx) are returned immediately before any processing begins.
- Extraction errors that affect the entire document result in `status: failed` with a descriptive `error_message`.
- Partial extraction issues (e.g., a single complex table skipped) are non-blocking — they produce warnings in the IR metadata rather than failures.
- Internal errors (5xx) never expose stack traces or implementation details to the client.

---

## Security Considerations

Aligned with ADR-005 (Privacy and External Processing):

- **No user metadata attached:** The ingestion layer stores only document content and structural metadata. No user identity, account info, or usage history is persisted alongside the document.
- **Input sanitization:** File names are sanitized before storage to prevent path traversal. File content is treated as untrusted input — adapters handle malformed content gracefully without crashing.
- **Size limits enforced server-side:** Client-reported sizes are not trusted; the server validates actual byte count after receiving the full upload.
- **Temporary retention:** The original file is deleted after session expiry. Only the derived IR persists during the session.
- **No execution of embedded content:** PDF JavaScript, macros, or active content are ignored by PyMuPDF's text extraction — they are never executed.

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| Adapters | Each adapter in isolation | Unit tests with fixture files (small .md, .txt, .pdf samples) covering normal cases, edge cases (empty files, huge headings, complex tables), and error cases (corrupted PDFs, scanned PDFs) |
| Validator | Validation rules | Unit tests for each constraint (format, size, encoding) with both passing and failing inputs |
| Language detection | Classification accuracy | Unit tests with known Spanish and English text samples, mixed-language edge cases, and very short texts |
| IR Builder | Assembly logic | Unit tests verifying correct chunk ordering, metadata population, and structural context assignment |
| Service (pipeline) | End-to-end ingestion flow | Integration tests that upload a file via the API and verify the resulting IR in the database |
| API endpoints | HTTP contract | Integration tests verifying status codes, response shapes, and error formats using httpx + pytest |

Fixture files live in `tests/fixtures/ingestion/` organized by format and test scenario.

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| FastAPI | HTTP framework | Project standard (tech.md) |
| Pydantic v2 | Data validation and IR models | Project standard (tech.md) |
| PyMuPDF (fitz) | PDF text extraction | Project standard (tech.md); handles text extraction, page structure, and scanned PDF detection without OCR dependency |
| supabase-py | Database and storage client | Project standard (tech.md) |
| python-multipart | Multipart upload parsing | Required by FastAPI for file uploads |
| pytest + httpx | Testing | Project standard (tech.md) |

No additional dependencies beyond the project's established stack are introduced.

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
