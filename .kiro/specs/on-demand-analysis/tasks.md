# Implementation Plan: On-Demand Analysis (Análisis Bajo Demanda)

## Overview

Implement the On-Demand Analysis feature (C3) that provides four document-level analyses triggered by the user after seeing the base analysis card. Each analysis uses a single LLM call with the full document IR, executes synchronously (5-15s), and persists results for future retrieval. Backend in Python (FastAPI + Pydantic v2), frontend in TypeScript (React + Zustand + Tailwind + shadcn/ui).

## Tasks

- [ ] 1. Define data models and database migration
  - [ ] 1.1 Create analysis result Pydantic models
    - Create `src/backend/app/analysis/on_demand/__init__.py`
    - Create `src/backend/app/analysis/on_demand/models.py`
    - Define `AnalysisType` enum (build_index, section_relations, questions_answered, conclusions)
    - Define `AnalysisStatus` enum (not_started, in_progress, completed, outdated, failed)
    - Define `SourceRef` model (chunk_ids: list[str], text_excerpt: str max 500 chars, section: str | None)
    - Define `StructureNode` model (id, title, level 1-6, role, question_answered, source_ref, children recursive)
    - Define `IndexResult` model (tree: list[StructureNode])
    - Define `SectionRelation` model (source_section, target_section, type, description, source_ref)
    - Define `RelationsResult` model (relations: list[SectionRelation])
    - Define `AnsweredQuestion` model (question, level: "document"|"section", section_title, source_ref)
    - Define `QuestionsResult` model (document_questions, section_questions)
    - Define `Observation` model (category, description, suggestion, section_ref, source_ref)
    - Define `ConclusionsResult` model (observations: list[Observation])
    - Define `AnalysisRecord` model (id, document_id, analysis_type, status, result: dict|None, model_id, prompt_version, error_message, created_at, updated_at)
    - _Requirements: Req 2 (criterion 2), Req 3 (criterion 2), Req 4 (criterion 2), Req 5 (criterion 3), Req 6 (criterion 8), Req 9 (criterion 1)_

  - [ ] 1.2 Create database migration
    - Create `src/backend/app/db/migrations/005_create_analysis_results.sql`
    - Table `analysis_results`: UUID PK, document_id FK, analysis_type TEXT, status TEXT DEFAULT 'not_started', result JSONB, model_id TEXT, prompt_version TEXT, error_message TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
    - UNIQUE constraint on (document_id, analysis_type)
    - Index on document_id
    - _Requirements: Req 6 (criteria 3, 5, 6)_

  - [ ] 1.3 Write unit tests for models
    - Create `tests/unit/analysis/on_demand/test_models.py`
    - Test SourceRef validation (text_excerpt max 500 chars)
    - Test StructureNode recursive children serialization
    - Test AnalysisRecord JSON serialization round-trip for each result type
    - Test enum values match design specification
    - _Requirements: Req 2 (criterion 2), Req 9 (criterion 1)_

- [ ] 2. Implement OnDemandAnalysisStorage
  - [ ] 2.1 Create storage module
    - Create `src/backend/app/analysis/on_demand/storage.py`
    - Implement `OnDemandAnalysisStorage` class with `__init__(self, supabase_client)`
    - `async get_result(document_id, analysis_type) -> AnalysisRecord | None`: query by document_id + analysis_type
    - `async save_result(record: AnalysisRecord) -> None`: upsert by (document_id, analysis_type) UNIQUE constraint
    - `async get_all_statuses(document_id) -> dict[str, dict]`: query all rows for document, return status + updated_at per type, fill missing types with "not_started"
    - `async mark_all_outdated(document_id) -> None`: update all rows for document_id to status="outdated"
    - _Requirements: Req 6 (criteria 3, 5, 6), Req 7 (criteria 6, 7)_

  - [ ] 2.2 Write unit tests for storage
    - Create `tests/unit/analysis/on_demand/test_storage.py`
    - Test get_result: existing, non-existing
    - Test save_result: insert new, update existing (upsert)
    - Test get_all_statuses: mix of existing and not_started types
    - Test mark_all_outdated: marks all, no-op if none exist
    - All tests mock Supabase client
    - _Requirements: Req 6 (criteria 3, 5, 6)_

- [ ] 3. Implement prompt templates
  - [ ] 3.1 Create Build Index prompt
    - Create `src/backend/app/analysis/on_demand/prompts/__init__.py`
    - Create `src/backend/app/analysis/on_demand/prompts/build_index.py`
    - Define `PROMPT_VERSION = "build-index-v1"`
    - Define `PROMPT_TEMPLATE` with: response_language instruction, instructions to build hierarchical tree with role + question_answered cascade, JSON schema for IndexResult, document content placeholder
    - _Requirements: Req 2 (criteria 1-6)_

  - [ ] 3.2 Create Section Relations prompt
    - Create `src/backend/app/analysis/on_demand/prompts/section_relations.py`
    - Define `PROMPT_VERSION = "section-relations-v1"`
    - Define `PROMPT_TEMPLATE` with: response_language, instructions to identify relationships (constrains, depends_on, complements, contradicts), exclude trivial connections, JSON schema, document content
    - _Requirements: Req 3 (criteria 1-5)_

  - [ ] 3.3 Create Questions Answered prompt
    - Create `src/backend/app/analysis/on_demand/prompts/questions_answered.py`
    - Define `PROMPT_VERSION = "questions-answered-v1"`
    - Define `PROMPT_TEMPLATE` with: response_language, instructions for cascade (3-5 document-level, 1-2 per section), specific/actionable questions, JSON schema, document content
    - _Requirements: Req 4 (criteria 1-6)_

  - [ ] 3.4 Create Conclusions prompt
    - Create `src/backend/app/analysis/on_demand/prompts/conclusions.py`
    - Define `PROMPT_VERSION = "conclusions-v1"`
    - Define `PROMPT_TEMPLATE` with: response_language for description, document_language for suggestion, categories (coherence, reordering, duplication, orphan, missing), structural-only suggestions, JSON schema, document content
    - _Requirements: Req 5 (criteria 1-5)_

- [ ] 4. Implement analyzers
  - [ ] 4.1 Create IndexAnalyzer
    - Create `src/backend/app/analysis/on_demand/index_analyzer.py`
    - Implement `IndexAnalyzer` class with `__init__(self, llm_client: LLMClient)`
    - `async analyze(ir, language, model_override, auto_fallback) -> IndexResult`
    - Build full document text from IR chunks with section markers
    - Format prompt with response_language and document text
    - Call `LLMClient.call(prompt, model_tier="primary", temperature=0.1, ...)` with 30s timeout
    - Parse JSON response, validate StructureNode tree structure
    - Raise on failure (let service handle error)
    - _Requirements: Req 2 (criteria 1-7)_

  - [ ] 4.2 Create RelationsAnalyzer
    - Create `src/backend/app/analysis/on_demand/relations_analyzer.py`
    - Implement `RelationsAnalyzer` class with `__init__(self, llm_client: LLMClient)`
    - `async analyze(ir, language, model_override, auto_fallback, index_result: IndexResult | None = None) -> RelationsResult`
    - Same pattern: build text, format prompt, call LLM, parse JSON
    - If `index_result` is provided, include structure_tree node IDs in prompt so the LLM can reference them in source_section/target_section fields
    - If `index_result` is None, relations reference section titles from the IR chunks
    - Validate relation types against vocabulary (constrains, depends_on, complements, contradicts)
    - _Requirements: Req 3 (criteria 1-7)_

  - [ ] 4.3 Create QuestionsAnalyzer
    - Create `src/backend/app/analysis/on_demand/questions_analyzer.py`
    - Implement `QuestionsAnalyzer` class with `__init__(self, llm_client: LLMClient)`
    - `async analyze(ir, language, model_override, auto_fallback) -> QuestionsResult`
    - Parse and validate cascade structure: document_questions + section_questions
    - _Requirements: Req 4 (criteria 1-7)_

  - [ ] 4.4 Create ConclusionsAnalyzer
    - Create `src/backend/app/analysis/on_demand/conclusions_analyzer.py`
    - Implement `ConclusionsAnalyzer` class with `__init__(self, llm_client: LLMClient)`
    - `async analyze(ir, language, document_language, model_override, auto_fallback) -> ConclusionsResult`
    - Takes both `language` (for description) and `document_language` (for suggestion) per language rules
    - Validate categories against allowed set
    - _Requirements: Req 5 (criteria 1-7)_

  - [ ] 4.5 Create shared text preparation utility
    - Create helper function `prepare_document_text(ir: IntermediateRepresentation) -> str`
    - Concatenates all chunks with section markers: `[Section: {section}] (chunk {order})\n{text}\n`
    - Used by all four analyzers
    - _Requirements: Req 2 (criterion 1), Req 3 (criterion 1), Req 4 (criterion 1), Req 5 (criterion 1)_

  - [ ] 4.6 Write unit tests for analyzers
    - Create `tests/unit/analysis/on_demand/test_index_analyzer.py`
    - Create `tests/unit/analysis/on_demand/test_relations_analyzer.py`
    - Create `tests/unit/analysis/on_demand/test_questions_analyzer.py`
    - Create `tests/unit/analysis/on_demand/test_conclusions_analyzer.py`
    - For each: test successful parse, test invalid JSON raises, test timeout raises, test prompt includes full document text, test language parameter applied
    - All tests mock LLMClient
    - _Requirements: Req 2-5 (all criteria)_

- [ ] 5. Implement OnDemandAnalysisService
  - [ ] 5.1 Create service orchestrator
    - Create `src/backend/app/analysis/on_demand/service.py`
    - Implement `OnDemandAnalysisService` with `__init__(self, index_analyzer, relations_analyzer, questions_analyzer, conclusions_analyzer, storage, ingestion_storage)`
    - `async execute(document_id, analysis_type, preferences) -> AnalysisRecord`:
      - Check storage for existing completed non-outdated result → return if found (idempotency)
      - Load IR from ingestion_storage → raise if not available
      - Route to correct analyzer based on analysis_type
      - For section_relations: check if build_index result exists, pass it to RelationsAnalyzer if available
      - On success: build AnalysisRecord with status="completed", persist, return
      - On failure: raise (endpoint handles error response)
    - `async get_result(document_id, analysis_type) -> AnalysisRecord | None`: delegate to storage
    - `async get_all_statuses(document_id) -> dict`: delegate to storage
    - _Requirements: Req 6 (criteria 1-8), Req 7 (criteria 2, 3)_

  - [ ] 5.2 Write unit tests for service
    - Create `tests/unit/analysis/on_demand/test_service.py`
    - Test execute: successful (new analysis)
    - Test execute: idempotent (existing completed result returned without LLM call)
    - Test execute: outdated result triggers fresh execution
    - Test execute: LLM failure propagates as exception
    - Test execute: IR not available raises appropriate error
    - Test get_result delegates to storage
    - Test get_all_statuses returns correct map
    - All tests mock analyzers + storage
    - _Requirements: Req 6 (criteria 1-8)_

- [ ] 6. Implement API endpoints
  - [ ] 6.1 Create analyses router
    - Create `src/backend/app/api/v1/analyses.py`
    - `POST /api/v1/documents/{document_id}/analyses/{analysis_type}`:
      - Validate analysis_type against enum
      - Inject RequestPreferences dependency
      - Call service.execute(document_id, analysis_type, preferences)
      - Return 200 with AnalysisRecord on success
      - Return 404 if document not found
      - Return 409 if IR not available
      - Return 502 if LLM call fails
    - `GET /api/v1/documents/{document_id}/analyses`:
      - Call service.get_all_statuses(document_id)
      - Return 200 with status summary
    - `GET /api/v1/documents/{document_id}/analyses/{analysis_type}`:
      - Call service.get_result(document_id, analysis_type)
      - Return 200 with result or "not_started" status
      - Return 404 if document not found
    - _Requirements: Req 7 (criteria 1-9)_

  - [ ] 6.2 Register router in application factory
    - Modify `src/backend/app/main.py`
    - Import and include analyses router with prefix `/api/v1/documents`
    - Wire OnDemandAnalysisService with all dependencies (analyzers, storage, ingestion_storage)
    - Set up dependency_overrides for the analysis service
    - _Requirements: Req 7 (criteria 1-9)_

  - [ ] 6.3 Wire outdated propagation on re-upload
    - Modify `src/backend/app/api/v1/documents.py` or `BaseAnalysisService`
    - When a document is re-uploaded and card is marked outdated, also call `OnDemandAnalysisStorage.mark_all_outdated(document_id)`
    - _Requirements: Req 6 (criterion 6)_

  - [ ] 6.4 Write integration tests for API endpoints
    - Create `tests/integration/analysis/test_on_demand_flow.py`
    - Test POST trigger: returns 200 with result
    - Test POST trigger: idempotent (second call returns cached)
    - Test POST trigger: 404 for non-existent document
    - Test POST trigger: 409 for document without IR
    - Test POST trigger: 502 on LLM failure
    - Test GET all statuses: correct summary
    - Test GET single: completed result, not_started result
    - Tests use httpx TestClient with mocked LLM
    - _Requirements: Req 7 (criteria 1-9)_

- [ ] 7. Create frontend types and API client
  - [ ] 7.1 Create TypeScript interfaces
    - Create `src/frontend/src/types/analysis.ts`
    - Define types: AnalysisType, AnalysisStatus, SourceRef, StructureNode, SectionRelation, AnsweredQuestion, Observation, AnalysisStatusSummary
    - Define response interfaces for each result type
    - _Requirements: Req 8 (criteria 1-4)_

  - [ ] 7.2 Create API client functions
    - Create `src/frontend/src/api/analyses.ts`
    - `triggerAnalysis(documentId, type): Promise<AnalysisResult>` — POST with preference headers, uses `apiFetch`
    - `getAnalysisStatuses(documentId): Promise<AnalysisStatusSummary>` — GET all statuses
    - `getAnalysisResult(documentId, type): Promise<AnalysisResult>` — GET single result
    - Handle error responses (404, 409, 502) with typed errors
    - _Requirements: Req 7 (criteria 1-9)_

  - [ ] 7.3 Create Zustand store
    - Create `src/frontend/src/store/analysisStore.ts`
    - State: `statuses: AnalysisStatusSummary | null`, `results: Partial<Record<AnalysisType, any>>`, `activeAnalysis: AnalysisType | null`, `error: string | null`
    - Actions: `fetchStatuses(documentId)`, `triggerAnalysis(documentId, type)`, `fetchResult(documentId, type)`, `reset()`
    - `triggerAnalysis`: sets activeAnalysis (optimistic in_progress), calls API, on success updates result + status, on failure sets error
    - _Requirements: Req 1 (criteria 6-10), Req 8 (criteria 1-4)_

- [ ] 8. Implement Options Panel component
  - [ ] 8.1 Create OptionsPanel
    - Create `src/frontend/src/components/analysis/OptionsPanel.tsx`
    - Props: `documentId: string`, `classification: string | null`
    - On mount: call `fetchStatuses(documentId)` from store
    - Render 4 analysis options (or 2 for narrative classification)
    - Each option shows: name (i18n), one-line description, status badge
    - Status-based rendering:
      - not_started → clickable button (triggers analysis)
      - in_progress → spinner, non-interactive
      - completed → link to view results
      - outdated → warning badge + "View" + "Re-analyze" buttons
      - failed → error badge + "Retry" button
    - Use shadcn/ui Card, Button, Badge components
    - _Requirements: Req 1 (criteria 1-10)_

  - [ ] 8.2 Add i18n keys for analysis options
    - Modify `src/frontend/src/i18n/es.json`: add `analysis.*` section with names, descriptions, statuses for each type
    - Modify `src/frontend/src/i18n/en.json`: same structure in English
    - _Requirements: Req 1 (criteria 2, 6-10)_

  - [ ] 8.3 Write component tests for OptionsPanel
    - Create `src/frontend/tests/components/analysis/OptionsPanel.test.tsx`
    - Test renders all 4 options for non-narrative
    - Test renders only 2 options for narrative classification
    - Test renders all 4 when classification is null (partial card)
    - Test click triggers analysis
    - Test status indicators render correctly per state
    - _Requirements: Req 1 (criteria 1-10)_

- [ ] 9. Implement results display components
  - [ ] 9.1 Create IndexTreeView
    - Create `src/frontend/src/components/analysis/IndexTreeView.tsx`
    - Renders StructureNode tree as expandable/collapsible
    - Each node shows: title, role badge (if present), question_answered
    - Expand node to reveal source_ref (SourceRefPopover)
    - Recursive rendering for children
    - Keyboard navigable (arrow keys expand/collapse)
    - _Requirements: Req 8 (criterion 1), Req 9 (criterion 2)_

  - [ ] 9.2 Create RelationsListView
    - Create `src/frontend/src/components/analysis/RelationsListView.tsx`
    - Groups relations by type (constrains, depends_on, complements, contradicts)
    - Each group has a heading with type label
    - Each relation shows: source → target, description, expandable source_ref
    - _Requirements: Req 8 (criterion 2), Req 9 (criterion 2)_

  - [ ] 9.3 Create QuestionsCascadeView
    - Create `src/frontend/src/components/analysis/QuestionsCascadeView.tsx`
    - Document-level questions displayed prominently at top
    - Section-level questions grouped under their parent section title
    - Each question expandable to show source_ref
    - _Requirements: Req 8 (criterion 3), Req 9 (criterion 2)_

  - [ ] 9.4 Create ConclusionsView
    - Create `src/frontend/src/components/analysis/ConclusionsView.tsx`
    - Groups observations by category
    - Each observation shows: description, structural suggestion (visually distinct), section_ref, expandable source_ref
    - Clear visual separation between description (ui_language) and suggestion (document_language)
    - _Requirements: Req 8 (criterion 4), Req 9 (criterion 2)_

  - [ ] 9.5 Create SourceRefPopover
    - Create `src/frontend/src/components/analysis/SourceRefPopover.tsx`
    - Shared component used by all result views
    - Shows text_excerpt with section context on expand/click
    - If source_ref is null, shows "Unverified" badge
    - Accessible: aria-expanded, keyboard trigger
    - _Requirements: Req 9 (criteria 1-4)_

  - [ ] 9.6 Create AnalysisResultView router
    - Create `src/frontend/src/components/analysis/AnalysisResultView.tsx`
    - Props: `analysisType`, `result`
    - Routes to correct view component based on type
    - Shows "outdated" banner when status is outdated, with "Re-analyze" button
    - _Requirements: Req 8 (criteria 6, 7)_

- [ ] 10. Integrate into post-upload flow
  - [ ] 10.1 Add OptionsPanel to UploadPage
    - Modify `src/frontend/src/components/upload/UploadPage.tsx`
    - After DocumentCardSection, render OptionsPanel when card is available
    - Pass documentId and card.classification to OptionsPanel
    - _Requirements: Req 1 (criterion 1)_

  - [ ] 10.2 Add AnalysisResultView below OptionsPanel
    - When user triggers or views an analysis, display results below the options panel
    - Use store's activeAnalysis and results to determine what to show
    - _Requirements: Req 8 (criteria 1-7)_

  - [ ] 10.3 Add accessibility attributes
    - All interactive elements keyboard navigable
    - ARIA labels on status badges, buttons, expandable sections
    - Live region for status changes (analysis started, completed)
    - _Requirements: Req 8 (criterion 5)_

- [ ] 11. Integration verification
  - [ ] 11.1 Frontend build verification
    - Run `npx vite build` — must complete without errors
    - Verify no TypeScript errors in source files

  - [ ] 11.2 Backend startup verification
    - Run `python -m uvicorn app.run:app` — must start without import errors
    - Verify new endpoints appear in Swagger docs at /docs

  - [ ] 11.3 Manual integration checklist
    - Upload document → card appears → Options Panel visible below card
    - Narrative document → only Questions + Conclusions shown
    - Click "Build Index" → spinner → tree appears (5-15s)
    - Click "Build Index" again → cached result returned instantly
    - Click "Section Relations" → relations list appears
    - Click "Questions Answered" → cascade displayed
    - Click "Conclusions" → observations displayed
    - Each result has expandable source_ref
    - Re-upload document → options show "outdated"
    - Click "Re-analyze" → fresh result replaces old

## Notes

- Tasks 1, 2, and 3 are independent and can be developed in parallel
- Task 4 depends on Tasks 1 and 3 (needs models + prompts)
- Task 5 depends on Tasks 2 and 4 (needs storage + analyzers)
- Task 6 depends on Task 5 (needs service)
- Tasks 7 and 8 depend on Task 1 (need types) but can proceed in parallel with backend tasks
- Task 9 depends on Task 7 (needs store + types)
- Task 10 depends on Tasks 8 and 9 (needs components)
- Task 11 depends on all previous tasks
- All analyzers follow the same pattern — implement one, copy for the rest
- Migration must be run in Supabase before testing persistence
- No new npm dependencies needed (shadcn/ui already installed)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "3.1", "3.2", "3.3", "3.4"] },
    { "id": 1, "tasks": ["1.3", "2.2", "4.5", "7.1"] },
    { "id": 2, "tasks": ["4.1", "4.2", "4.3", "4.4", "7.2", "7.3"] },
    { "id": 3, "tasks": ["4.6", "5.1", "8.1", "8.2"] },
    { "id": 4, "tasks": ["5.2", "6.1", "6.2", "6.3", "8.3"] },
    { "id": 5, "tasks": ["6.4", "9.1", "9.2", "9.3", "9.4", "9.5", "9.6"] },
    { "id": 6, "tasks": ["10.1", "10.2", "10.3"] },
    { "id": 7, "tasks": ["11.1", "11.2", "11.3"] }
  ]
}
```
