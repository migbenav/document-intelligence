# Requirements Document

Knowledge Model Extraction (Analysis Engine)

## Introduction

This feature implements the analysis engine: the core intelligence of the system that consumes the Intermediate Representation (IR) produced by the ingestion layer and generates a structured Knowledge Model. The engine uses LLMs (abstracted via LiteLLM) to extract typed knowledge elements, identify relationships between them, infer the document type, and verify evidence references against the source document.

This is the first feature that introduces LLM interaction into the pipeline. It establishes the LLM abstraction layer, prompt versioning, and the Knowledge Model data structures that all subsequent features (quality analysis, natural language queries, visualization) depend on.

## Relevant Documentation

- #[[file:docs/product/04-product-mvp-specification.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-006-document-type-schemas.md]]
- #[[file:docs/architecture/001-technology-stack.md]]
- #[[file:.kiro/specs/document-ingestion/design.md]]

## Feature Boundaries

**In scope:**
- LLM abstraction layer (LiteLLM wrapper with provider switching, fallbacks, rate limiting).
- Prompt template system with versioning.
- Document type inference (automatic suggestion).
- Document type confirmation API (user accepts/changes type).
- Knowledge Model extraction (elements with source_ref).
- Relationship extraction (optional, confidence-gated).
- Evidence verification (verify source_ref against IR text).
- Knowledge Model Pydantic models.
- Analysis session management (persist results).
- API endpoints: initiate analysis, get knowledge model, confirm document type.
- Database migration for analysis results (knowledge_elements, analysis_sessions).

**Out of scope (belongs to subsequent features):**
- Quality analysis (inconsistencies, missing elements, suggestions) — Feature 5.
- Knowledge Model visualization UI — Feature 4.
- Natural language queries — Feature 6.
- User feedback on elements — Feature 7.
- Frontend document type confirmation UI (this feature provides the API; Feature 2 or a dedicated frontend task provides the UI).

## Glossary

| Term | Definition |
|------|------------|
| Knowledge Model | A structured representation of the knowledge contained in a document, composed of typed elements with optional relationships. |
| Knowledge Element | A single unit of structured knowledge extracted from the document (e.g., a concept, actor, rule). |
| Taxonomy | The fixed set of element types: propósito, conceptos, actores, reglas, procesos, restricciones. |
| source_ref | A flexible evidence reference that traces a knowledge element back to the original document (includes document_id, page, section, chunk_id, evidence text span). |
| Document Type | One of: PRD, Technical Spec, Policy/Process, Generic — determines which schema is used for completeness evaluation. |
| LLM Abstraction Layer | A single point of communication with LLM providers via LiteLLM, enabling provider switching without modifying the pipeline. |
| Evidence Verification | The process of confirming that a source_ref's evidence text span actually exists in the source document's IR. |
| Analysis Session | A record tracking the state and results of a document analysis (pending → analyzing → completed / failed). |
| IR (Intermediate Representation) | The format-agnostic structured document produced by the ingestion layer, consumed as input by this feature. |

---

## Requirements

### Requirement 1: LLM Abstraction Layer

**User Story:** As a developer, I need a single point of communication with LLM providers so that the system can switch providers or models without modifying the analysis pipeline.

#### Acceptance Criteria

1. Given the analysis engine needs to call an LLM, when it makes a request, then the request goes through a centralized LLM abstraction layer that wraps LiteLLM — no direct SDK calls to any provider exist outside this layer.
2. Given the LLM abstraction layer, when it is configured, then it supports at minimum two model configurations: a primary extraction model (Gemini 2.5 Flash) and a secondary/fallback model (Groq Llama 3.3 70B).
3. Given the primary model is rate-limited or unavailable, when a request fails due to a transient error (rate limit, timeout, service unavailable), then the abstraction layer automatically falls back to the configured fallback model without the caller needing to handle retry logic. When the failure is due to invalid API credentials for both models, then the layer raises an authentication error immediately without attempting fallback.
4. Given the abstraction layer, when any LLM call is made, then it uses controlled generation parameters (temperature ≤ 0.1 by default) to maximize reproducibility per ADR-004.
5. Given the abstraction layer, when a call is made, then it logs the model version used and the prompt version so that results can be traced to a specific configuration (reproducibility tracking).
6. Given the system configuration, when environment variables for LLM API keys are missing or invalid, then the abstraction layer raises a clear error at startup (not at first call) indicating which credentials are missing.
7. Given the automatic fallback has also failed, when the caller receives the final error, then the caller may implement its own retry logic as a secondary mechanism — the abstraction layer does not prevent caller-level retries.

**Traceability:**
- RF-15: Provider abstraction layer requirement.
- ADR-005: Only text + prompts sent; provider replaceable.
- Tech Stack D-05: LiteLLM for abstraction.
- Tech Stack D-06: Gemini 2.5 Flash (primary) + Groq (secondary).
- ADR-004: Controlled parameters, model version tracking, prompt versioning.

---

### Requirement 2: Prompt Template System

**User Story:** As a developer, I need versioned, structured prompt templates so that the system's analysis behavior is reproducible, auditable, and improvable over time.

#### Acceptance Criteria

1. Given the analysis engine, when it constructs a prompt for the LLM, then it uses a prompt template loaded from a dedicated templates directory (not inline strings in source code).
2. Given a prompt template, when it is used, then it includes a version identifier that is recorded alongside the analysis results for reproducibility.
3. Given the extraction prompt, when it instructs the LLM, then it explicitly requests the fixed taxonomy of element types (propósito, conceptos, actores, reglas, procesos, restricciones) and the relationship vocabulary (constrains, participates_in, depends_on, contradicts).
4. Given any prompt template, when it includes the document content, then it includes only the IR text and structural context — no user metadata, account information, or usage history is included (ADR-005 minimization principle). Document metadata embedded in the IR text itself (such as author names or creation dates that appear in the document content) is permitted to remain as-is.
5. Given a prompt for extraction, when it instructs the LLM, then it requires each extracted element to include an `evidence` field containing a verbatim text span from the source document.
6. Given the prompt templates, when a new prompt version is created, then previous versions remain available for comparison and rollback.

**Traceability:**
- ADR-004: Prompts versionados e inmutables por release.
- ADR-005: Only text + prompts sent; minimization principle.
- RF-03: Taxonomy of element types.
- RF-03.1: source_ref with evidence text span.
- RF-04: Relationship vocabulary.

---

### Requirement 3: Document Type Inference

**User Story:** As a user, I want the system to automatically suggest the type of my document so that I don't need to know the internal taxonomy to benefit from type-specific analysis.

#### Acceptance Criteria

1. Given an ingested document (status = ready), when analysis is initiated, then the system infers the document type (PRD, Technical Spec, Policy/Process, or Generic) based on the document content before proceeding with extraction.
2. Given the inference step, when the system identifies a type, then it returns the suggested type along with a brief justification (one sentence explaining why this type was selected), regardless of the current analysis stage — the suggestion and justification are always available once inference completes.
3. Given the system cannot classify the document with sufficient confidence, when the inference completes, then it leaves the document type unset (defaults to no specific type) and suggests "Generic" as the recommendation to the user.
4. Given the inference result, when it is returned to the caller, then the analysis does not proceed to full extraction until the type is confirmed (the system waits for explicit confirmation via the confirm-type endpoint).
5. Given the type inference, when the LLM is called for classification, then it uses the secondary/light model (Groq) rather than the primary extraction model to minimize latency and cost for this simpler task.

**Traceability:**
- ADR-006: Hybrid selection (inference + user confirmation).
- RF-06: Document types for completeness evaluation.
- US-005.1: User confirms or corrects the suggested document type.
- CA-03.2: System infers type and presents suggestion for confirmation.

---

### Requirement 4: Document Type Confirmation

**User Story:** As a user, I want to confirm or change the suggested document type so that the analysis evaluates my document against the correct schema.

#### Acceptance Criteria

1. Given a document with an inferred type (analysis status = awaiting_confirmation), when the user calls the confirm-type endpoint with the accepted type, then the system records the confirmed type and proceeds with Knowledge Model extraction.
2. Given the confirm-type endpoint, when the user provides a type different from the suggestion (e.g., changes from "PRD" to "Technical Spec"), then the system uses the user-provided type for all subsequent analysis.
3. Given the confirm-type endpoint, when the user provides "Generic" as the type, then the system proceeds with full Knowledge Model extraction but without schema-based completeness evaluation in future quality analysis. The analysis status continues to be determined by the extraction and verification pipeline (not automatically marked as complete).
4. Given a document that has already been confirmed and analyzed, when the confirm-type endpoint is called again, then the system rejects the request with an appropriate error (type cannot be changed after analysis is complete).
5. Given the confirm-type endpoint, when an invalid type value is provided, then the system returns a 400 error listing the valid types.

**Traceability:**
- ADR-006: User can accept suggestion, change type, or select Generic.
- US-005.1: User confirms or corrects the suggested type.
- RF-06: Types determine completeness schema.

---

### Requirement 5: Knowledge Model Extraction

**User Story:** As a user, I want the system to generate a structured Knowledge Model from my document so that I can understand its content as organized knowledge elements rather than raw text.

#### Acceptance Criteria

1. Given a document with a confirmed type, when extraction begins, then the system sends the IR text content to the primary LLM with the extraction prompt and produces a Knowledge Model containing typed elements.
2. Given the extraction result, when the Knowledge Model is generated, then each element has: a unique id, a type from the fixed taxonomy (propósito, conceptos, actores, reglas, procesos, restricciones), a name, a description/content, and a source_ref.
3. Given the extraction result, when the Knowledge Model is generated, then it contains at minimum a "propósito" element (every document has a purpose, even if inferred).
4. Given the source_ref of each element, when it is populated, then it includes: document_id, chunk_id (referencing the IR chunk), and an evidence field containing a verbatim text span from the source document.
5. Given the source_ref, when the document is a PDF, then it additionally includes the page number. When the document is Markdown, it additionally includes the section heading.
6. Given the extraction prompt, when the LLM response cannot be parsed against the Knowledge Model Pydantic schema at all (complete parse failure), then extraction is halted and the analysis session is marked as failed. When individual elements within a parseable response are malformed, then those specific elements are discarded with a warning while valid elements are retained.
7. Given a document longer than the model's practical context window, when extraction is performed, then the system processes the document in manageable segments and merges the results into a single coherent Knowledge Model (deduplicating elements that appear across segments).

**Traceability:**
- RF-02: System must analyze content and generate Knowledge Model.
- RF-03: Knowledge Model with typed elements from fixed taxonomy.
- RF-03.1: source_ref with document_id, page, section, chunk_id, evidence.
- CA-01: System generates Knowledge Model with verifiable source_ref.
- ADR-002: Hybrid model with typed elements.

---

### Requirement 6: Relationship Extraction

**User Story:** As a user, I want the Knowledge Model to include relationships between elements so that I can understand how concepts, actors, rules, and processes are connected within my document.

#### Acceptance Criteria

1. Given the Knowledge Model extraction, when relationships are identified between elements, then they are included as optional relations using the fixed vocabulary: constrains, participates_in, depends_on, contradicts.
2. Given a relationship, when it is extracted, then it references the source element id, target element id, the relationship type, and optionally a brief description of the relationship.
3. Given the extraction process, when the LLM identifies relationships, then only relationships with sufficient confidence are included — the system does not force relationship extraction for all elements.
4. Given the relationship vocabulary, when a "contradicts" relationship is identified, then it is treated as bidirectional (both elements reference each other). All other relationship types are directed (source → target).
5. Given the Knowledge Model, when relationships reference element IDs, then all referenced IDs exist within the same Knowledge Model — no dangling references are persisted.

**Traceability:**
- RF-04: Optional relationships with fixed vocabulary.
- ADR-002: Relations optional, captured when confident.
- ADR-006: 4 relationship types with semantic and directional definitions.

---

### Requirement 7: Evidence Verification

**User Story:** As a user, I want each knowledge element's evidence to be verified against the original document so that I can trust that the system's claims are grounded in the actual text.

#### Acceptance Criteria

1. Given a Knowledge Model with extracted elements, when the evidence verification step runs, then it checks each element's source_ref.evidence text against the IR chunks to confirm the text span exists in the document.
2. Given the verification check, when the evidence text span is found (exact or near-exact match allowing minor whitespace/formatting differences) in the referenced chunk, then the element is marked as verified (verified = true).
3. Given the verification check, when the evidence text span cannot be found in the referenced chunk or anywhere in the IR, then the element is marked as not verified (verified = false) — the element is still included in the Knowledge Model but flagged.
4. Given the verification process, when it completes, then it reports the verification rate (percentage of elements verified) as part of the analysis session metadata.
5. Given the verification step, when it runs, then it does NOT call the LLM — verification is a deterministic text-matching operation against the IR.

**Traceability:**
- RF-03.2: System verifies evidence exists in original document; unverified elements are marked.
- ADR-004: Trust by Evidence — verification of references as must-have.
- CA-01: Knowledge Model with verifiable source_ref.

---

### Requirement 8: Analysis Session Management

**User Story:** As a system, I need to track the state of each analysis so that the user can monitor progress and retrieve results.

#### Acceptance Criteria

1. Given a document ready for analysis, when analysis is initiated, then an analysis session is created with a unique session_id, associated document_id, status "inferring_type", and timestamps.
2. Given an analysis session, when its status changes, then it transitions through the following states: inferring_type → awaiting_confirmation → extracting → verifying → completed (or failed at any step).
3. Given a completed analysis session, when its results are stored, then it persists: the confirmed document type, the full Knowledge Model (elements + relationships), verification results, prompt versions used, model versions used, and extraction metadata (element count, relationship count, verification rate).
4. Given an analysis that fails at any step, when the failure occurs, then the session status is set to "failed" with a descriptive error_message, and any partial results that were persisted during normal processing are cleaned up (discarded) to ensure no incomplete Knowledge Models are retrievable.
5. Given an analysis session, when results are stored, then the Knowledge Model is persisted as JSONB in the analysis_sessions table (aligned with Supabase PostgreSQL capabilities).

**Traceability:**
- RF-08: System stores Knowledge Model and analysis results temporarily.
- MVP Roadmap Feature 3: "API endpoints para iniciar análisis y obtener resultados."

---

### Requirement 9: Analysis API Endpoints

**User Story:** As a frontend client, I need API endpoints to initiate analysis, confirm the document type, and retrieve the Knowledge Model so that I can build the analysis workflow UI.

#### Acceptance Criteria

1. Given a document with status "ready" (ingestion complete), when `POST /api/v1/documents/{document_id}/analyze` is called, then the system initiates type inference and returns 202 with the session_id and status "inferring_type". When the document is not in "ready" status, then the system rejects the request with 409 (conflict — not ready for analysis).
2. Given a document that does not exist, when the analyze endpoint is called, then the system returns 404 (not found).
3. Given an analysis session in "awaiting_confirmation" status, when `POST /api/v1/documents/{document_id}/confirm-type` is called with `{"document_type": "prd"}`, then the system records the confirmed type and begins extraction, returning 202 with updated status.
4. Given a completed analysis session, when `GET /api/v1/documents/{document_id}/knowledge-model` is called, then the system returns 200 with the full Knowledge Model (elements, relationships, verification metadata).
5. Given an analysis session in any non-completed state, when the knowledge-model endpoint is called, then the system returns 409 (conflict) indicating analysis is not yet complete.
6. Given any analysis endpoint, when the document_id does not exist, then the system returns 404 with a descriptive error.
7. Given the analyze endpoint, when the document already has a completed or in-progress analysis, then the system returns 409 (conflict) indicating analysis already exists.

**Traceability:**
- MVP Roadmap Feature 3: "API: POST /analyze, GET /{id}/knowledge-model, POST /{id}/confirm-type."
- Document Ingestion Design: API patterns (202 for async operations, 404/409 for state conflicts).

---

### Requirement 10: Reproducibility and Minimization

**User Story:** As a user, I want the analysis to produce consistent results when run on the same document, and I want to be confident that only the minimum necessary information is sent to the AI service.

#### Acceptance Criteria

1. Given the same document, same model configuration, and same prompt version, when analysis is run twice, then the resulting Knowledge Models are structurally consistent — the same principal knowledge is extracted (equivalent elements with matching types, names, and semantic content; equivalent relationships; equivalent evidence references). Structural consistency means the extracted knowledge is semantically equivalent, not that the serialized JSON output is byte-for-byte identical (field ordering, whitespace, phrasing variations in descriptions are acceptable differences). The system reduces LLM non-determinism through deterministic prompts, low temperature parameters, schema-constrained generation, output validation against the Pydantic schema, and normalization of extracted content where appropriate. Implementation techniques such as result caching or fixed random seeds may be employed to further improve consistency but are not architectural requirements.
2. Given the analysis pipeline, when it sends data to the LLM, then it sends only: the document text content (from IR chunks), structural context (section headings or page numbers), and the system prompt. No user identity, session history, or metadata beyond the document is included.
3. Given a completed analysis session, when its metadata is reviewed, then it records: the prompt version used, the model identifier used, and the generation parameters (temperature, etc.) — enabling auditability.
4. Given the analysis results, when they are persisted, then no user metadata, account information, or usage history is stored alongside the Knowledge Model.

**Traceability:**
- ADR-004: Bounded reproducibility — structural consistency, not textual identity.
- ADR-005: Minimization principle — only text + prompts sent.
- RF-13: Only minimum necessary information sent to AI.
- RF-15: Provider abstraction for reproducibility tracking.
