# Implementation Plan: Base Analysis (Análisis Base)

## Overview

Implement the Base Analysis feature (C2) that automatically produces a "document card" within 5 seconds of upload. The card combines deterministic local processing (title, statistics, organization type, index detection, file metadata) with a single LLM call to the light model (Groq) for summary and classification. Graceful degradation ensures users always see local data even if the LLM fails. Backend in Python (FastAPI + Pydantic v2), frontend in TypeScript (React + Zustand + Tailwind + shadcn/ui).

## Tasks

- [ ] 1. Define document card data models and database migration
  - [ ] 1.1 Create DocumentCard Pydantic models
    - Create `src/backend/app/models/document_card.py` with: `OrganizationType` enum (numbered_articles, headed_sections, hierarchical_numbering, free_form), `DocumentClassification` enum (normative, guide, manual, procedure, technical, narrative, other), `DocumentCardStatistics` model (total_chunks, sections_detected, hierarchy_levels, has_existing_index), `FileMetadata` model (size_bytes, format, language, last_modified), `DocumentCard` model (id, document_id, title, summary, classification, organization_type, statistics, file_metadata, status, outdated, model_id, prompt_version, created_at, updated_at)
    - `status` is Literal["completed", "failed_llm", "partial"]
    - `summary` and `classification` are nullable (null when status=partial)
    - `outdated: bool = False` for change detection
    - _Requirements: Req 4 (criteria 1, 2), Req 6 (criterion 1)_

  - [ ] 1.2 Create database migration
    - Create SQL migration for `document_cards` table with: UUID primary key, UNIQUE constraint on document_id (FK to documents), JSONB columns for statistics and file_metadata, outdated BOOLEAN DEFAULT false, index on document_id
    - _Requirements: Req 4 (criterion 1)_

  - [ ] 1.3 Write unit tests for card models
    - Create `src/backend/tests/unit/analysis/base_analysis/test_card_models.py`
    - Test Pydantic v2 serialization/deserialization round-trips
    - Test enum values match design specification
    - Test nullable fields (summary, classification null when partial)
    - Test outdated default is False
    - _Requirements: Req 4 (criterion 2)_

- [ ] 2. Implement LocalAnalyzer
  - [ ] 2.1 Create LocalAnalyzer module
    - Create `src/backend/app/analysis/base_analysis/__init__.py`
    - Create `src/backend/app/analysis/base_analysis/local_analyzer.py`
    - Implement `LocalAnalyzer` class with `analyze(ir) -> LocalAnalysisResult`
    - `_extract_title`: iterate chunks sorted by order, return first `structural_context.section` found; fallback to filename without extension
    - `_compute_statistics`: count total chunks, unique sections (distinct `structural_context.section`), max hierarchy level (`structural_context.level`, default 1), detect existing index
    - `_detect_organization_type`: priority order — numbered_articles (regex `Art\.\s*\d+|Artículo\s+\d+|ARTICULO`) > headed_sections (chunks with `structural_context.level`) > hierarchical_numbering (regex `\d+\.\d+`) > free_form
    - `_detect_existing_index`: search first 20% of chunks for TOC patterns (short lines with page numbers, dot/dash separators, section names containing "índice"/"contenido"/"table of contents"/"contents" case-insensitive)
    - `_build_file_metadata`: extract size_bytes, format, language from IR metadata
    - No network calls, no LLM calls, no external service calls
    - _Requirements: Req 2 (criteria 1-7)_

  - [ ] 2.2 Write unit tests for LocalAnalyzer
    - Create `src/backend/tests/unit/analysis/base_analysis/test_local_analyzer.py`
    - Test title extraction: from first heading, from filename fallback
    - Test statistics: chunk count, section count, hierarchy levels, default level
    - Test organization type detection: each type with synthetic IR, priority order
    - Test index detection: positive cases (TOC patterns), negative cases
    - Test file metadata assembly
    - Test performance: verify <100ms for large synthetic IR (up to 10MB equivalent)
    - All tests use synthetic IntermediateRepresentation objects
    - _Requirements: Req 2 (criteria 1-7)_

- [ ] 3. Implement LLMAnalyzer
  - [ ] 3.1 Create LLMAnalyzer module and prompt template
    - Create `src/backend/app/analysis/base_analysis/llm_analyzer.py`
    - Implement `LLMAnalyzer` class with `__init__(self, llm_client: LLMClient)`
    - Implement `async analyze(title, chunks, organization_type) -> LLMAnalysisResult | None`
    - Build prompt with title, organization_type, and text sample (first 10 chunks concatenated, max 2000 chars)
    - Call `LLMClient.call(prompt, model_tier="light", temperature=0.1)` wrapped in `asyncio.wait_for(timeout=10)`
    - Parse response as JSON with fields "summary" and "classification"
    - Return None on any failure (timeout, LLM error, invalid JSON, missing fields)
    - Log failures without raising exceptions
    - Create `src/backend/app/analysis/base_analysis/prompts.py` with `PROMPT_TEMPLATE` and `PROMPT_VERSION = "base-analysis-v1"`
    - Prompt instructs: respond with JSON only, summary of 2-3 lines, classification from fixed set
    - _Requirements: Req 3 (criteria 1-7)_

  - [ ] 3.2 Write unit tests for LLMAnalyzer
    - Create `src/backend/tests/unit/analysis/base_analysis/test_llm_analyzer.py`
    - Test successful call: valid JSON response → LLMAnalysisResult
    - Test timeout: asyncio.TimeoutError → returns None
    - Test LLM error: LLMTransientError → returns None
    - Test invalid JSON response → returns None
    - Test missing fields in JSON → returns None
    - Test prompt construction: includes title, org_type, text sample ≤2000 chars
    - Test model_tier="light" and temperature=0.1 are passed
    - Test PROMPT_VERSION is included in result
    - All tests mock LLMClient
    - _Requirements: Req 3 (criteria 1-7)_

- [ ] 4. Implement BaseAnalysisStorage
  - [ ] 4.1 Create BaseAnalysisStorage module
    - Create `src/backend/app/analysis/base_analysis/storage.py`
    - Implement `BaseAnalysisStorage` class with `__init__(self, supabase_client)`
    - `async get_card(document_id) -> DocumentCard | None`: query document_cards by document_id
    - `async upsert_card(card: DocumentCard) -> None`: insert or update (by document_id), reset outdated to False on upsert
    - `async mark_outdated(document_id) -> None`: set outdated=True on existing card
    - _Requirements: Req 4 (criteria 1, 3, 4), Req 6 (criteria 1, 3)_

  - [ ] 4.2 Write unit tests for BaseAnalysisStorage
    - Create `src/backend/tests/unit/analysis/base_analysis/test_storage.py`
    - Test get_card: existing card, non-existing card
    - Test upsert_card: insert new, update existing
    - Test upsert_card: outdated resets to False
    - Test mark_outdated: sets outdated=True
    - All tests mock Supabase client
    - _Requirements: Req 4 (criteria 1, 3), Req 6 (criterion 1)_

- [ ] 5. Implement BaseAnalysisService orchestrator
  - [ ] 5.1 Create BaseAnalysisService module
    - Create `src/backend/app/analysis/base_analysis/service.py`
    - Implement `BaseAnalysisService` with `__init__(local_analyzer, llm_analyzer, storage)`
    - `async analyze(document_id, ir) -> DocumentCard`: check existing card (idempotency by status + size_bytes), run local → run LLM → build card → upsert
    - If LLM returns None: status="partial", summary=None, classification=None
    - If LLM succeeds: status="completed" with all fields
    - Does not raise exceptions — all failures result in partial card
    - `async retry_llm(document_id, ir) -> DocumentCard`: load existing card, re-execute LLM, update fields (summary, classification, model_id, prompt_version, status, updated_at), persist
    - Raise `CardNotFoundError` if no card exists for retry
    - _Requirements: Req 1 (criteria 3, 4), Req 4 (criterion 4), Req 5 (criteria 1, 2, 3)_

  - [ ] 5.2 Write unit tests for BaseAnalysisService
    - Create `src/backend/tests/unit/analysis/base_analysis/test_service.py`
    - Test analyze: successful (completed card)
    - Test analyze: LLM fails (partial card saved)
    - Test analyze: idempotent (existing completed card returned without re-execution)
    - Test analyze: does not raise on any failure
    - Test retry_llm: success updates card to completed
    - Test retry_llm: LLM fails again sets status="failed_llm"
    - Test retry_llm: raises CardNotFoundError when no card exists
    - All tests mock LocalAnalyzer, LLMAnalyzer, BaseAnalysisStorage
    - _Requirements: Req 1 (criteria 3, 4), Req 5 (criteria 1, 2, 3)_

- [ ] 6. Implement API endpoints
  - [ ] 6.1 Create card API router
    - Create `src/backend/app/api/v1/card.py`
    - `GET /api/v1/documents/{document_id}/card`: return 200 with DocumentCard, or 404 (card_not_found vs document_not_found)
    - `POST /api/v1/documents/{document_id}/card/retry-llm`: return 200 (updated card), 404 (card_not_found), or 409 (card_already_complete)
    - Validate document_id as UUID
    - Register router in application
    - _Requirements: Req 7 (criteria 1-6)_

  - [ ] 6.2 Write integration tests for API endpoints
    - Create `src/backend/tests/integration/analysis/test_base_analysis_flow.py`
    - Test GET /card with existing completed card → 200
    - Test GET /card with no card → 404 (card_not_found)
    - Test GET /card with non-existent document → 404 (document_not_found)
    - Test POST /retry-llm on partial card → 200
    - Test POST /retry-llm on completed card → 409
    - Test POST /retry-llm with no card → 404
    - Tests use httpx TestClient with mocked dependencies
    - _Requirements: Req 7 (criteria 1-6)_

- [ ] 7. Integrate with ingestion pipeline
  - [ ] 7.1 Add BackgroundTask trigger
    - Modify upload endpoint (in `src/backend/app/api/v1/documents.py` or equivalent) to add `background_tasks.add_task(base_analysis_service.analyze, document_id, ir)` after successful ingestion (status=ready)
    - Wire/instantiate BaseAnalysisService with all dependencies (LocalAnalyzer, LLMAnalyzer, BaseAnalysisStorage)
    - Ensure upload response returns immediately without waiting for analysis
    - Ensure analysis failure does not affect document status
    - _Requirements: Req 1 (criteria 1, 2, 4)_

  - [ ] 7.2 Write end-to-end integration test
    - Test full flow: upload document → ingestion → background analysis → GET /card returns completed card
    - Test with mocked LLM failure: upload → GET /card returns partial card
    - _Requirements: Req 1 (criteria 1, 2), Req 5 (criterion 4)_

- [ ] 8. Implement frontend store and API client
  - [ ] 8.1 Create TypeScript interfaces
    - Create `src/frontend/src/types/documentCard.ts`
    - Interface `DocumentCard` with all fields in camelCase, including `outdated: boolean`
    - _Requirements: Req 8 (criterion 2)_

  - [ ] 8.2 Create API client functions
    - Create `src/frontend/src/api/documentCard.ts`
    - `fetchCard(documentId: string): Promise<DocumentCard>` — calls GET /card
    - `retryLlm(documentId: string): Promise<DocumentCard>` — calls POST /retry-llm
    - Handle error responses (404, 409) with typed errors
    - _Requirements: Req 7 (criteria 1, 4), Req 8 (criteria 1, 4)_

  - [ ] 8.3 Create Zustand store
    - Create `src/frontend/src/store/documentCardStore.ts`
    - State: `card: DocumentCard | null`, `loading: boolean`, `error: string | null`
    - Actions: `fetchCard(documentId)`, `retryLlm(documentId)`, `reset()`
    - _Requirements: Req 8 (criteria 1, 4)_

- [ ] 9. Implement frontend card components
  - [ ] 9.1 Create DocumentCardSkeleton
    - Create `src/frontend/src/components/document-card/DocumentCardSkeleton.tsx`
    - Loading state using shadcn/ui Skeleton component
    - ARIA live region to announce loading state to screen readers
    - _Requirements: Req 8 (criteria 1, 7)_

  - [ ] 9.2 Create DocumentCardView
    - Create `src/frontend/src/components/document-card/DocumentCardView.tsx`
    - Display completed card: title (prominent), summary, classification badge, organization type, statistics, file metadata
    - Display partial card: local fields + "Reintentar análisis" button (no placeholder text for missing fields)
    - Display outdated indicator when `outdated=true`
    - Use shadcn/ui components: Card, Badge, Button, Skeleton
    - Accessible: keyboard navigable, WCAG 2.1 AA contrast on badges (4.5:1 text)
    - _Requirements: Req 8 (criteria 2, 3, 6, 7)_

- [ ] 10. Integrate card into post-upload flow
  - [ ] 10.1 Implement polling and integration
    - Connect DocumentCardView to upload flow (App.tsx or layout component)
    - After upload success: show DocumentCardSkeleton, start polling fetchCard every 1.5s (max 10 attempts, 15s total)
    - On card received: display DocumentCardView
    - On polling exhausted: show informational message + manual retry button
    - On retry button click (partial card): call retryLlm, show loading, update on success
    - _Requirements: Req 8 (criteria 1, 4, 5)_

## Notes

- Each task references specific requirements (Req N criterion M) for traceability
- Tasks 2, 3, and 4 are independent and can be developed in parallel after Task 1
- All backend tests use mocked LLM responses and mocked Supabase client
- No new dependencies beyond the project's established stack
- The base analysis is the prerequisite for all on-demand analyses (C3) — the card establishes the document's classification which determines available analyses

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.2"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2", "8.1", "8.2", "8.3"] },
    { "id": 7, "tasks": ["9.1", "9.2"] },
    { "id": 8, "tasks": ["10.1"] }
  ]
}
```
