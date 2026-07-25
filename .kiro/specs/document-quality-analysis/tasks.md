# Implementation Plan: Document Quality Analysis

## Overview

This plan implements the quality analysis engine: the pipeline that consumes a completed Knowledge Model and evaluates document quality across three dimensions — contradictions/ambiguities, completeness gaps (per document type schema), and actionable improvement suggestions. Tasks are ordered by dependency — data models and schemas first, then database migration, then individual detectors (parallelizable), then pipeline orchestration, API layer, and finally testing.

The existing `AnalysisService`, `VerificationService`, `LLMClient`, and Knowledge Model infrastructure (Feature 3) are reused. This feature adds the quality analysis layer on top.

## Tasks

- [x] 1. Data models and schemas
  - [x] 1.1 Create quality analysis Pydantic models
    - Create `src/backend/app/models/quality_analysis.py` with Pydantic v2 models:
      - `FindingSourceRef` (document_id, chunk_id, page: int | None, section: str | None, evidence: str max 500 chars, evidence_verified: bool = False)
      - `Inconsistency` (id, type: Literal["contradiction", "ambiguity"], description: str max 500 chars, severity: Literal["high", "medium", "low"], affected_element_ids: list[str], source_refs: list[FindingSourceRef], involves_unverified_elements: bool = False, all_evidence_unverified: bool = False, from_explicit_relationship: bool = False)
      - `MissingElement` (id, classification: Literal["missing", "partial"], expected_element: str, description: str, severity: Literal["high", "medium", "low"], schema_reference: str)
      - `Suggestion` (id, description: str max 300 chars, category: Literal["structure", "clarity", "completeness", "consistency"], priority: Literal["high", "medium", "low"], related_finding_ids: list[str] = [], source_refs: list[FindingSourceRef] = [], all_evidence_unverified: bool = False)
      - `QualityAnalysisMetadata` (prompt_versions: dict[str, str], model_id: str, temperature: float, document_type: str, started_at: datetime, completed_at: datetime, finding_counts: dict[str, int])
      - `QualityAnalysisResult` (document_id: str, status: Literal["analyzing", "completed", "failed"], inconsistencies: list[Inconsistency] = [], missing_elements: list[MissingElement] = [], suggestions: list[Suggestion] = [], metadata: QualityAnalysisMetadata | None = None, error_message: str | None = None, error_phase: str | None = None)
    - Write unit tests in `tests/unit/analysis/quality/test_quality_models.py` verifying serialization, validation, field constraints (max lengths, literal values)
    - _Requirements: 1.2, 2.2, 3.1, 3.2, 4.2, 7.1, 7.3, 7.5_

  - [x] 1.2 Create document type schemas configuration
    - Create `src/backend/app/analysis/quality/schemas.py` with `DOCUMENT_TYPE_SCHEMAS` dict mapping document types to expected elements:
      - `prd`: propósito, usuarios/actores, requisitos funcionales, restricciones, criterios de éxito
      - `technical_spec`: propósito, alcance, componentes/conceptos, interfaces, restricciones, decisiones
      - `policy_process`: propósito, alcance, actores/roles, reglas, procesos, excepciones
    - Each entry includes: name, description, importance (high/medium/low)
    - Add `get_schema(document_type: str) -> list[dict] | None` helper that returns None for "generic" or unknown types
    - Write unit tests in `tests/unit/analysis/quality/test_schemas.py` verifying all three schemas are defined, generic returns None, schema structure is correct
    - _Requirements: 3.4, 10.4_

- [x] 2. Database migration
  - [x] 2.1 Create quality analysis migration
    - Create `src/backend/app/db/migrations/003_add_quality_analysis.sql`
    - Add columns to `analysis_sessions` table: `quality_analysis JSONB DEFAULT NULL`, `quality_status TEXT DEFAULT NULL`, `quality_error_message TEXT DEFAULT NULL`, `quality_started_at TIMESTAMPTZ DEFAULT NULL`, `quality_completed_at TIMESTAMPTZ DEFAULT NULL`
    - Add comments on columns documenting their purpose
    - quality_status values: NULL (not started), 'analyzing', 'completed', 'failed'
    - _Requirements: 6.1, 6.5_

- [x] 3. Prompt templates
  - [x] 3.1 Create contradiction detection prompt
    - Create `src/backend/app/analysis/prompts/contradiction_detection_v1.py`
    - Export `VERSION = "contradiction-v1"` constant
    - Implement `build(elements_json: str, relationships_json: str, ir_text: str) -> str` that constructs the prompt
    - Prompt instructs LLM to find contradictions between elements, output structured JSON conforming to the Inconsistency Pydantic model (type="contradiction")
    - Prompt includes severity criteria (high: mutually exclusive facts; medium: incompatible intent; low: minor wording tensions)
    - No user metadata or session info included — only KM elements, relationships, and IR text
    - Write unit tests in `tests/unit/analysis/quality/test_prompts.py` verifying: version accessible, prompt includes severity criteria, no user metadata slots, output schema instructions present
    - _Requirements: 1.1, 1.2, 1.4, 9.2, 10.1, 10.7, 10.8_

  - [x] 3.2 Create ambiguity detection prompt
    - Create `src/backend/app/analysis/prompts/ambiguity_detection_v1.py`
    - Export `VERSION = "ambiguity-v1"` constant
    - Implement `build(elements_json: str, ir_text: str) -> str` that constructs the prompt
    - Prompt instructs LLM to identify: undefined terms, vague quantifiers, unclear pronoun antecedents, unspecified conditions
    - Requires output JSON with at least 2 plausible interpretations per finding
    - Includes severity criteria (high: blocks comprehension; medium: creates uncertainty; low: stylistic imprecision)
    - No user metadata included
    - Write unit tests verifying: version accessible, four ambiguity categories mentioned, interpretation requirement present
    - _Requirements: 2.1, 2.2, 2.3, 9.2, 10.1, 10.7, 10.8_

  - [x] 3.3 Create completeness evaluation prompt
    - Create `src/backend/app/analysis/prompts/completeness_evaluation_v1.py`
    - Export `VERSION = "completeness-v1"` constant
    - Implement `build(elements_json: str, schema_json: str) -> str` that constructs the prompt
    - Prompt is used for partial coverage assessment: given an element that exists, determine if it adequately covers its schema definition or only partially addresses it
    - Output JSON conforming to a partial assessment response model
    - No user metadata included
    - Write unit tests verifying: version accessible, schema inclusion instruction present, partial assessment instructions clear
    - _Requirements: 3.1, 3.5, 9.2, 10.4, 10.7, 10.8_

  - [x] 3.4 Create suggestion generation prompt
    - Create `src/backend/app/analysis/prompts/suggestion_generation_v1.py`
    - Export `VERSION = "suggestion-v1"` constant
    - Implement `build(findings_json: str, elements_json: str, ir_text: str) -> str` that constructs the prompt
    - Prompt instructs LLM to generate actionable suggestions (concrete actions, not restatements of problems)
    - Includes category options (structure, clarity, completeness, consistency) and priority mapping to severity
    - Enforces max 300 character descriptions
    - Requires at least one source_ref per suggestion
    - No user metadata included
    - Write unit tests verifying: version accessible, actionability instruction present, max 300 char mentioned, categories listed
    - _Requirements: 4.1, 4.2, 4.3, 9.2, 10.1, 10.7, 10.8_

- [x] 4. Checkpoint - Verify foundation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Individual detectors and evaluators
  - [x] 5.1 Implement ContradictionDetector
    - Create `src/backend/app/analysis/quality/contradiction_detector.py`
    - Constructor receives `LLMClient`
    - Method `async detect(knowledge_model, ir) -> list[Inconsistency]`:
      - Step 1: Collect explicit `contradicts` relationships from KM — create confirmed Inconsistency findings with `from_explicit_relationship = True`, severity assigned per criteria, source_refs from both elements
      - Step 2: Build prompt with KM elements and relationships, call LLM (primary model, temperature 0.1)
      - Step 3: Parse LLM JSON response against Pydantic model; on parse failure, raise error
      - On LLM failure: return only structural contradictions (Req 1.6)
      - Set `involves_unverified_elements = True` when any affected element has `verified = False`
    - Write unit tests in `tests/unit/analysis/quality/test_contradiction_detector.py` covering: explicit relationships detected, LLM findings parsed, LLM failure returns only structural, empty KM returns empty, unverified elements flagged
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.2, 8.4, 8.5_

  - [x] 5.2 Implement AmbiguityDetector
    - Create `src/backend/app/analysis/quality/ambiguity_detector.py`
    - Constructor receives `LLMClient`
    - Method `async detect(knowledge_model, ir) -> list[Inconsistency]`:
      - Build prompt with KM elements and IR text chunks
      - Call LLM (primary model, temperature 0.1)
      - Parse response against Pydantic model; on parse failure, raise error
      - All findings have type="ambiguity", at least 1 source_ref, description with 2+ interpretations
      - Set `involves_unverified_elements` when applicable
    - On LLM failure: raise exception (no partial results for ambiguity — Req 2.5)
    - Write unit tests in `tests/unit/analysis/quality/test_ambiguity_detector.py` covering: successful detection, parse failure raises error, LLM failure propagates, empty results valid
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 8.2, 8.4_

  - [x] 5.3 Implement CompletenessEvaluator
    - Create `src/backend/app/analysis/quality/completeness_evaluator.py`
    - Constructor receives `LLMClient`
    - Method `async evaluate(knowledge_model, document_type) -> list[MissingElement]`:
      - If document_type is "generic": return empty list immediately (Req 3.3)
      - If KM has zero elements: raise error indicating completeness cannot be assessed (Req 3.6)
      - Load schema via `get_schema(document_type)`; if None, fail (Req 10.4)
      - Step 1 (deterministic): Match KM element types/names against schema expected elements — classify as present or missing
      - Step 2 (LLM): For present elements, use completeness evaluation prompt to assess partial coverage
      - Produce MissingElement findings for missing and partial elements with severity from schema importance
    - Write unit tests in `tests/unit/analysis/quality/test_completeness_evaluator.py` covering: generic type returns empty, missing elements detected, partial coverage via LLM, empty KM raises error, schema not found raises error
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.3, 10.4, 10.5_

  - [x] 5.4 Implement SuggestionGenerator
    - Create `src/backend/app/analysis/quality/suggestion_generator.py`
    - Constructor receives `LLMClient`
    - Method `async generate(inconsistencies, missing_elements, knowledge_model, ir) -> list[Suggestion]`:
      - Build prompt with all findings + KM context + IR text
      - Call LLM (primary model, temperature 0.1)
      - Parse response against Pydantic model
      - Post-processing: enforce max 20 suggestions (truncate lowest priority if exceeded — Req 4.6)
      - Validate: at least 1 suggestion per high-severity finding (Req 4.4); if missing, generate placeholder suggestions
      - Each suggestion must have at least 1 source_ref (Req 7.6)
      - If zero findings and LLM returns no structural improvements: return empty list (Req 4.5)
    - Write unit tests in `tests/unit/analysis/quality/test_suggestion_generator.py` covering: suggestions generated from findings, max 20 enforced, high-severity coverage, empty findings empty result, source_refs present
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.6_

  - [x] 5.5 Implement FindingVerifier
    - Create `src/backend/app/analysis/quality/finding_verifier.py`
    - Method `verify_all(inconsistencies, suggestions, ir) -> tuple[list[Inconsistency], list[Suggestion]]`:
      - Reuse the same verification algorithm from `VerificationService` (normalize whitespace, exact match in referenced chunk, exact match in any chunk, fuzzy match 80% threshold)
      - For each source_ref in each finding: set `evidence_verified = True/False`
      - For each finding: if all source_refs have `evidence_verified = False`, set `all_evidence_unverified = True`
      - MissingElement findings are NOT verified (no source_ref by definition — Req 7.4)
    - Write unit tests in `tests/unit/analysis/quality/test_finding_verifier.py` covering: exact match verified, fuzzy match verified, no match not verified, all_evidence_unverified flag set, empty source_refs handled
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6, 7.7_

- [x] 6. Pipeline orchestrator
  - [x] 6.1 Implement QualityAnalysisService
    - Create `src/backend/app/analysis/quality/service.py`
    - Constructor receives: ContradictionDetector, AmbiguityDetector, CompletenessEvaluator, SuggestionGenerator, FindingVerifier, AnalysisStorageService
    - Method `async run_analysis(document_id) -> QualityAnalysisResult`:
      - Prerequisite check: verify analysis session exists and status = "completed" (Req 8.1); else raise error
      - If quality_status = "analyzing": raise error (analysis already in progress)
      - Create/reset quality analysis record: set quality_status = "analyzing", quality_started_at = now(), clear previous results
      - Execute pipeline with 120-second timeout using `asyncio.wait_for()` + `asyncio.shield()` for cleanup (Req 6.7)
      - Pipeline steps with phase updates:
        1. Update phase → "analyzing_contradictions", run ContradictionDetector.detect()
        2. Update phase → "analyzing_ambiguities", run AmbiguityDetector.detect()
        3. Update phase → "analyzing_completeness", run CompletenessEvaluator.evaluate()
        4. Update phase → "generating_suggestions", run SuggestionGenerator.generate()
        5. Run FindingVerifier.verify_all()
        6. Mark elements with involves_unverified_elements where applicable (Req 8.4)
      - On success: persist results as JSONB, set quality_status = "completed", quality_completed_at = now()
      - On failure: preserve explicit-relationship contradictions only, clear all other partial results, set quality_status = "failed" with error message (Req 6.4)
      - Record metadata: prompt versions, model_id, temperature, timestamps, finding counts (Req 9.3)
    - Method `async get_results(document_id) -> QualityAnalysisResult | None`:
      - Retrieve persisted quality analysis results (idempotent, Req 5.8)
    - Create `src/backend/app/analysis/quality/__init__.py` exporting all quality modules
    - Write unit tests in `tests/unit/analysis/quality/test_quality_service.py` covering: full happy path, KM not completed rejects, timeout triggers failure, LLM failure preserves structural contradictions, re-trigger overwrites previous results, phase updates written to DB
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 8.1, 8.2, 8.3, 8.5, 8.6, 9.3, 9.4_

- [x] 7. API endpoint
  - [x] 7.1 Implement quality analysis API endpoints
    - Create `src/backend/app/api/v1/quality.py` with FastAPI router
    - `POST /api/v1/documents/{document_id}/quality-analysis`:
      - Validate document exists (404 if not)
      - Validate KM extraction completed (409 km_not_completed if not)
      - Validate no analysis in progress (409 analysis_in_progress if running)
      - Trigger pipeline (background task), return 202 with document_id + initial status
    - `GET /api/v1/documents/{document_id}/quality-analysis`:
      - Document not found → 404
      - KM not completed → 409 (km_not_completed)
      - Not triggered yet → 404 (not_found)
      - In progress → 202 with current phase status
      - Completed → 200 with full results including metadata (Req 5.1, 5.7, 5.8)
      - Failed → 500 with error details and phase (Req 5.6)
    - Register router in main.py under prefix `/api/v1/documents`
    - Add dependency injection for QualityAnalysisService
    - Error response format: `{"error": "code", "message": "..."}` consistent with existing patterns
    - Write unit tests for each endpoint covering all status code scenarios
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [x] 8. Checkpoint - Verify pipeline and API
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Integration and property-based tests
  - [x] 9.1 Write property-based tests for contradiction pass-through
    - Create `tests/property/analysis/test_quality_properties.py`
    - **Property 1: Explicit Contradictions Pass-Through** — For any generated KM with `contradicts` relationships, the output always includes one Inconsistency per relationship with `from_explicit_relationship = True`, regardless of LLM mock behavior
    - Use Hypothesis with custom strategies for KM generation
    - Minimum 100 iterations
    - **Validates: Requirements 1.1, 1.3, 1.6**

  - [x] 9.2 Write property-based tests for finding structure
    - **Property 2: Finding Structural Completeness** — For any Inconsistency of type "contradiction", verify at least 2 source_refs, at least 2 affected_element_ids, description ≤ 500 chars, valid severity. For type "ambiguity", verify at least 1 source_ref
    - Minimum 100 iterations
    - **Validates: Requirements 1.2, 2.2, 7.1, 7.2, 7.3**

  - [x] 9.3 Write property-based tests for generic type and suggestion bounds
    - **Property 3: Generic Type Completeness Skip** — For any document with type "generic", missing_elements is always empty while contradictions/ambiguities may be non-empty
    - **Property 4: Suggestion Count Bound** — For any quality analysis output, suggestions count ≤ 20
    - **Property 5: Suggestion Coverage** — For any result with N high-severity findings, suggestions count ≥ N (capped at 20)
    - Minimum 100 iterations each
    - **Validates: Requirements 3.3, 4.4, 4.6, 8.6**

  - [x] 9.4 Write property-based tests for failure state and evidence verification
    - **Property 6: Clean Failure State** — For any failed analysis, quality_analysis contains only explicit-relationship contradictions (if any), error_message is non-empty ≤ 1000 chars
    - **Property 7: Evidence Verification Determinism** — Running verify_all twice on the same inputs produces identical evidence_verified values; all_evidence_unverified is set correctly
    - **Property 8: KM Prerequisite Gate** — For any document without completed KM, run_analysis returns error without modifying quality records
    - Minimum 100 iterations each
    - **Validates: Requirements 6.2, 6.4, 7.5, 7.7, 8.1**

  - [x] 9.5 Write integration tests
    - Create `tests/integration/analysis/test_quality_flow.py`
    - End-to-end test: completed KM → POST trigger → poll status via GET → retrieve results → verify structure
    - Test error scenarios: document not found (404), KM not completed (409), analysis in progress (409), analysis failed (500)
    - Test idempotent retrieval: GET returns same results without re-triggering
    - Test re-trigger after completion: POST resets and re-runs
    - Test timeout behavior with slow mock
    - All tests use mocked LLM responses
    - _Requirements: 1–10 (all)_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All integration tests use mocked LLM responses to avoid real API calls during CI
- The existing `LLMClient`, `AnalysisStorageService`, and `VerificationService` from Feature 3 are reused — no new LLM abstractions needed
- The `FindingVerifier` reuses the verification algorithm from `VerificationService` but applies it to quality findings instead of KM elements
- Environment variables needed: same as Feature 3 (GEMINI_API_KEY, GROQ_API_KEY, PRIMARY_MODEL, etc.)
- Dependencies to add: `hypothesis` (dev dependency for property-based testing)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": 3, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 4, "tasks": ["6.1"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["9.1", "9.2", "9.3", "9.4", "9.5"] }
  ]
}
```
