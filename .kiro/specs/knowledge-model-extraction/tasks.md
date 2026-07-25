# Implementation Plan: Knowledge Model Extraction (Analysis Engine)

## Overview

This plan implements the analysis engine: LLM abstraction, prompt templates, document type inference, Knowledge Model extraction, evidence verification, and API endpoints. Tasks are ordered by dependency — foundational infrastructure first, then core logic, then orchestration and API layer, and finally integration verification.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": [1, 2],
      "description": "Knowledge Model Pydantic models and database migration"
    },
    {
      "wave": 2,
      "tasks": [3],
      "description": "LLM abstraction layer (LiteLLM wrapper)"
    },
    {
      "wave": 3,
      "tasks": [4, 5],
      "description": "Prompt templates (type inference + extraction)"
    },
    {
      "wave": 4,
      "tasks": [6, 7],
      "description": "Type inference service and evidence verification"
    },
    {
      "wave": 5,
      "tasks": [8],
      "description": "Extraction service"
    },
    {
      "wave": 6,
      "tasks": [9],
      "description": "Analysis service (pipeline orchestrator)"
    },
    {
      "wave": 7,
      "tasks": [10],
      "description": "API endpoints"
    },
    {
      "wave": 8,
      "tasks": [11],
      "description": "Integration tests"
    }
  ]
}
```

## Tasks

- [x] 1. Knowledge Model Pydantic models
  Create `src/backend/app/models/knowledge_model.py` with Pydantic v2 models: `SourceRef` (document_id, chunk_id, page: int | None, section: str | None, evidence: str), `Relation` (target_id, type as Literal["constrains", "participates_in", "depends_on", "contradicts"], description: str | None), `KnowledgeElement` (id, type as Literal["proposito", "concepto", "actor", "regla", "proceso", "restriccion"], name, content, source_ref: SourceRef, relations: list[Relation], verified: bool = False), `ExtractionMetadata` (prompt_version, model_id, temperature, element_count, relationship_count, verification_rate, extracted_at: datetime), `KnowledgeModel` (document_id, document_type, elements: list[KnowledgeElement], extraction_metadata), `AnalysisSession` response model (id, document_id, status, suggested_type: str | None, suggested_type_justification: str | None, confirmed_type: str | None, error_message: str | None, created_at, updated_at), `TypeSuggestion` (document_type: str | None — None when confidence is low, suggested_type: str — always populated with recommendation, justification: str). Write unit tests in `tests/unit/analysis/test_models.py` to verify serialization, validation, and that TypeSuggestion supports the unset document_type case.
  **Requirements: 3.3, 5, 6, 8**

- [x] 2. Database migration for analysis sessions
  Create `src/backend/app/db/migrations/002_create_analysis_sessions.sql` with the `analysis_sessions` table: id UUID PK, document_id UUID FK UNIQUE REFERENCES documents(document_id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'inferring_type' (inferring_type | awaiting_confirmation | extracting | verifying | completed | failed), suggested_type TEXT, suggested_type_justification TEXT, confirmed_type TEXT, knowledge_model JSONB, extraction_metadata JSONB, error_message TEXT, prompt_version TEXT, model_id TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(). The UNIQUE constraint on document_id enforces one analysis per document (Req 9.7).
  **Requirements: 8.1, 8.2, 8.5**

- [x] 3. LLM abstraction layer
  Implement `src/backend/app/analysis/llm_client.py` with `LLMClient` class wrapping LiteLLM. Constructor reads model config from environment variables (GEMINI_API_KEY, GROQ_API_KEY, PRIMARY_MODEL, LIGHT_MODEL, FALLBACK_MODEL with defaults). Validate API keys at instantiation — raise a clear `ConfigurationError` if any required key is missing (Req 1.6). Method `async call(prompt, *, model_tier="primary", temperature=0.1) -> str` routes to the correct model, uses LiteLLM `acompletion` with controlled temperature (Req 1.4). Fallback logic: on transient errors (rate limit, timeout, service unavailable) auto-fallback to secondary model; on authentication/credential errors, raise immediately without fallback attempt (Req 1.3). Log model_id actually used and prompt version for reproducibility tracking (Req 1.5). The layer must not suppress errors in a way that prevents caller-level retries after both primary and fallback fail (Req 1.7). Write unit tests with mocked LiteLLM in `tests/unit/analysis/test_llm_client.py` covering: successful call, transient error triggers fallback, credential error skips fallback, missing env vars raise at init, model_id tracking reflects actual model used.
  **Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7**

- [x] 4. Prompt template: type inference
  Create `src/backend/app/analysis/prompts/type_inference_v1.py` with a versioned prompt template for document type classification. Export `VERSION = "type-inference-v1"` constant (Req 2.2). The `build(ir_text_sample: str) -> str` function constructs the prompt: receives the first ~2000 chars of the IR text, instructs the LLM to classify as one of (prd, technical_spec, policy_process, generic), and return JSON with `{"document_type": "...", "justification": "..."}`. The prompt must not include any user metadata or session info — only document text and structural context (Req 2.4). Write unit tests in `tests/unit/analysis/test_prompts.py` verifying: prompt includes only document text, version identifier is accessible, all valid types are mentioned in prompt instructions.
  **Requirements: 2.1, 2.2, 2.4, 3.1**

- [x] 5. Prompt template: extraction
  Create `src/backend/app/analysis/prompts/extraction_v1.py` with a versioned prompt template for Knowledge Model extraction. Export `VERSION = "extraction-v1"` constant (Req 2.2). The `build(ir_text: str, document_type: str, structural_contexts: list[dict]) -> str` function constructs the prompt: receives the full IR text + confirmed document type + structural context, instructs the LLM to extract elements using the fixed taxonomy (proposito, concepto, actor, regla, proceso, restriccion — Req 2.3), include source_ref with evidence text spans for each element (Req 2.5), and identify relationships using the vocabulary (constrains, participates_in, depends_on, contradicts — Req 2.3). Output format: JSON matching the KnowledgeModel Pydantic schema. The prompt must require a verbatim evidence field per element. No user metadata or session info included (Req 2.4). Prompt uses deterministic, schema-constrained instructions to reduce LLM non-determinism (Req 10.1). Write unit tests verifying: taxonomy and relationship vocabulary appear in prompt, evidence instruction present, no user metadata slots, version accessible.
  **Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 6.1, 10.1**

- [x] 6. Type inference service
  Implement `src/backend/app/analysis/type_inference.py` with `TypeInferenceService` class. Method `async infer(ir: IntermediateRepresentation) -> TypeSuggestion` constructs the type inference prompt using the first ~2000 chars of combined IR chunk text, calls the LLM via `LLMClient` with model_tier="light" (Req 3.5), parses the JSON response. When the LLM response indicates a type with sufficient confidence, populate `TypeSuggestion.document_type` with the detected type and `suggested_type` with the same value. When confidence is low or the response is unparseable, set `TypeSuggestion.document_type = None` and `suggested_type = "generic"` (Req 3.3). Always populate `justification`. The suggestion and justification remain available regardless of subsequent analysis stages (Req 3.2). Write unit tests with mocked LLMClient in `tests/unit/analysis/test_type_inference.py` covering: successful classification, low confidence defaults to generic suggestion with None type, unparseable response defaults gracefully.
  **Requirements: 3.1, 3.2, 3.3, 3.5**

- [x] 7. Evidence verification service
  Implement `src/backend/app/analysis/verification.py` with `VerificationService` class. Method `verify(knowledge_model: KnowledgeModel, ir: IntermediateRepresentation) -> VerificationResult` iterates over each element's source_ref.evidence, normalizes whitespace, and checks existence: (1) exact substring match in the referenced chunk_id, (2) exact match in any IR chunk, (3) fuzzy match (80% similarity threshold) in any chunk. Sets `element.verified = True` if found, `False` if not found anywhere (Req 7.2, 7.3). Does NOT call the LLM — purely deterministic (Req 7.5). Returns `VerificationResult` with verified_count, total_count, verification_rate (percentage), and unverified_element_ids (Req 7.4). Write unit tests in `tests/unit/analysis/test_verification.py` covering: exact match in referenced chunk, exact match in different chunk, fuzzy match, no match, whitespace normalization, verification rate calculation.
  **Requirements: 7.1, 7.2, 7.3, 7.4, 7.5**

- [x] 8. Extraction service
  Implement `src/backend/app/analysis/extraction.py` with `ExtractionService` class. Method `async extract(ir: IntermediateRepresentation, document_type: str) -> KnowledgeModel` constructs the extraction prompt with full IR text and document type, calls the LLM via `LLMClient` with model_tier="primary" (Req 5.1). Parses the JSON response: if the response cannot be parsed at all (complete parse failure), raise an `ExtractionError` that signals the pipeline to halt and mark the session as failed (Req 5.6). If the response is parseable but individual elements are malformed, discard those elements with warnings and retain valid ones (Req 5.6). Post-processing: ensure all relationship target_ids reference existing element IDs — remove dangling references (Req 6.5). For "contradicts" relationships, ensure bidirectionality — if element A contradicts B, B must also reference A (Req 6.4). Validate that at minimum a "proposito" element exists — if missing, log a warning (Req 5.3). For source_ref: populate page for PDF documents, section for Markdown (Req 5.5). Generate `ExtractionMetadata` with prompt_version, model_id, temperature, counts. Handle documents exceeding context limits by segmentation at chunk boundaries with deduplication by element name + type (Req 5.7). Apply output normalization (trim whitespace, consistent casing for types) to reduce non-determinism (Req 10.1). Write unit tests with mocked LLMClient in `tests/unit/analysis/test_extraction.py` covering: successful extraction, complete parse failure raises error, partial malformed elements discarded, dangling references removed, contradicts made bidirectional, proposito validation, segmentation merging.
  **Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 10.1**

- [x] 9. Analysis service (pipeline orchestrator)
  Implement `src/backend/app/analysis/service.py` with `AnalysisService` class. Constructor receives LLMClient, TypeInferenceService, ExtractionService, VerificationService, and a Supabase client for persistence. Method `async start_analysis(document_id) -> AnalysisSession`: verify document exists and is in "ready" status (else raise appropriate error), verify no analysis session exists for this document (Req 9.7), create session with status "inferring_type" (Req 8.1), retrieve IR from storage, call TypeInferenceService.infer(ir), update session with suggested_type + justification, set status to "awaiting_confirmation" (Req 8.2). Method `async confirm_and_extract(document_id, document_type) -> AnalysisSession`: validate session is in "awaiting_confirmation" state (Req 4.4), validate document_type is one of valid values (Req 4.5), record confirmed_type (Req 4.1), update status to "extracting", call ExtractionService.extract(ir, document_type), update status to "verifying", call VerificationService.verify(km, ir), persist completed KM + metadata (Req 8.3), update status to "completed". Failure handling: on any error, set status to "failed" with descriptive error_message, and clean up any partial knowledge_model data already persisted (set knowledge_model field to NULL) to ensure no incomplete KM is retrievable (Req 8.4). Ensure data minimization: no user metadata stored alongside results (Req 10.4). Write unit tests with mocked dependencies in `tests/unit/analysis/test_service.py` covering: full happy path, document not found, document not ready, analysis already exists, wrong session state for confirm, invalid type, extraction failure cleanup, type inference failure cleanup.
  **Requirements: 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.7, 10.2, 10.4**

- [x] 10. API endpoints
  Implement FastAPI router in `src/backend/app/api/v1/analysis.py`: `POST /{document_id}/analyze` — returns 202 with session + suggested type on success; returns 404 when document does not exist (Req 9.2); returns 409 when document is not in "ready" status (Req 9.1) or when analysis already exists (Req 9.7). `POST /{document_id}/confirm-type` — accepts `{"document_type": "..."}`, validates against allowed values (prd, technical_spec, policy_process, generic), returns 400 with list of valid types on invalid value (Req 4.5); returns 202 on success; returns 404 if not found; returns 409 if session is not in "awaiting_confirmation" or is already completed (Req 4.4). `GET /{document_id}/knowledge-model` — returns 200 with full KM including elements, relationships, and extraction_metadata (Req 9.4); returns 404 if not found (Req 9.6); returns 409 if analysis not yet completed (Req 9.5). Register router in `main.py` under prefix `/api/v1/documents`. Add dependency injection for AnalysisService. Error response format: `{"error": "code", "message": "..."}` consistent with ingestion API patterns. Write unit tests for each endpoint covering all status code scenarios.
  **Requirements: 4.4, 4.5, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7**

- [x] 11. Integration tests
  Write end-to-end tests in `tests/integration/analysis/test_analysis_flow.py` using httpx AsyncClient with mocked LLM responses: upload document → initiate analysis → verify type suggestion returned with justification → confirm type → wait for completion → retrieve Knowledge Model → verify structure (elements with source_ref containing evidence, relationships with valid target_ids, contradicts relations are bidirectional, verification metadata with rate, ExtractionMetadata with prompt_version and model_id). Test error scenarios: document not found (404), document not ready (409), analysis already exists (409), invalid type (400 with valid types list), confirm on wrong state (409), get KM before completion (409). Test that evidence verification correctly marks verified/unverified elements. Test that complete parse failure results in failed session with cleanup. Test low-confidence type inference returns None document_type with generic suggestion.
  **Requirements: 1-10 (all)**

## Notes

- All tasks include unit tests alongside implementation.
- The LLM client (Task 3) is the foundation — all services depend on it.
- Tasks 6 and 7 can be parallelized (type inference and verification are independent).
- Integration tests (Task 11) require mocking LLM responses to avoid real API calls during CI.
- Environment variables needed: GEMINI_API_KEY, GROQ_API_KEY (optional: PRIMARY_MODEL, LIGHT_MODEL, FALLBACK_MODEL overrides).
- The extraction service (Task 8) is the most complex task and may need iteration on prompt engineering.
- Req 10.1 (structural consistency) is addressed through implementation practices across tasks 3, 5, 8: deterministic prompts, low temperature, schema-constrained generation, output validation, and normalization — not through a single dedicated task.
