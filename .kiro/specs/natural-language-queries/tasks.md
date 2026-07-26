# Implementation Plan: Natural Language Queries

## Overview

Implement the Natural Language Queries feature (Feature 6) that enables users to ask questions about their document in natural language and receive structured, evidence-grounded answers from the Knowledge Model. The implementation follows the pipeline: context construction → LLM call → response parsing → evidence verification. Backend in Python (FastAPI + Pydantic), frontend in TypeScript (React + Zustand + Tailwind + shadcn/ui).

## Tasks

- [ ] 1. Define query data models and prompt templates
  - [ ] 1.1 Create query Pydantic models
    - Create `src/backend/app/models/query.py` with: `QueryRequest`, `QueryResponse`, `QuerySourceRef`, `QueryMetadata`, `QueryErrorResponse`, `QueryContext`, `QueryContextElement`, `QueryContextRelation`
    - `QueryRequest`: question field with min_length=1, max_length=1000
    - `QueryResponse`: answer (max 5000 chars), answerable bool, source_refs (max 10), all_evidence_unverified bool, metadata
    - `QuerySourceRef`: document_id, chunk_id, page (optional), section (optional), evidence (max 500 chars), evidence_verified bool
    - `QueryMetadata`: prompt_version, model_id, temperature, timestamp (datetime UTC)
    - `QueryErrorResponse`: error code, message, optional question
    - `QueryContext`: elements list, relations list, total_tokens int, has_unverified_elements bool
    - `QueryContextElement`: element_id, type, name, content, evidence, verified
    - `QueryContextRelation`: source_id, target_id, type, optional description
    - _Requirements: 1.1, 1.4, 3.1, 3.2, 3.5, 3.6, 5.1_

  - [ ] 1.2 Create query answering prompt template
    - Create `src/backend/app/analysis/prompts/query_answering_v1.py`
    - Define `VERSION = "query-answering-v1"` constant
    - Implement `build(context_elements: list, relations: list, question: str) -> str` function
    - Prompt requires: direct answer from context only, 1–10 evidence references (verbatim spans), JSON output conforming to QueryResponse schema, explicit "cannot answer" instruction when context is insufficient, grounding instruction (every claim → evidence span), [UNVERIFIED] annotation for unverified context elements
    - Include only: KM element fields (type, name, content, evidence), relations (source_id, target_id, type), user question as plain string — no user identity, session history, account metadata, or document_id
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 2.6, 7.2_

  - [ ] 1.3 Create query relevance scoring prompt template
    - Create `src/backend/app/analysis/prompts/query_relevance_scoring_v1.py`
    - Define `VERSION = "query-relevance-scoring-v1"` constant
    - Implement `build(question: str, element_summaries: list[dict[str, str]]) -> str` function
    - Prompt asks LLM to score each element 0–10 for relevance to the question
    - Input: element summaries with id, type, name, content_preview (first 100 chars)
    - Output format: JSON array of {"id": "...", "score": N}
    - _Requirements: 2.1, 6.1_

  - [ ]* 1.4 Write unit tests for query models
    - Create `src/backend/tests/unit/analysis/query/test_query_models.py`
    - Test validation: question min/max length, answer max length, evidence max 500 chars, source_refs max 10
    - Test defaults: evidence_verified=False, all_evidence_unverified=False
    - Test serialization/deserialization round-trips
    - _Requirements: 1.1, 1.8, 3.5, 5.1, 5.4_

- [ ] 2. Implement ContextBuilder
  - [ ] 2.1 Implement ContextBuilder module
    - Create `src/backend/app/analysis/query/__init__.py`
    - Create `src/backend/app/analysis/query/context_builder.py`
    - Implement `ContextBuilder` class with `__init__(self, llm_client, max_elements=20, budget_ratio=0.6)`
    - Implement `async build_context(self, question, knowledge_model, ir, context_window_tokens) -> QueryContext | None`
    - Score KM elements via single LLM call using `query_relevance_scoring_v1.build()` (light model tier)
    - Select top-N elements (max 20) based on relevance scores
    - Include first-degree relationships (one hop only) from directly relevant elements
    - Annotate unverified elements with [UNVERIFIED] marker
    - Enforce 60% token budget using `len(text) / 4` heuristic; trim in reverse priority: relational context first, then lower-scored direct elements
    - Prioritize: directly relevant > relationally connected > verified over unverified
    - Return None if zero elements meet relevance criteria
    - On scoring LLM failure: fallback to including all elements up to token budget (no ranking)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 2.2 Write unit tests for ContextBuilder
    - Create `src/backend/tests/unit/analysis/query/test_context_builder.py`
    - Test element selection with mocked LLM scoring responses
    - Test max 20 element cap enforcement
    - Test one-hop relational context inclusion (not two-hop)
    - Test 60% token budget enforcement (trim behavior)
    - Test priority ordering (direct > relational > verified preference)
    - Test fallback behavior when scoring LLM fails
    - Test returns None when no elements are relevant
    - Test unverified element annotation
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.7_

  - [ ]* 2.3 Write property test for Context Budget Compliance (Property 2)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 2: Context Budget Compliance**
    - Generate KMs of varying sizes (1–100 elements), verify max 20 elements selected and total_tokens ≤ 60% of context_window_tokens
    - Use mocked LLM scoring that returns random scores
    - **Validates: Requirements 2.1, 2.4**

  - [ ]* 2.4 Write property test for Relational Context One-Hop Bound (Property 3)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 3: Relational Context One-Hop Bound**
    - Generate KMs with deep relationship chains (3+ hops), verify only elements reachable in exactly one hop from directly relevant elements appear in context
    - **Validates: Requirements 2.2**

- [ ] 3. Implement ResponseParser
  - [ ] 3.1 Implement ResponseParser module
    - Create `src/backend/app/analysis/query/response_parser.py`
    - Implement `ResponseParser` class
    - Implement `parse(self, raw_output: str, document_id: str) -> QueryResponse` — extracts JSON from LLM output, validates against QueryResponse Pydantic schema, sets document_id on each source_ref (LLM output has only chunk_ids)
    - Implement `build_corrective_reprompt(self, original_prompt: str, raw_output: str, error: str) -> str` — includes original prompt, invalid output, and specific error for correction
    - Raise `ResponseParseError` on validation failure
    - Handle common LLM output issues: JSON wrapped in markdown code fences, trailing text after JSON
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

  - [ ]* 3.2 Write unit tests for ResponseParser
    - Create `src/backend/tests/unit/analysis/query/test_response_parser.py`
    - Test valid JSON parsing and Pydantic validation
    - Test document_id post-mapping to all source_refs
    - Test JSON extraction from markdown code fences
    - Test parse failure raises ResponseParseError
    - Test corrective re-prompt construction includes error details
    - Test evidence max 500 char enforcement
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

  - [ ]* 3.3 Write property test for Response Structural Completeness (Property 1)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 1: Response Structural Completeness**
    - Generate random valid QueryResponses with answerable=True, verify: non-empty answer (≤5000 chars), 1–10 source_refs, each source_ref has non-empty document_id, non-empty chunk_id, evidence ≤500 chars
    - **Validates: Requirements 1.1, 3.1, 3.2, 3.5, 5.1**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement QueryEvidenceVerifier
  - [ ] 5.1 Implement QueryEvidenceVerifier module
    - Create `src/backend/app/analysis/query/evidence_verifier.py`
    - Implement `QueryEvidenceVerifier` class with `__init__(self, fuzzy_threshold=0.8)`
    - Implement `verify(self, source_refs: list[QuerySourceRef], ir) -> list[QuerySourceRef]`
    - Reuse algorithm from existing `VerificationService` in `src/backend/app/analysis/verification.py`: (1) normalize whitespace, (2) exact substring match in referenced chunk_id, (3) exact substring match in any IR chunk, (4) fuzzy match at 80% threshold in any chunk
    - Set `evidence_verified = True/False` on each source_ref
    - Handle edge cases: empty evidence → mark as unverified without running algorithm; chunk_id not in IR → skip chunk step, proceed with full-IR matching
    - Deterministic — no LLM calls
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 5.2 Write unit tests for QueryEvidenceVerifier
    - Create `src/backend/tests/unit/analysis/query/test_evidence_verifier.py`
    - Test exact match in referenced chunk
    - Test exact match in different chunk
    - Test fuzzy match at/above/below 80% threshold
    - Test empty evidence text handling
    - Test missing chunk_id in IR
    - Test all_evidence_unverified flag computation
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7_

  - [ ]* 5.3 Write property test for Evidence Verification Determinism (Property 6)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 6: Evidence Verification Determinism**
    - Generate random source_refs and fixed IR, apply verification twice, verify identical results; verify all_evidence_unverified is True when all source_refs have evidence_verified=False
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.5**

- [ ] 6. Implement QueryService orchestrator
  - [ ] 6.1 Implement QueryService module
    - Create `src/backend/app/analysis/query/service.py`
    - Implement `QueryService` class with `__init__(self, llm_client, context_builder, response_parser, evidence_verifier)`
    - Implement `async answer(self, document_id, question, knowledge_model, ir) -> QueryResponse`
    - Pipeline: (1) build context, (2) check empty context → return cannot-answer response, (3) build prompt via `query_answering_v1.build()`, (4) call LLM (primary tier, temperature ≤ 0.1), (5) parse response (with one retry on failure via corrective re-prompt), (6) verify evidence, (7) compute all_evidence_unverified flag, (8) attach metadata (prompt_version, model_id, temperature, timestamp UTC)
    - Handle 30-second total timeout via asyncio.wait_for
    - Raise `QueryError` on LLM failure/timeout or parse failure after retry
    - Each query is independent — no state maintained between calls
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.3, 7.4, 7.5_

  - [ ]* 6.2 Write unit tests for QueryService
    - Create `src/backend/tests/unit/analysis/query/test_query_service.py`
    - Test successful pipeline end-to-end with mocked dependencies
    - Test cannot-answer response when context is empty (None)
    - Test retry flow: first parse fails, second succeeds
    - Test retry flow: both parses fail → raises QueryError
    - Test LLM timeout handling (>30s)
    - Test metadata attachment (prompt version, model_id, temperature, timestamp)
    - Test temperature ≤ 0.1 default
    - _Requirements: 1.1, 1.3, 1.5, 1.6, 7.3, 7.4_

  - [ ]* 6.3 Write property test for Query Statelessness (Property 7)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 7: Query Statelessness**
    - Generate sequences of queries to the same QueryService instance, verify each query's context and response is identical regardless of position in the sequence
    - **Validates: Requirements 1.6**

  - [ ]* 6.4 Write property test for Metadata Completeness (Property 10)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 10: Metadata Completeness**
    - Generate random QueryResponses (answerable and not), verify metadata always contains: non-empty prompt_version matching VERSION constant, non-empty model_id, temperature float, timestamp in ISO 8601 UTC
    - **Validates: Requirements 1.4, 7.3, 5.1**

  - [ ]* 6.5 Write property test for Controlled Temperature (Property 11)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 11: Controlled Temperature**
    - Verify LLM calls use temperature ≤ 0.1 by default; if overridden, actual temperature is recorded in metadata
    - **Validates: Requirements 7.4**

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement API endpoint
  - [ ] 8.1 Create query API endpoint
    - Create `src/backend/app/api/v1/query.py`
    - Implement `POST /api/v1/documents/{document_id}/query` endpoint
    - Request body: `QueryRequest` (question field validated by Pydantic)
    - Check document exists → 404 if not
    - Check analysis session status == "completed" → 409 with "km_not_completed" if not
    - Load Knowledge Model and IR from database
    - Instantiate and call `QueryService.answer()`
    - Return 200 with `QueryResponse` on success
    - Return 500 with `QueryErrorResponse` on `QueryError` (code: "query_failed" or "response_parse_error")
    - Apply 30-second timeout to query processing; return 500 on timeout
    - Do not expose internal stack traces in error responses
    - Register router in the application
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 1.7, 1.8_

  - [ ]* 8.2 Write property test for Knowledge Model Prerequisite Gate (Property 8)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 8: Knowledge Model Prerequisite Gate**
    - Generate documents with various analysis statuses (not "completed"), verify 409 returned without executing any pipeline (no LLM calls)
    - **Validates: Requirements 1.7, 5.2**

  - [ ]* 8.3 Write property test for Input Validation (Property 9)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 9: Input Validation**
    - Generate empty strings and strings >1000 chars, verify 422 returned without executing any pipeline
    - **Validates: Requirements 1.8, 5.4**

  - [ ]* 8.4 Write property test for Empty Context Cannot-Answer (Property 5)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 5: Empty Context Cannot-Answer**
    - Generate queries where context construction returns None (zero elements), verify response has answerable=False, non-empty answer explaining limitation, empty source_refs list
    - **Validates: Requirements 1.3, 2.7**

  - [ ]* 8.5 Write property test for Data Minimization (Property 4)
    - Add to `src/backend/tests/property/analysis/test_query_properties.py`
    - **Property 4: Data Minimization**
    - Generate random prompts via query_answering_v1.build(), verify no user identity, session history, account metadata, document_id, or unrelated information is present
    - **Validates: Requirements 2.6, 6.3, 7.2**

- [ ] 9. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement frontend query panel
  - [ ] 10.1 Create Zustand query store
    - Create query store file in `src/frontend/src/store/` (following existing store patterns)
    - State: messages array (question-answer pairs), isLoading, error
    - Actions: submitQuery (calls API), clearMessages (reset on navigation)
    - Session scoped to page lifecycle (cleared on unmount)
    - _Requirements: 8.6, 1.6_

  - [ ] 10.2 Create API client function for queries
    - Add query function to existing API client in `src/frontend/src/api/`
    - Function: `queryDocument(documentId: string, question: string): Promise<QueryResponse>`
    - Handle 30-second timeout on client side
    - Map error responses (404, 409, 422, 500) to typed error objects
    - _Requirements: 5.1, 8.2_

  - [ ] 10.3 Implement VerificationBadge component
    - Create `src/frontend/src/components/query/VerificationBadge.tsx`
    - Display verified/unverified status with distinct iconography and text labels (not color alone)
    - Meet WCAG 2.1 AA contrast ratio: 4.5:1 for text, 3:1 for graphical elements
    - Focusable via keyboard
    - _Requirements: 8.3, 8.7_

  - [ ] 10.4 Implement EvidenceReference component
    - Create `src/frontend/src/components/query/EvidenceReference.tsx`
    - Display evidence text span (truncated to 200 chars with expand option)
    - Show section/page reference when available
    - Include VerificationBadge for each source_ref
    - Clickable — navigates to KM element containing the evidence and highlights matching text
    - If target already visible, scroll to and highlight without full navigation
    - Keyboard focusable and activatable
    - _Requirements: 8.3, 8.4, 8.7_

  - [ ] 10.5 Implement QueryMessage component
    - Create `src/frontend/src/components/query/QueryMessage.tsx`
    - Display question-answer pair with visual distinction between user question and system answer
    - Render answer text
    - Render list of EvidenceReference components for source_refs
    - Display "cannot answer" messages with informational tone
    - Display error messages with apologetic tone (no technical details)
    - _Requirements: 8.3, 8.5_

  - [ ] 10.6 Implement QueryInput component
    - Create `src/frontend/src/components/query/QueryInput.tsx`
    - Text input field with character counter showing current/1000 max
    - Disable submit when input is empty or exceeds 1000 chars
    - Disable submit during loading (prevent duplicate submissions)
    - Keyboard navigable (Enter to submit)
    - _Requirements: 8.1, 8.7_

  - [ ] 10.7 Implement QueryPanel component and integrate
    - Create `src/frontend/src/components/query/QueryPanel.tsx`
    - Main container: scrollable list of QueryMessage components + QueryInput at bottom
    - Connect to Zustand store for state management
    - Show loading indicator while query is processing (ARIA live region announcement)
    - Display timeout message if no response within 30 seconds
    - Clear conversation on unmount (page navigation/refresh)
    - Only show panel when document has completed Knowledge Model
    - ARIA live regions for loading states announced to screen readers
    - Integrate QueryPanel into the document view (alongside existing KM visualization)
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7_

- [ ] 11. Integration tests
  - [ ]* 11.1 Write integration tests for query flow
    - Create `src/backend/tests/integration/analysis/test_query_flow.py`
    - Test full pipeline via httpx AsyncClient: document with completed KM → POST query → receive answer with verified evidence
    - Test 404 for non-existent document
    - Test 409 for document without completed KM
    - Test 422 for invalid question length
    - Test 500 for mocked LLM failure
    - Test cannot-answer scenario
    - All tests use mocked LLM responses
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 1.3_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All backend tests use mocked LLM responses to avoid real API calls during CI
- No new database tables or migrations needed (stateless feature)
- All LLM calls go through the existing `LLMClient` abstraction
- Frontend uses the existing stack: React 18 + TypeScript + Tailwind + shadcn/ui + Zustand

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.2", "3.3", "5.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "6.4", "6.5", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4", "8.5", "10.1", "10.2"] },
    { "id": 6, "tasks": ["10.3", "10.4"] },
    { "id": 7, "tasks": ["10.5", "10.6"] },
    { "id": 8, "tasks": ["10.7", "11.1"] }
  ]
}
```
