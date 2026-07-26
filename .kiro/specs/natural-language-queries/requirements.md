# Requirements Document

Natural Language Queries

## Introduction

This feature implements the natural language query engine: a service that allows users to ask questions about their document in natural language and receive answers grounded in the Knowledge Model. Each answer includes traceable evidence (`source_ref`) linking back to the original document, maintaining the Trust by Evidence model (ADR-004).

The query engine operates on the completed Knowledge Model (produced by Feature 3) as its primary context source. It constructs prompts that include relevant Knowledge Model elements and relationships, sends them to the LLM, and parses responses to extract structured answers with source references. The system enriches answers with relational context from the Knowledge Model (RF-04: "Consultas por lenguaje natural: enriquecer respuestas con contexto relacional").

This feature completes the interactive capability of the MVP (PRD C5: Asistencia mediante IA), enabling users to explore and interrogate their document's knowledge through conversation rather than only passive visualization.

## Relevant Documentation

- #[[file:docs/product/04-product-mvp-specification.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/architecture/mvp-roadmap.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/requirements.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/design.md]]
- #[[file:src/backend/app/models/knowledge_model.py]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/backend/app/analysis/verification.py]]

## Feature Boundaries

**In scope:**
- Query service that receives a natural language question and returns a structured answer with source references.
- Context construction from the Knowledge Model (selecting relevant elements and relationships as LLM context).
- Prompt template for query answering, versioned following existing patterns.
- Response parsing: extracting the answer text plus `source_ref` evidence references.
- Evidence verification of response source_refs against the original document/IR.
- Query API endpoint: POST /{id}/query.
- Query response Pydantic models (QueryRequest, QueryResponse, QuerySourceRef).
- Integration with existing LLM abstraction layer (LiteLLM wrapper).
- Relational context enrichment (including related elements in the context sent to the LLM).
- Reproducibility principles (controlled parameters, prompt versioning, metadata tracking).
- Privacy/minimization compliance (only document knowledge + question + prompt sent to LLM).
- Frontend: query/chat panel UI, answers with clickable/navigable evidence.

**Out of scope (belongs to other features or future iterations):**
- Knowledge Model extraction (completed in Feature 3).
- Knowledge Model visualization (completed in Feature 4).
- Quality analysis (completed in Feature 5).
- Conversation history persistence across sessions (no multi-turn memory stored server-side).
- RAG with vector embeddings or external retrieval (context is the Knowledge Model, not a vector store).
- Document comparison queries (multi-document).
- Custom query templates defined by the user.
- Fine-tuning or learning from past queries.
- User feedback on query answers (Feature 7 scope).
- Streaming responses.

## Glossary

| Term | Definition |
|------|------------|
| Query_Service | The backend service that orchestrates the natural language query pipeline: receives the question, constructs context, calls the LLM, parses the response, and verifies evidence. |
| Query | A natural language question posed by the user about the content of their document. |
| Query_Response | The structured answer returned to the user, containing answer text and one or more source_ref evidence references. |
| Context_Construction | The process of selecting relevant Knowledge Model elements and relationships to include in the LLM prompt as context for answering the user's question. |
| source_ref | A flexible evidence reference that traces a response claim back to the original document (includes document_id, chunk_id, page, section, evidence text span). |
| Knowledge_Model | The structured representation of the document's knowledge (typed elements with relationships), produced by Feature 3 and consumed as input by this feature. |
| Relational_Context | Additional Knowledge Model elements included in the query context because they are connected via relationships (constrains, participates_in, depends_on, contradicts) to directly relevant elements. |
| Evidence_Verification | The deterministic process of confirming that a source_ref's evidence text span actually exists in the source document's IR. |
| LLM_Abstraction_Layer | The existing centralized wrapper around LiteLLM (from Feature 3) through which all LLM calls are made. |
| Query_Metadata | Auditing information recorded with each query response: prompt version, model identifier, generation parameters, timestamp. |

---

## Requirements

### Requirement 1: Query Service

**User Story:** As a user, I want to ask natural language questions about my document so that I can obtain answers based on the Knowledge Model without reading the entire document manually.

#### Acceptance Criteria

1. WHEN a user submits a natural language question of 1 to 1000 characters for a document with a completed Knowledge Model, THE Query_Service SHALL process the question and return a structured Query_Response containing an answer text and at least one source_ref linking to the original document. Each source_ref SHALL reference a KnowledgeElement present in the document's Knowledge Model.
2. WHEN the Query_Service receives a question, THE Query_Service SHALL construct a context by selecting Knowledge Model elements whose content is related to the question's subject matter, include these elements and their relationships in the LLM prompt alongside the user's question and the system prompt — no other information is sent. The total context provided to the LLM SHALL NOT exceed the configured model's context window limit.
3. IF the Knowledge Model does not contain sufficient information to answer the question, THEN THE Query_Service SHALL return a response that explicitly states the question cannot be answered based on the available knowledge, without fabricating an answer. The response SHALL still include an empty or absent source_refs list rather than invented references.
4. WHEN the Query_Service returns a response, THE Query_Service SHALL include query metadata: the prompt version used, the LLM model identifier, the generation parameters (temperature), and the response timestamp.
5. IF the LLM service is unavailable or returns an error during query processing, THEN THE Query_Service SHALL return an error response with a descriptive message indicating the failure reason, without returning partial or fabricated answers. The Query_Service SHALL consider the LLM service unavailable if no response is received within 30 seconds.
6. THE Query_Service SHALL process each question independently — no conversation history from prior questions is maintained or used as context between requests. Each query is self-contained.
7. IF a user submits a question for a document whose Knowledge Model has not reached "completed" status, THEN THE Query_Service SHALL reject the request with an error response indicating that the document analysis must be completed before queries can be processed.
8. IF a user submits a question that is empty or exceeds 1000 characters, THEN THE Query_Service SHALL reject the request with an error response indicating the question length constraint.

**Traceability:**
- RF-09: User can query the Knowledge Model via natural language; responses include traceable evidence.
- US-007: User wants to ask questions and get answers based on the Knowledge Model with traceable evidence.
- CA-04: Response uses knowledge from the model and includes traceable evidence.
- ADR-005: Only minimum necessary information sent to LLM.

---

### Requirement 2: Context Construction

**User Story:** As a system, I need to select the most relevant Knowledge Model elements as context for the LLM so that answers are grounded in the document's structured knowledge and enriched with relational context.

#### Acceptance Criteria

1. WHEN a question is received, THE Query_Service SHALL rank Knowledge Model elements by semantic similarity between the question and each element's name, content, and evidence fields, and SHALL select the top-ranked elements up to a maximum of 20 directly relevant elements for inclusion in the context.
2. WHEN relevant elements are selected, THE Query_Service SHALL include their first-degree relationships (constrains, participates_in, depends_on, contradicts) and the target elements of those relationships as additional relational context — limited to one hop from directly relevant elements — so that the LLM can reason about connections between concepts.
3. THE Query_Service SHALL include for each context element: the element type, name, content, and the evidence text span from its source_ref — providing the LLM with both structured knowledge and original document text.
4. THE Query_Service SHALL limit the total context payload to no more than 60% of the LLM's configured context window token limit, prioritizing: (a) directly relevant elements first, (b) relationally connected elements second, (c) elements with verified evidence over unverified ones. Elements that would cause the budget to be exceeded SHALL be excluded in reverse priority order.
5. WHEN the Knowledge Model contains elements marked as `verified = false`, THE Query_Service SHALL still include them in the context if they are among the top-ranked elements selected in criterion 1, but SHALL indicate their unverified status in the prompt so the LLM can account for reduced evidence confidence.
6. THE Query_Service SHALL NOT include user metadata, session history, account information, or any data beyond the Knowledge Model elements, their relationships, the IR text chunks referenced by those elements, and the system prompt (ADR-005 minimization principle).
7. IF no Knowledge Model elements meet the relevance selection criteria for a given question (zero elements selected), THEN THE Query_Service SHALL return the query to the upstream handler with an empty context indicator, allowing Requirement 1 criterion 3 (cannot-answer response) to be triggered rather than sending the LLM a prompt with no contextual grounding.

**Traceability:**
- RF-04: "Consultas por lenguaje natural: enriquecer respuestas con contexto relacional."
- RF-13: Only minimum necessary information sent to AI.
- ADR-005: Minimization — only text + prompts sent; no user metadata.
- ADR-004: Trust by Evidence — context grounded in verified elements.

---

### Requirement 3: Response Parsing and Structure

**User Story:** As a user, I want answers to include specific references to the original document so that I can verify the response and locate the relevant text.

#### Acceptance Criteria

1. WHEN the LLM returns a response to a query, THE Query_Service SHALL parse the response to extract: the answer text and one or more source_ref references (minimum 1, maximum 20) linking claims to the original document.
2. WHEN a source_ref is extracted from the response, THE Query_Service SHALL structure it with: document_id, chunk_id (referencing the IR chunk), page (when available for PDF), section (when available for Markdown), and an evidence field containing the verbatim text span that supports the claim.
3. THE Query_Service SHALL validate that the parsed response conforms to the QueryResponse Pydantic schema. IF the LLM output cannot be parsed into a valid QueryResponse on the first attempt, THEN THE Query_Service SHALL retry the LLM call once with a corrective re-prompt. IF the second attempt also fails validation, THEN THE Query_Service SHALL return an error response indicating a response parsing failure, including the original question text in the error context, rather than returning malformed data.
4. WHEN the answer references multiple distinct claims from different parts of the document, THE Query_Service SHALL include a separate source_ref for each claim, allowing the user to trace each assertion independently. The total source_ref count SHALL equal or exceed the number of distinct claims referenced in the answer — each distinct claim requires at least one source_ref.
5. THE Query_Service SHALL limit the evidence text span in each source_ref to a maximum of 500 characters, consistent with the evidence format used throughout the system.
6. IF the Query_Service returns a parsing failure error, THEN THE error response SHALL include: an error code indicating the failure type ("response_parse_error"), a message describing the parsing failure reason, and the original question — so that the client can identify the failed query and offer the user the option to retry. The error response SHALL be returned even if some of these fields (error code, message, or original question) cannot be populated; omitted fields SHALL be absent rather than fabricated, ensuring the user always knows parsing failed.

**Traceability:**
- ADR-004: source_ref in all responses for Trust by Evidence.
- RF-03.1: source_ref structure (document_id, page, section, chunk_id, evidence).
- RF-09: Responses include traceable evidence (source_ref).
- CA-04: Response includes traceable evidence to document source.

---

### Requirement 4: Evidence Verification

**User Story:** As a user, I want the system to verify that evidence cited in answers actually exists in my document so that I can trust the response is grounded in real text and not fabricated.

#### Acceptance Criteria

1. WHEN a Query_Response is generated with source_refs, THE Query_Service SHALL verify each source_ref's evidence text span against the IR chunks using the following deterministic algorithm: (a) normalize whitespace in the evidence text, (b) attempt exact substring match in the referenced chunk_id, (c) attempt exact substring match in any IR chunk, (d) attempt fuzzy match (80% similarity threshold) in any IR chunk. The source_ref is verified if any step (b), (c), or (d) succeeds.
2. WHEN the evidence text span is matched by any step of the verification algorithm (exact match in referenced chunk, exact match in any chunk, or fuzzy match at 80% similarity threshold), THE Query_Service SHALL mark the source_ref as verified (`evidence_verified = true`).
3. WHEN the evidence text span cannot be matched by any step of the verification algorithm in any IR chunk, THE Query_Service SHALL mark the source_ref as not verified (`evidence_verified = false`) — the source_ref is still included in the response but flagged.
4. THE verification step SHALL NOT call the LLM — it is a deterministic text-matching operation against the IR, reusing the same verification algorithm established in Feature 3 (VerificationService).
5. WHEN a Query_Response contains source_refs where all references have `evidence_verified = false`, THE Query_Service SHALL include a response-level attribute `all_evidence_unverified = true` to indicate reduced confidence in the answer's traceability.
6. IF a source_ref contains an empty or absent evidence text span, THEN THE Query_Service SHALL mark that source_ref as not verified (`evidence_verified = false`) without performing the text-matching algorithm.
7. IF a source_ref references a chunk_id that does not exist in the IR, THEN THE Query_Service SHALL skip the referenced-chunk step and proceed with exact and fuzzy matching against all available IR chunks.

**Traceability:**
- RF-03.2: System verifies evidence exists in original document.
- ADR-004: Verification of references as must-have for Trust by Evidence.
- Feature 3 Requirement 7: Same deterministic text-matching verification approach.

---

### Requirement 5: Query API Endpoint

**User Story:** As a frontend client, I need an API endpoint to submit questions and receive structured answers so that I can build the query/chat UI.

#### Acceptance Criteria

1. WHEN `POST /api/v1/documents/{document_id}/query` is called with a JSON body containing a `question` field (non-empty string, maximum 1000 characters), THE API SHALL process the query and return 200 with a QueryResponse containing: the answer text (maximum 5000 characters), a list of source_refs (each including document_id, chunk_id, page, section, evidence text span, and evidence_verified boolean status; maximum 10 source_refs per response), and query metadata (prompt version, model identifier, temperature value used, and ISO-8601 UTC timestamp of query execution).
2. WHEN `POST /api/v1/documents/{document_id}/query` is called and the document does not have a completed Knowledge Model (analysis session status is not "completed"), THE API SHALL return 409 with an error body containing error code "km_not_completed" and a message indicating that queries require a completed Knowledge Model.
3. WHEN `POST /api/v1/documents/{document_id}/query` is called and the document_id does not correspond to any existing document, THE API SHALL return 404 with an error body containing error code "not_found" and a message identifying the missing document.
4. WHEN `POST /api/v1/documents/{document_id}/query` is called with a missing question field, an empty question, or a question exceeding 1000 characters, THE API SHALL return 422 with a validation error indicating the specific constraint violation (missing field, empty value, or character limit exceeded).
5. IF the query processing fails due to an LLM error or internal processing error, THEN THE API SHALL return 500 with an error body containing error code "query_failed" and a message indicating the failure category (LLM unavailable, LLM timeout, or internal processing error) without exposing internal stack traces or implementation details.
6. WHEN `POST /api/v1/documents/{document_id}/query` is called with a valid request, THE API SHALL return the complete response within 30 seconds. This timeout applies only to requests that pass validation and proceed to actual query processing — requests immediately rejected for validation errors (422) are not subject to this timeout. Queries are processed synchronously and do not require polling.

**Traceability:**
- MVP Roadmap Feature 6: "API: POST /{id}/query."
- Document Ingestion & Analysis Engine API patterns (404/409 for state conflicts).
- ADR-004: source_ref and evidence traceability in all responses.

---

### Requirement 6: Query Prompt Template

**User Story:** As a developer, I need a dedicated versioned prompt template for query answering so that the query behavior is auditable, reproducible, and improvable.

#### Acceptance Criteria

1. THE Query_Service SHALL use a versioned prompt template for query answering, stored as a Python module in the prompts directory with a `VERSION` string constant and a `build()` function that accepts the selected Knowledge Model elements and the user's question as parameters, returning the complete prompt string.
2. THE query prompt SHALL require: a direct answer to the question based only on the provided Knowledge Model context, at least 1 and at most 10 evidence references (verbatim text spans from the source document corresponding to `SourceRef.evidence` fields) when the question is answerable from context, zero evidence references when the response is a "cannot answer" indication, and an explicit instruction to produce a "cannot answer" indication when the question cannot be answered from the available context.
3. THE query prompt SHALL include as context only: the selected KnowledgeElement fields (type, name, content, source_ref.evidence) and their Relation entries (target_id, type), plus the user's question as a plain string. No user metadata, account information, or session history is included in the prompt.
4. THE query prompt SHALL require structured JSON output conforming to the QueryResponse Pydantic model, which includes at minimum: an answer text field, a list of evidence references, and a boolean or enum field indicating whether the question was answerable from context, such that the output can be validated by calling the model's constructor without raising a ValidationError.
5. WHEN a new query prompt version is created, THE previous version file SHALL remain in the prompts directory unchanged, preserving its module and VERSION constant for comparison and rollback.
6. THE query prompt SHALL instruct the LLM to ground every claim in the answer to at least one verbatim evidence span from the provided context, and to explicitly label any statement that requires reasoning beyond what is directly stated as unsupported — so that an answer containing a claim with no matching evidence reference is considered non-conformant. WHEN no context elements are available (empty context), the grounding requirement is not applicable — THE Query_Service SHALL immediately return the "cannot answer" indication rather than attempting to ground claims without evidence.
7. IF the provided Knowledge Model context contains zero elements relevant to the user's question, THEN THE query prompt SHALL instruct the LLM to return the "cannot answer" indication with an empty evidence list rather than generating an answer from parametric knowledge.

**Traceability:**
- Feature 3 Requirement 2: Prompt Template System pattern.
- ADR-004: Prompts versionados e inmutables por release.
- ADR-005: Only text + prompts sent; minimization principle.
- RF-09: Answers based on Knowledge Model with traceable evidence.

---

### Requirement 7: Reproducibility and Minimization

**User Story:** As a user, I want query answers to be consistent and I want to be confident that only the minimum necessary information is sent to the AI service.

#### Acceptance Criteria

1. WHEN the same question is asked twice against the same Knowledge Model with the same model configuration and prompt version, THE Query_Service SHALL produce structurally consistent answers — the same set of source_ref chunk_ids are referenced and the same principal factual claims are present in both responses, though exact phrasing may differ. Structural consistency is satisfied when both responses reference the same chunk_ids and contain assertions about the same topics/entities as determined by the source_refs included.
2. WHEN the Query_Service sends data to the LLM, THE Query_Service SHALL send only: the Knowledge Model elements and relationships selected as context, the IR text chunks referenced by those elements, the user's question, and the system prompt. No user identity, session history, account metadata, or information unrelated to the document content is included.
3. WHEN a query response is returned, THE Query_Service SHALL include metadata recording: the prompt version used (matching the VERSION constant from the prompt module), the model identifier used (provider/model string), the generation parameters (temperature value), and the response timestamp in ISO 8601 UTC format — enabling auditability and cross-run comparison.
4. THE Query_Service SHALL use controlled generation parameters (temperature ≤ 0.1 by default) to maximize reproducibility of answers. IF a system configuration specifies a temperature value greater than 0.1, THEN THE Query_Service SHALL accept the override but record the actual temperature used in the response metadata.
5. THE Query_Service SHALL communicate with the LLM exclusively through the existing LLM abstraction layer (LiteLLM wrapper from Feature 3), inheriting its fallback, rate limiting, and configuration capabilities. THE Query_Service SHALL NOT make direct calls to any LLM provider API bypassing this layer.

**Traceability:**
- ADR-004: Bounded reproducibility — structural consistency.
- ADR-005: Minimization principle — only text + prompts sent.
- RF-13: Only minimum necessary information sent to AI.
- RF-15: Provider abstraction layer — all calls through LLM abstraction.
- Feature 3 Requirement 1: LLM Abstraction Layer reused.

---

### Requirement 8: Query Chat UI

**User Story:** As a user, I want an integrated chat/query panel in the application so that I can ask questions and see answers with clickable evidence references that navigate me to the relevant document text.

#### Acceptance Criteria

1. WHEN the user navigates to a document with a completed Knowledge Model, THE UI SHALL display a query panel (chat interface) where the user can type and submit natural language questions. The input field SHALL indicate the maximum question length (1000 characters) and SHALL disable the submit action when the input is empty or exceeds 1000 characters.
2. WHEN the user submits a question, THE UI SHALL display a loading indicator while the query is being processed, disable the submit button to prevent duplicate submissions, and render the answer text once the response is received. IF no response is received within 30 seconds, THEN THE UI SHALL display a timeout message and re-enable the input.
3. WHEN a Query_Response is displayed, THE UI SHALL render each source_ref as a clickable/navigable evidence reference that shows: the evidence text span (truncated to 200 characters with an expand option if longer), the section or page reference (when available), and a visual indicator of verification status (verified vs. unverified) using distinct iconography and text labels in addition to color.
4. WHEN the user clicks on an evidence reference, THE UI SHALL navigate to the Knowledge Model element containing the cited evidence and highlight the matching text span. IF the target element is already visible, THE UI SHALL scroll to and highlight it without full navigation.
5. WHEN a query returns an error or indicates the question cannot be answered, THE UI SHALL display a user-facing message distinguishing between: (a) the question cannot be answered from available knowledge (informational tone, suggesting the user rephrase or try a different question), and (b) a system error occurred (apologetic tone, suggesting the user try again later). Technical error details SHALL NOT be shown.
6. THE UI SHALL display the conversation within the current session as a scrollable list of question-answer pairs, maintaining visual context of prior questions asked during the same session. The session is defined as the current page lifecycle — conversation history is cleared when the user navigates away from the document or refreshes the page (client-side only, not persisted server-side).
7. THE query panel SHALL be accessible: input field is keyboard-navigable, evidence references are focusable and activatable via keyboard, loading states are announced to screen readers via ARIA live regions, and verification status indicators SHALL meet WCAG 2.1 AA contrast ratio (minimum 4.5:1 for text, 3:1 for graphical elements).

**Traceability:**
- MVP Roadmap Feature 6: "Frontend: panel de chat/consulta, respuestas con evidencia clicable/navegable."
- US-007: User wants to ask questions and get answers with traceable evidence.
- ADR-004: source_ref visible to user for verification (Trust by Evidence).
- CA-04: Response includes traceable evidence to document source.
