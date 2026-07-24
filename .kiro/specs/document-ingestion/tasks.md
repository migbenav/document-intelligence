# Implementation Plan: Document Ingestion

## Overview

This plan implements the document ingestion feature: upload, validation, text extraction, intermediate representation generation, and temporary storage. Tasks are ordered by dependency — foundational modules first, then adapters, then orchestration and API layer, and finally integration verification.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": [1],
      "description": "Project scaffolding and Pydantic models"
    },
    {
      "wave": 2,
      "tasks": [2, 3, 4, 7],
      "description": "Database migration, validator, adapter base + Markdown, language detection"
    },
    {
      "wave": 3,
      "tasks": [5, 6, 8],
      "description": "Plain text adapter, PDF adapter, IR builder"
    },
    {
      "wave": 4,
      "tasks": [9],
      "description": "Storage service"
    },
    {
      "wave": 5,
      "tasks": [10],
      "description": "Ingestion service (pipeline orchestrator)"
    },
    {
      "wave": 6,
      "tasks": [11],
      "description": "API endpoints"
    },
    {
      "wave": 7,
      "tasks": [12],
      "description": "Integration tests"
    }
  ]
}
```

## Tasks

- [ ] 1. Project scaffolding and Pydantic models
  Create the backend directory structure under `src/backend/app/` and implement core Pydantic v2 models in `models/document.py`: `DocumentFormat` enum, `DetectedLanguage` enum, `ContentChunkModel`, `DocumentMetadata`, `IntermediateRepresentation`, `DocumentStatus`, and `ValidationErrorResponse`. All models must use `Field` descriptors and serialize to JSON matching the API response format defined in design.md.
  **Requirements: 3, 7**

- [ ] 2. Database migration
  Create `src/backend/app/db/migrations/001_create_documents.sql` with the `documents` table (document_id UUID PK, original_filename, format, size_bytes, language, upload_timestamp, warnings JSONB, status, error_message, expires_at, created_at) and `document_chunks` table (id UUID PK, document_id FK CASCADE, chunk_id, text, structural_context JSONB, order, created_at, UNIQUE on document_id+chunk_id). Include index `idx_chunks_document` on document_chunks(document_id).
  **Requirements: 3, 5**

- [ ] 3. Validator module
  Implement `src/backend/app/ingestion/validator.py` with `ValidationResult` dataclass and `Validator` class. The `validate(file_bytes, filename)` method checks: supported extension (.md, .txt, .pdf), size limits (1 MB for md/txt, 10 MB for pdf), and UTF-8 encoding for md/txt. Returns specific error codes (`unsupported_format`, `file_too_large`, `invalid_encoding`) with actionable user-facing messages. Write unit tests in `tests/unit/ingestion/test_validator.py`.
  **Requirements: 1.4, 1.5, 1.6, 1.7**

- [ ] 4. Format adapter base class and Markdown adapter
  Create `src/backend/app/ingestion/adapters/base.py` with `ContentChunk` dataclass, `ExtractionResult` dataclass, and `FormatAdapter` ABC (methods: `can_handle`, `extract`). Implement `MarkdownAdapter` in `markdown_adapter.py`: splits by h1/h2 headings via regex, one chunk per section, structural_context `{"section": "## Heading"}`, preamble content gets `{"section": "(preamble)"}`, h3+ stays within parent chunk. chunk_id format: `chunk-000`. Write unit tests with fixture files in `tests/fixtures/ingestion/markdown/`.
  **Requirements: 2.1, 7**

- [ ] 5. Plain text adapter
  Implement `PlainTextAdapter` in `plaintext_adapter.py`: single chunk by default, splits at ALL CAPS lines or lines followed by `===`/`---` underlines. Structural context: `{"section": "HEADING"}` or `{"section": "(document)"}`. Write unit tests with fixtures in `tests/fixtures/ingestion/plaintext/`.
  **Requirements: 2.2, 7**

- [ ] 6. PDF adapter
  Implement `PdfAdapter` in `pdf_adapter.py` using PyMuPDF: open with `fitz.open(stream=file_bytes, filetype="pdf")`, detect scanned PDFs (total text < 50 chars → reject with error), extract text per page with structural_context `{"page": N}` (1-indexed), split pages >4000 chars at paragraph boundaries, ignore images, extract simple tables as text, skip complex tables with warning. Implement `is_scanned_pdf()` helper. Write unit tests with fixtures in `tests/fixtures/ingestion/pdf/`.
  **Requirements: 2.3, 2.4, 2.5, 2.6, 2.7**

- [ ] 7. Language detection module
  Implement `LanguageDetector` in `src/backend/app/ingestion/language.py` with `detect(text_sample) -> DetectedLanguage`. Sample first 1000 chars, use stopword frequency matching (English: the/is/and, Spanish: el/la/de/que) plus character patterns (ñ, ¿, ¡). Return `UNKNOWN` if confidence below threshold. No LLM or network dependency. Write unit tests in `tests/unit/ingestion/test_language.py`.
  **Requirements: 4.1, 4.2, 4.3**

- [ ] 8. IR builder module
  Implement `IRBuilder` in `src/backend/app/ingestion/ir_builder.py` with `build(document_id, metadata, chunks) -> IntermediateRepresentation`. Validates sequential chunk ordering (0-indexed, no gaps) and unique chunk_ids — raises `ValueError` on violations. Write unit tests in `tests/unit/ingestion/test_ir_builder.py`.
  **Requirements: 3.1, 3.2, 3.3, 3.4, 3.5**

- [ ] 9. Storage service
  Implement `StorageService` in `src/backend/app/ingestion/storage.py` with async methods: `store_original` (Supabase Storage at `documents/{id}/original/{filename}`), `persist_ir` (insert into documents + document_chunks, set status=ready), `create_document_record` (status=processing), `mark_failed`, `get_status`, `get_ir`, `delete_expired` (query expires_at < now, cascade delete + remove storage files). Sanitize filenames. Read retention duration from `DOCUMENT_RETENTION_SECONDS` env var. No user metadata stored.
  **Requirements: 5.1, 5.2, 5.3, 5.4, 3.6**

- [ ] 10. Ingestion service (pipeline orchestrator)
  Implement `IngestionService` in `src/backend/app/ingestion/service.py`. Constructor receives Validator, list of FormatAdapters, LanguageDetector, IRBuilder, StorageService. Method `async ingest(file_bytes, filename, content_type) -> DocumentStatus` orchestrates: generate UUID → validate → create record → store original → select adapter → extract → detect language (first 1000 chars) → build IR → persist IR. Validation failures short-circuit. Extraction failures mark as failed.
  **Requirements: 1, 6, 7**

- [ ] 11. API endpoints
  Implement FastAPI router in `src/backend/app/api/v1/documents.py`: `POST /upload` (multipart, returns 202/400/422), `GET /{document_id}/status` (returns 200/404), `GET /{document_id}/ir` (returns 200/404/409). Create `src/backend/app/main.py` with app factory, CORS config, and dependency injection. Error responses use format: `{"error": "code", "message": "..."}`.
  **Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 6.3, 6.4**

- [ ] 12. Integration tests
  Write end-to-end tests in `tests/integration/ingestion/test_upload_flow.py` using httpx AsyncClient: upload each format → poll status → retrieve IR → verify structure. Test error scenarios (unsupported format, oversized, non-UTF-8, scanned PDF, non-existent document). Verify format-independent output (same content in .md and .txt → equivalent IR). Create fixture files in `tests/fixtures/ingestion/`.
  **Requirements: 1, 6, 7**

## Notes

- All tasks include unit tests alongside implementation (except Task 12 which is dedicated to integration tests).
- Tasks 3-9 can be parallelized after Task 1 is complete, but the dependency graph shows the recommended sequential order.
- The storage service (Task 9) requires Supabase credentials configured via environment variables for integration testing.
- Fixture PDF files for testing should be generated programmatically using PyMuPDF to avoid binary files in the repo.
