# Design — Natural Language Queries

## Overview

This document describes the technical design for the Natural Language Queries feature (Feature 6). It covers the architecture, data models, API contracts, module structure, and key technical decisions required to implement the approved requirements.

The query engine is the system's interactive capability. It consumes the completed Knowledge Model (produced by Feature 3) and enables users to ask natural language questions about their document, receiving structured answers grounded in the Knowledge Model with traceable evidence (`source_ref`). This completes the MVP's interactive experience (PRD C5: Asistencia mediante IA) — users can explore document knowledge through conversation rather than only passive visualization.

## Relevant Documentation

- #[[file:.kiro/specs/natural-language-queries/requirements.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/design.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:src/backend/app/models/knowledge_model.py]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/backend/app/analysis/verification.py]]

---

## Architecture

### System Context

```
┌──────────────┐     ┌────────────────────────────────────────────────────────┐
│   Frontend   │────▶│              Natural Language Query Engine               │
│  (Query Chat │◀────│  (context construction → LLM call → response parsing →  │
│   Panel)     │     │   evidence verification)                                │
└──────────────┘     └────────────────────────────────────────────────────────┘
                                      │                    ▲
                                      │                    │
                                      ▼                    │
                              ┌───────────────┐    ┌──────────────────┐
                              │  LLM Providers │    │  Knowledge Model │
                              │  (Gemini/Groq) │    │  (Feature 3)     │
                              └───────────────┘    └──────────────────┘
                                                           ▲
                                                           │
                                                   ┌──────────────────┐
                                                   │  IR (Ingestion)  │
                                                   │  (Feature 1)     │
                                                   └──────────────────┘
```

### Internal Module Decomposition

The query engine is organized into five internal modules:

1. **QueryService** — Orchestrator that receives the question, coordinates context construction, LLM call, parsing, and verification.
2. **ContextBuilder** — Selects relevant KM elements via LLM-based semantic scoring, includes relational context (one-hop), manages token budget (60% of context window).
3. **ResponseParser** — Parses LLM JSON output into QueryResponse Pydantic model, handles retry with corrective re-prompt on parse failure.
4. **QueryEvidenceVerifier** — Adapts existing `VerificationService` algorithm for query source_refs against IR chunks.
5. **Prompt templates** — Two versioned prompt modules: `query_answering_v1.py` (answer generation) and `query_relevance_scoring_v1.py` (context element scoring).

### Pipeline Flow

```
API: POST /api/v1/documents/{document_id}/query
       │
       ├── [document not found] → 404
       ├── [KM not completed] → 409
       ├── [question empty or >1000 chars] → 422
       │
       ▼
QueryService.answer(document_id, question)
       │
       ├── Step 1: ContextBuilder.build_context(question, km, ir, context_window_tokens)
       │       ├── Score KM elements by semantic relevance to question
       │       ├── Select top-N elements (max 20)
       │       ├── Include first-degree relationships (one hop)
       │       ├── Enforce 60% token budget
       │       └── [zero elements selected] → return empty context indicator
       │
       ├── [empty context] → return "cannot answer" response immediately
       │
       ├── Step 2: Build prompt via query_answering_v1.build()
       │       └── Includes: selected elements + relations + question + instructions
       │
       ├── Step 3: LLMClient.call(prompt, model_tier="primary", temperature≤0.1)
       │       ├── [LLM timeout >30s] → return error
       │       └── [LLM error] → fallback via LLMClient, else return error
       │
       ├── Step 4: ResponseParser.parse(llm_output)
       │       ├── Validate against QueryResponse Pydantic schema
       │       ├── [parse failure] → retry once with corrective re-prompt
       │       └── [second failure] → return parsing error response
       │
       ├── Step 5: QueryEvidenceVerifier.verify(source_refs, ir)
       │       ├── For each source_ref: normalize → exact match → fuzzy match
       │       ├── Set evidence_verified on each source_ref
       │       └── Set all_evidence_unverified if all refs are unverified
       │
       ├── Step 6: Attach query metadata (prompt version, model_id, temperature, timestamp)
       │
       └── Return QueryResponse (200)

ON FAILURE:
       ├── LLM unavailable/timeout → 500 with "query_failed" error
       ├── Parse failure (after retry) → 500 with "response_parse_error"
       └── Internal error → 500 with "query_failed"
```

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `api/v1/query.py` | HTTP layer — POST to submit query, return response | REST endpoint (POST) | `QueryService` |
| `QueryService` | Orchestrates the query pipeline end-to-end | `answer(document_id, question) → QueryResponse` | `ContextBuilder`, `ResponseParser`, `QueryEvidenceVerifier`, `LLMClient` |
| `ContextBuilder` | Selects relevant KM elements, manages token budget | `build_context(question, km) → QueryContext` | `LLMClient` (for relevance scoring), KM elements |
| `ResponseParser` | Parses and validates LLM JSON output | `parse(raw_output) → QueryResponse` | Pydantic models |
| `QueryEvidenceVerifier` | Verifies evidence spans against IR | `verify(source_refs, ir) → list[QuerySourceRef]` | IR chunks, verification algorithm |
| `query_answering_v1.py` | Versioned prompt template | `VERSION`, `build(context_elements, question)` | — |
| `query_relevance_scoring_v1.py` | Versioned prompt for element relevance scoring | `VERSION`, `build(question, element_summaries)` | — |

### Key Interfaces

```python
# --- Query Models (Req 1, 3, 4, 5) ---

class QuerySourceRef(BaseModel):
    """A source reference in a query response linking a claim to the original document."""
    document_id: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    evidence: str = Field(max_length=500)  # Verbatim text span, max 500 chars
    evidence_verified: bool = False  # Set by QueryEvidenceVerifier


class QueryMetadata(BaseModel):
    """Auditing metadata for reproducibility."""
    prompt_version: str  # e.g., "query-answering-v1"
    model_id: str  # e.g., "gemini/gemini-2.5-flash"
    temperature: float  # Actual temperature used
    timestamp: datetime  # ISO 8601 UTC


class QueryResponse(BaseModel):
    """Complete response to a natural language query."""
    answer: str = Field(max_length=5000)
    answerable: bool  # True if answered from context, False if "cannot answer"
    source_refs: list[QuerySourceRef] = Field(default_factory=list, max_length=10)
    all_evidence_unverified: bool = False  # True when ALL source_refs are unverified
    metadata: QueryMetadata


class QueryRequest(BaseModel):
    """Request body for the query endpoint."""
    question: str = Field(min_length=1, max_length=1000)


class QueryErrorResponse(BaseModel):
    """Error response for query failures."""
    error: str  # Error code: "query_failed", "response_parse_error", "km_not_completed", "not_found"
    message: str
    question: str | None = None  # Included for parse errors
```

```python
# --- Service Interfaces ---

class QueryContext(BaseModel):
    """The assembled context for the LLM prompt."""
    elements: list[QueryContextElement]  # Selected KM elements with fields
    relations: list[QueryContextRelation]  # First-degree relations
    total_tokens: int  # Estimated token count
    has_unverified_elements: bool  # Whether any element has verified=False


class QueryContextElement(BaseModel):
    """A KM element formatted for inclusion in the query context."""
    element_id: str
    type: str
    name: str
    content: str
    evidence: str
    verified: bool


class QueryContextRelation(BaseModel):
    """A relation entry included in context."""
    source_id: str
    target_id: str
    type: str
    description: str | None = None


class ContextBuilder:
    """Selects relevant KM elements and constructs the query context."""

    def __init__(self, llm_client: LLMClient, max_elements: int = 20, budget_ratio: float = 0.6) -> None: ...

    async def build_context(
        self,
        question: str,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
        context_window_tokens: int,
    ) -> QueryContext | None:
        """Build query context from KM elements.

        Returns None if no elements meet relevance criteria (empty context).
        Selects up to max_elements directly relevant elements.
        Includes first-degree relationships (one hop).
        Enforces budget_ratio * context_window_tokens limit.
        Prioritizes: directly relevant > relationally connected > verified over unverified.
        """
        ...


# --- Prompt Modules ---

# query_relevance_scoring_v1.py
VERSION = "query-relevance-scoring-v1"

def build(question: str, element_summaries: list[dict[str, str]]) -> str:
    """Construct the relevance scoring prompt.
    
    Args:
        question: The user's natural language question.
        element_summaries: List of dicts with keys 'id', 'type', 'name', 'content_preview'
            (first 100 chars of content for each KM element).
    
    Returns:
        Prompt that asks the LLM to score each element 0-10 for relevance to the question.
        Output format: JSON array of {"id": "...", "score": N}
    """
    ...


class ResponseParser:
    """Parses LLM output into QueryResponse with retry."""

    def parse(self, raw_output: str, document_id: str) -> QueryResponse:
        """Parse raw LLM JSON output into a validated QueryResponse.

        The document_id parameter is set on each source_ref after parsing
        (the LLM output does not contain document_id — only chunk_ids).

        Raises ResponseParseError if the output cannot be parsed.
        """
        ...

    def build_corrective_reprompt(self, original_prompt: str, raw_output: str, error: str) -> str:
        """Build a corrective re-prompt for the retry attempt."""
        ...


class QueryEvidenceVerifier:
    """Verifies query source_ref evidence against the IR."""

    def __init__(self, fuzzy_threshold: float = 0.8) -> None: ...

    def verify(
        self,
        source_refs: list[QuerySourceRef],
        ir: IntermediateRepresentation,
    ) -> list[QuerySourceRef]:
        """Verify each source_ref's evidence text against IR chunks.

        Algorithm (same as VerificationService):
        1. Normalize whitespace in evidence text.
        2. Exact substring match in referenced chunk_id.
        3. Exact substring match in any IR chunk.
        4. Fuzzy match (80% threshold) in any chunk.

        Sets evidence_verified on each source_ref.
        Does NOT call the LLM — purely deterministic.
        """
        ...


class QueryService:
    """Orchestrates the complete natural language query pipeline."""

    def __init__(
        self,
        llm_client: LLMClient,
        context_builder: ContextBuilder,
        response_parser: ResponseParser,
        evidence_verifier: QueryEvidenceVerifier,
    ) -> None: ...

    async def answer(
        self,
        document_id: str,
        question: str,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
    ) -> QueryResponse:
        """Process a natural language query and return a grounded answer.

        Pipeline:
        1. Build context (select relevant KM elements).
        2. Construct prompt via query_answering_v1.build().
        3. Call LLM (primary tier, temperature ≤ 0.1).
        4. Parse response (with one retry on failure).
        5. Verify evidence against IR.
        6. Attach metadata.

        Returns QueryResponse on success.
        Raises QueryError on LLM failure or parse failure after retry.
        Timeout: 30 seconds total.
        """
        ...
```

---

## Data Models

### Query Response Models (Pydantic)

The Pydantic models are defined above in the Interfaces section. Key design decisions:

- `QueryResponse` unifies both answerable and "cannot answer" cases via the `answerable` boolean.
- `QuerySourceRef` reuses the same field structure as the existing `SourceRef` (from knowledge_model.py) with the addition of `evidence_verified`.
- `QueryMetadata` is embedded in every response for reproducibility auditing.
- `all_evidence_unverified` is a response-level flag computed from individual source_ref verification status.
- No `conversation_id` or session references — queries are stateless (Req 1.6).

### Database Schema

**No new database tables are required.** The query feature is entirely stateless:

- Queries are not persisted server-side (Req 1.6).
- No conversation history is stored.
- The Knowledge Model and IR (consumed as input) already exist in the `analysis_sessions` and `document_chunks` tables.
- The frontend maintains session conversation history client-side only (Req 8.6).

This is a deliberate decision to minimize scope and enforce statelessness. If query analytics or history are needed in the future, a `query_logs` table can be added without affecting the query pipeline.

---

## API Design

### POST /api/v1/documents/{document_id}/query

Submits a natural language question and returns a structured answer. Synchronous — returns 200 with the complete response.

**Request Body:**
```json
{
  "question": "What are the main actors described in this document?"
}
```

**Response (200) — Query answered:**
```json
{
  "answer": "The document describes three main actors: the System Administrator who manages infrastructure, the End User who interacts with the product, and the API Consumer who integrates programmatically.",
  "answerable": true,
  "source_refs": [
    {
      "document_id": "uuid",
      "chunk_id": "chunk-005",
      "page": null,
      "section": "## Actors and Roles",
      "evidence": "The System Administrator is responsible for infrastructure management and user provisioning",
      "evidence_verified": true
    },
    {
      "document_id": "uuid",
      "chunk_id": "chunk-005",
      "page": null,
      "section": "## Actors and Roles",
      "evidence": "End Users interact with the product through the web interface",
      "evidence_verified": true
    },
    {
      "document_id": "uuid",
      "chunk_id": "chunk-007",
      "page": null,
      "section": "## API Integration",
      "evidence": "API Consumers integrate with the system programmatically via the REST API",
      "evidence_verified": true
    }
  ],
  "all_evidence_unverified": false,
  "metadata": {
    "prompt_version": "query-answering-v1",
    "model_id": "gemini/gemini-2.5-flash",
    "temperature": 0.1,
    "timestamp": "2026-08-01T14:30:00Z"
  }
}
```

**Response (200) — Cannot answer:**
```json
{
  "answer": "The available knowledge does not contain information about deployment procedures. The document focuses on product requirements and user roles.",
  "answerable": false,
  "source_refs": [],
  "all_evidence_unverified": false,
  "metadata": {
    "prompt_version": "query-answering-v1",
    "model_id": "gemini/gemini-2.5-flash",
    "temperature": 0.1,
    "timestamp": "2026-08-01T14:30:05Z"
  }
}
```

**Error Responses:**

| Status | Condition | Error Code |
|--------|-----------|------------|
| 404 | Document not found | `not_found` |
| 409 | Knowledge Model not completed | `km_not_completed` |
| 422 | Question empty or exceeds 1000 characters | Pydantic validation error |
| 500 | LLM error, timeout, or parse failure | `query_failed` or `response_parse_error` |

**409 response (KM not completed):**
```json
{
  "error": "km_not_completed",
  "message": "Queries require a completed Knowledge Model. Current analysis status: extracting."
}
```

**500 response (query failed):**
```json
{
  "error": "query_failed",
  "message": "Query processing failed: LLM service unavailable."
}
```

**500 response (parse error):**
```json
{
  "error": "response_parse_error",
  "message": "Failed to parse LLM response after retry: missing 'answer' field in JSON output.",
  "question": "What are the main actors described in this document?"
}
```

---

## Key Technical Decisions

### Decision 1: Context Construction — LLM-Based Semantic Scoring

**Choice:** Use LLM-based scoring (via the light model tier) to rank KM elements by semantic relevance to the question, rather than keyword matching or embedding-based retrieval.

**Reasoning:** The Knowledge Model is relatively small (typically 10–50 elements). Vector embeddings would require an embedding model and index infrastructure that the MVP doesn't have. Simple keyword matching misses semantic relationships (e.g., "performance" matching "restriccion" elements about response times). LLM-based scoring via the light model provides semantic understanding with acceptable latency for <50 elements. The scoring prompt asks the LLM to rate each element's relevance to the question on a 0–10 scale.

### Decision 2: Token Budget Management — 60% of Context Window

**Choice:** Limit total context (selected elements + relations + prompt template) to 60% of the configured model's context window.

**Reasoning:** Leaving 40% for the LLM's response generation ensures the model has adequate space for a comprehensive answer (up to 5000 chars) plus JSON structure. The 60% limit is applied after element selection and enforced by trimming elements in reverse priority order (relational context first, then lower-scored direct elements).

**Token estimation:** For the MVP, tokens are estimated using a simple character-based heuristic: `estimated_tokens = len(text) / 4`. This avoids adding a `tiktoken` dependency for a rough estimate. The 60% budget is conservative enough that the ~10% estimation error from this heuristic does not cause prompt truncation issues. If precision becomes necessary in the future, a tokenizer library can replace the heuristic without changing the budget logic.

### Decision 3: Synchronous API with 30-Second Timeout

**Choice:** The query endpoint is fully synchronous (returns 200, not 202 + polling). A 30-second timeout wraps the entire pipeline.

**Reasoning:** Query-answer interactions are inherently request-response. Users expect immediate answers in a chat interface. The pipeline (context construction + one LLM call + parsing + verification) typically completes in 3–10 seconds. The 30-second timeout (Req 5.6) catches edge cases where the LLM is slow without blocking the client indefinitely. On timeout, the endpoint returns 500 with a descriptive error.

**Latency budget breakdown:** The 30-second total budget is distributed as:
- Context scoring (light model): ~1–3 seconds (batch scoring of all elements in one call)
- Answer generation (primary model): ~3–8 seconds
- Retry on parse failure (if needed): ~3–8 seconds additional
- Evidence verification (deterministic): <100ms
- Overhead (DB reads, parsing): <500ms

Worst case with retry: ~12–19 seconds. The LLMClient's built-in fallback adds at most one additional attempt per call (scoring + answer), which in extreme cases could reach ~25 seconds. The 30-second timeout provides sufficient margin. If the scoring call fails and triggers fallback + the answer call also fails and triggers fallback + a retry is needed, the pipeline will likely timeout — this is acceptable as it represents a severe degradation scenario where returning an error is the correct behavior.

### Decision 4: Stateless — No Query Persistence

**Choice:** Queries are not stored server-side. No conversation history, no query logs, no database writes during query processing.

**Reasoning:** Per Req 1.6, each query is independent. Statelessness simplifies the architecture (no new tables, no cleanup jobs, no session management). The frontend maintains conversation history client-side for the current page lifecycle (Req 8.6). If query analytics are needed later, a write-behind log can be added without changing the pipeline.

### Decision 5: Retry Mechanism — One Corrective Re-Prompt

**Choice:** On parse failure, retry once with a corrective re-prompt that includes the original prompt, the invalid output, and a correction instruction. If the second attempt also fails, return a parsing error.

**Reasoning:** LLMs occasionally produce malformed JSON or miss required fields. A single retry with explicit correction ("your previous output was invalid because X, please produce valid JSON") resolves most transient formatting issues. More than one retry would unacceptably increase latency within the 30-second budget.

### Decision 6: Evidence Verification — Reuse Existing Algorithm

**Choice:** Reuse the same deterministic text-matching algorithm from `VerificationService` (Feature 3) for query evidence verification.

**Reasoning:** ADR-004 mandates evidence verification for all responses. The existing algorithm (normalize → exact match in referenced chunk → exact match in any chunk → fuzzy match at 80%) is proven, deterministic, and tested. The `QueryEvidenceVerifier` wraps this logic for the query source_ref format without duplicating the algorithm.

### Decision 7: Relevance Scoring Strategy

**Choice:** Score elements using a single LLM call with the light model tier that rates all elements at once, rather than individual scoring calls.

**Reasoning:** With a typical KM of 10–50 elements, a single prompt can present all element summaries (type + name + first 100 chars of content) and ask for relevance scores. This uses one LLM call for scoring vs. N calls for individual scoring. The light model tier keeps latency low. If the scoring call fails, the system falls back to including all elements up to the token budget (no ranking, just truncation).

### Decision 8: Unverified Elements in Context

**Choice:** Include unverified KM elements in context if they are among the top-ranked, but annotate them in the prompt with "[UNVERIFIED]" markers.

**Reasoning:** Per Req 2.5, unverified elements should not be excluded (they may still contain correct knowledge), but the LLM should be aware of reduced confidence. The annotation allows the LLM to weight its reliance on those elements and potentially indicate lower confidence in claims derived from them.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Response Structural Completeness

*For any* valid query that produces an answerable response, the QueryResponse SHALL contain: a non-empty answer text (max 5000 chars), at least 1 and at most 10 source_refs, and each source_ref SHALL have a non-empty document_id, a non-empty chunk_id, and an evidence field of at most 500 characters.

**Validates: Requirements 1.1, 3.1, 3.2, 3.5, 5.1**

### Property 2: Context Budget Compliance

*For any* Knowledge Model and question, the context constructed by ContextBuilder SHALL select at most 20 directly relevant elements AND the total token count of the assembled context (elements + relations + prompt template) SHALL NOT exceed 60% of the configured context window token limit.

**Validates: Requirements 2.1, 2.4**

### Property 3: Relational Context One-Hop Bound

*For any* set of directly relevant elements selected during context construction, the additional relational context elements included SHALL be reachable in exactly one hop via the Knowledge Model's relationship graph. No element more than one relationship edge away from a directly relevant element SHALL appear in the context.

**Validates: Requirements 2.2**

### Property 4: Data Minimization

*For any* prompt constructed by the query pipeline, the prompt content SHALL contain only Knowledge Model elements (type, name, content, evidence), their relationships, the user's question as a plain string, and system instructions. No user identity, session history, account metadata, document_id, or information unrelated to the document content SHALL be present in the prompt.

**Validates: Requirements 2.6, 6.3, 7.2**

### Property 5: Empty Context Cannot-Answer

*For any* query where context construction selects zero relevant elements, the QueryResponse SHALL have `answerable = false`, an answer text explaining the limitation, and an empty source_refs list. No fabricated evidence SHALL be returned.

**Validates: Requirements 1.3, 2.7**

### Property 6: Evidence Verification Determinism

*For any* set of source_refs and a fixed IR, applying the verification algorithm (normalize → exact match in referenced chunk → exact match in any chunk → fuzzy match at 80%) produces the same `evidence_verified` values on every invocation. *For any* QueryResponse where all source_refs have `evidence_verified = false`, the response-level `all_evidence_unverified` attribute SHALL be `true`.

**Validates: Requirements 4.1, 4.2, 4.3, 4.5**

### Property 7: Query Statelessness

*For any* sequence of queries submitted to the same document, each query's context construction and prompt SHALL contain no information from prior queries in the sequence. The context and response for query N SHALL be identical whether it is the first query or the hundredth.

**Validates: Requirements 1.6**

### Property 8: Knowledge Model Prerequisite Gate

*For any* document whose analysis session status is not "completed", submitting a query SHALL return a 409 error response with code "km_not_completed" without executing any part of the query pipeline (no LLM calls, no context construction).

**Validates: Requirements 1.7, 5.2**

### Property 9: Input Validation

*For any* question string that is empty (length 0) or exceeds 1000 characters, the query endpoint SHALL return a 422 validation error without executing any part of the query pipeline.

**Validates: Requirements 1.8, 5.4**

### Property 10: Metadata Completeness

*For any* QueryResponse (whether answerable or not), the metadata field SHALL contain: a non-empty prompt_version string matching the VERSION constant from the prompt module, a non-empty model_id string, a temperature float value, and a timestamp in ISO 8601 UTC format.

**Validates: Requirements 1.4, 7.3, 5.1**

### Property 11: Controlled Temperature

*For any* LLM call made by the QueryService using default configuration, the temperature parameter SHALL be ≤ 0.1. If a system configuration overrides the temperature to a value > 0.1, the actual temperature used SHALL be recorded in the response metadata.

**Validates: Requirements 7.4**

---

## Interaction Flow

```
=== QUERY SUBMISSION (POST /api/v1/documents/{document_id}/query) ===

1. Client calls POST /api/v1/documents/{document_id}/query with {"question": "..."}
       │
       ├── [document not found] → 404 {"error": "not_found", "message": "..."}
       ├── [analysis session not found] → 404
       ├── [analysis session status ≠ "completed"] → 409 {"error": "km_not_completed"}
       ├── [question empty or >1000 chars] → 422 (Pydantic validation)
       │
       ▼
2. Load Knowledge Model + IR from database
       │── Retrieve KM from analysis_sessions.knowledge_model
       │── Retrieve IR chunks from document_chunks
       │
       ▼
3. ContextBuilder.build_context(question, km, ir, context_window_tokens)
       │── Score all KM elements for relevance to question (light model)
       │── Select top-20 directly relevant elements
       │── Include first-degree relationships (one hop)
       │── Annotate unverified elements with [UNVERIFIED] marker
       │── Enforce 60% token budget (trim in reverse priority order)
       │
       ├── [zero elements selected] → skip to step 3b
       │       └── 3b: Return QueryResponse(answerable=false, source_refs=[], ...)
       │
       ├── [scoring LLM fails] → fallback: include all elements up to budget
       │
       ▼
4. Build prompt: query_answering_v1.build(context_elements, question)
       │── Format elements with type, name, content, evidence
       │── Format relations with source_id, target_id, type
       │── Include "cannot answer" instruction for insufficient context
       │── Include grounding requirement (every claim → evidence)
       │── Require JSON output conforming to QueryResponse schema
       │
       ▼
5. LLMClient.call(prompt, model_tier="primary", temperature=0.1)
       │── [success] → raw JSON string
       │── [transient error] → auto-fallback to secondary model (LLMClient built-in)
       │── [both models fail] → raise QueryError → 500
       │── [timeout >30s] → raise QueryError → 500
       │
       ▼
6. ResponseParser.parse(raw_output, document_id)
       │── Extract JSON from LLM output
       │── Validate against QueryResponse Pydantic schema
       │── Set document_id on each source_ref
       │
       ├── [parse success] → QueryResponse
       ├── [parse failure, attempt 1] →
       │       └── Build corrective re-prompt → LLMClient.call() → parse again
       │           ├── [parse success] → QueryResponse
       │           └── [parse failure, attempt 2] → raise ResponseParseError → 500
       │
       ▼
7. QueryEvidenceVerifier.verify(source_refs, ir)
       │── For each source_ref:
       │     normalize whitespace in evidence
       │     try exact match in referenced chunk_id
       │     try exact match in any IR chunk
       │     try fuzzy match (80% threshold) in any chunk
       │     set evidence_verified = true/false
       │── If all source_refs have evidence_verified = false:
       │     set response.all_evidence_unverified = true
       │
       ▼
8. Attach metadata
       │── prompt_version = query_answering_v1.VERSION
       │── model_id = llm_response.model_id
       │── temperature = actual temperature used
       │── timestamp = datetime.now(UTC)
       │
       ▼
9. Return 200 with QueryResponse
```

---

## Error Handling

| Error Source | Error Type | HTTP Status | Behavior | Recovery |
|-------------|-----------|-------------|----------|----------|
| Document not found | Prerequisite | 404 | Return error with "not_found" code | Correct document_id |
| KM not completed | Prerequisite | 409 | Return error with "km_not_completed" code | Wait for KM extraction to complete |
| Question empty or >1000 chars | Validation | 422 | Return Pydantic validation error | Fix question length |
| Primary LLM rate-limited | Transient | — | Auto-fallback to secondary model via LLMClient | Automatic |
| Both LLM models fail | Transient | 500 | Return "query_failed" error | User retries |
| LLM timeout (>30s) | Timeout | 500 | Return "query_failed" with timeout indication | User retries |
| LLM response unparseable (1st attempt) | Parse | — | Retry with corrective re-prompt | Automatic |
| LLM response unparseable (2nd attempt) | Parse | 500 | Return "response_parse_error" with original question | User retries |
| Context scoring LLM fails | Transient | — | Fallback: include all elements up to budget (no ranking) | Automatic (degraded) |
| Zero relevant elements found | Logic | 200 | Return "cannot answer" response (answerable=false) | User rephrases question |
| All evidence unverified | Trust | 200 | Return response with all_evidence_unverified=true | User reviews manually |
| Empty evidence in source_ref | Data | — | Mark source_ref as unverified without running algorithm | N/A |
| Referenced chunk_id not in IR | Data | — | Skip chunk step, proceed with full-IR matching | N/A |

---

## Security Considerations

Aligned with ADR-005 (Privacy and External Processing):

- **Data minimization:** Only KM elements, relationships, IR text chunks referenced by those elements, the user's question, and system prompts are sent to LLM providers. No user identity, session history, document identifiers, or account metadata is included in prompts (Req 2.6, 7.2).
- **No query persistence:** Queries are not stored server-side. No user questions or answers are persisted, eliminating data retention concerns for query content.
- **Reuses LLM abstraction:** All LLM communication goes through the existing `LLMClient`, maintaining centralized credential management and audit trail.
- **LLM output treated as untrusted:** All LLM responses are validated against Pydantic schemas before being returned to the client. Invalid output is rejected and reported as a failure.
- **Evidence verification:** Source_refs are verified against the actual document text to detect hallucinated evidence. Unverified findings are clearly flagged with `evidence_verified = false` and the response-level `all_evidence_unverified` flag.
- **Input sanitization:** The user's question is included in the prompt as a plain string. The prompt template does not use format string interpolation that could allow prompt injection — the question is placed in a clearly delimited section.
- **No internal details exposed:** Error responses return descriptive messages without stack traces or implementation details (Req 5.5).
- **document_id isolation:** The `document_id` is never included in LLM prompts (Property 4). Source_refs in the LLM's JSON output use chunk_ids only. The `document_id` field is populated by the `ResponseParser` after receiving the LLM response, mapping chunk references to the known document context. This ensures the LLM has no access to document identifiers.

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| ContextBuilder | Element selection, token budget enforcement, one-hop relations, fallback on scoring failure | Unit tests with mocked LLM scoring; property tests for budget and element cap |
| ResponseParser | JSON extraction, Pydantic validation, corrective re-prompt construction | Unit tests with valid/invalid LLM outputs; property tests for structural completeness |
| QueryEvidenceVerifier | Evidence text-matching, all_evidence_unverified flag | Property tests reusing verification algorithm; unit tests for boundary cases (empty evidence, missing chunk_id) |
| QueryService | Pipeline orchestration, statelessness, timeout, error propagation | Unit tests with mocked dependencies; property tests for statelessness and metadata |
| API Endpoint | HTTP contract, status codes, validation, error responses | Integration tests via httpx AsyncClient |
| query_answering_v1 | Prompt structure, data minimization, context formatting | Unit tests verifying prompt content; property tests for data minimization |
| End-to-End | Full pipeline with mocked LLM | Integration tests: KM ready → query → receive answer with verified evidence |

**Property-Based Testing (Hypothesis):**

The following correctness properties will be tested using property-based testing (minimum 100 iterations):

- Property 1: Response Structural Completeness — generate random valid QueryResponses, verify all field constraints
- Property 2: Context Budget Compliance — generate KMs of varying sizes, verify max 20 elements and token budget
- Property 3: Relational Context One-Hop Bound — generate KMs with deep relationship chains, verify only one hop included
- Property 4: Data Minimization — generate random prompts, verify no forbidden content present
- Property 5: Empty Context Cannot-Answer — generate queries with irrelevant KMs, verify "cannot answer" structure
- Property 6: Evidence Verification Determinism — generate random evidence+IR pairs, verify deterministic results
- Property 7: Query Statelessness — generate sequences of queries, verify no cross-contamination
- Property 8: Knowledge Model Prerequisite Gate — generate documents with various statuses, verify rejection
- Property 9: Input Validation — generate strings of various lengths, verify validation behavior
- Property 10: Metadata Completeness — generate responses, verify all metadata fields present
- Property 11: Controlled Temperature — verify temperature parameter constraints

**Property Test Library:** Hypothesis (Python PBT library, already used in the project)

**Test Configuration:**
- Minimum 100 iterations per property test
- Each property test tagged with: `Feature: natural-language-queries, Property {N}: {title}`

**Unit Testing Balance:**
- Unit tests focus on: specific integration examples (LLM failure scenarios, retry flow), edge cases (empty KM, max-length questions), error response formatting
- Property tests focus on: universal constraints that hold across all inputs (structural completeness, budget limits, data minimization, verification determinism)

All tests use mocked LLM responses to avoid real API calls during CI.

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| LiteLLM | LLM provider abstraction (via existing LLMClient) | Project standard; already configured for Features 3 and 5 |
| FastAPI | HTTP framework | Project standard; existing backend framework |
| Pydantic v2 | Data validation for query models and LLM output parsing | Project standard; validates untrusted LLM output |
| supabase-py | Database client for KM/IR retrieval | Project standard; existing database layer |
| pytest + httpx | Testing | Project standard; async integration tests |
| Hypothesis | Property-based testing | Already used in the project (`.hypothesis/` directory present) |

No additional dependencies beyond the project's established stack.

---

## File Structure

```
src/backend/
├── app/
│   ├── api/v1/
│   │   ├── documents.py              # Existing ingestion endpoints
│   │   ├── analysis.py               # Existing KM analysis endpoints
│   │   ├── quality.py                # Existing quality analysis endpoints (Feature 5)
│   │   └── query.py                  # NEW: query endpoint
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── service.py                # Existing AnalysisService
│   │   ├── llm_client.py             # Existing LLMClient (reused)
│   │   ├── type_inference.py         # Existing
│   │   ├── extraction.py             # Existing
│   │   ├── verification.py           # Existing (algorithm reused by QueryEvidenceVerifier)
│   │   ├── query/                     # NEW: Query module
│   │   │   ├── __init__.py
│   │   │   ├── service.py            # QueryService orchestrator
│   │   │   ├── context_builder.py    # ContextBuilder — element selection + budget
│   │   │   ├── response_parser.py    # ResponseParser — JSON parsing + retry
│   │   │   └── evidence_verifier.py  # QueryEvidenceVerifier — evidence verification
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── type_inference_v1.py       # Existing
│   │       ├── extraction_v1.py           # Existing
│   │       ├── contradiction_detection_v1.py  # Existing (Feature 5)
│   │       ├── ambiguity_detection_v1.py      # Existing (Feature 5)
│   │       ├── completeness_evaluation_v1.py  # Existing (Feature 5)
│   │       ├── suggestion_generation_v1.py    # Existing (Feature 5)
│   │       ├── query_answering_v1.py          # NEW: Query answer prompt template
│   │       └── query_relevance_scoring_v1.py  # NEW: Relevance scoring prompt template
│   ├── models/
│   │   ├── document.py               # Existing IR models
│   │   ├── knowledge_model.py        # Existing KM models
│   │   ├── quality_analysis.py       # Existing (Feature 5)
│   │   └── query.py                  # NEW: QueryRequest, QueryResponse, QuerySourceRef, QueryMetadata
│   └── db/
│       └── migrations/
│           ├── 001_create_documents.sql
│           ├── 002_create_analysis_sessions.sql
│           └── 003_add_quality_analysis.sql   # Existing (Feature 5)
└── tests/
    ├── unit/
    │   └── analysis/
    │       ├── query/                         # NEW
    │       │   ├── test_context_builder.py
    │       │   ├── test_response_parser.py
    │       │   ├── test_evidence_verifier.py
    │       │   ├── test_query_service.py
    │       │   └── test_query_models.py
    │       └── ... (existing tests)
    ├── property/                               # Existing (from Feature 5)
    │   └── analysis/
    │       ├── test_quality_properties.py     # Existing (Feature 5)
    │       └── test_query_properties.py       # NEW: Property-based tests
    └── integration/
        └── analysis/
            ├── test_analysis_flow.py          # Existing
            ├── test_quality_flow.py           # Existing (Feature 5)
            └── test_query_flow.py             # NEW

src/frontend/
├── src/
│   ├── components/
│   │   ├── knowledge-model/               # Existing (Feature 4)
│   │   ├── layout/                        # Existing
│   │   ├── ui/                            # Existing (shadcn/ui)
│   │   ├── upload/                        # Existing (Feature 2)
│   │   └── query/                         # NEW: Query chat panel
│   │       ├── QueryPanel.tsx             # Main chat panel component
│   │       ├── QueryInput.tsx             # Input field with char counter
│   │       ├── QueryMessage.tsx           # Question-answer pair display
│   │       ├── EvidenceReference.tsx      # Clickable evidence reference
│   │       └── VerificationBadge.tsx      # Verified/unverified indicator
│   ├── api/                               # Existing
│   ├── store/                             # Existing
│   └── ...
└── tests/                                 # Existing
```

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Query Service | `QueryService`, pipeline orchestration, `query_answering_v1.py` prompt, stateless processing, prerequisite gate, input validation |
| Req 2: Context Construction | `ContextBuilder`, LLM-based semantic scoring, max 20 elements, one-hop relational context, 60% token budget, unverified element annotation, data minimization, empty context handling |
| Req 3: Response Parsing and Structure | `ResponseParser`, Pydantic validation, corrective re-prompt retry, `QuerySourceRef` with max 500 char evidence, error response with original question |
| Req 4: Evidence Verification | `QueryEvidenceVerifier`, deterministic text-matching (normalize → exact → fuzzy at 80%), `evidence_verified` flag, `all_evidence_unverified` response-level flag, empty evidence handling, missing chunk_id handling |
| Req 5: Query API Endpoint | `api/v1/query.py`, POST endpoint, 200/404/409/422/500 responses, 30-second timeout, synchronous processing |
| Req 6: Query Prompt Template | `query_answering_v1.py` + `query_relevance_scoring_v1.py` modules, VERSION constant + build() function, structured JSON output requirement, grounding instruction, "cannot answer" instruction, data minimization in prompt |
| Req 7: Reproducibility and Minimization | `QueryMetadata` with prompt version + model_id + temperature + timestamp, temperature ≤ 0.1 default, all calls through LLMClient, data minimization enforcement |
| Req 8: Query Chat UI | Frontend `QueryPanel` + `QueryInput` + `QueryMessage` + `EvidenceReference` + `VerificationBadge`, client-side session history, accessibility (ARIA live regions, keyboard navigation, WCAG 2.1 AA contrast) |
