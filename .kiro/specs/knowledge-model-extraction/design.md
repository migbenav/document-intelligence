# Design — Knowledge Model Extraction (Analysis Engine)

## Overview

This document describes the technical design for the Knowledge Model Extraction feature (Analysis Engine). It covers the architecture, data models, API contracts, module structure, and key technical decisions required to implement the approved requirements.

The analysis engine is the system's intelligence core. It consumes the Intermediate Representation (IR) produced by the ingestion layer, uses LLMs to extract structured knowledge, and produces a Knowledge Model that downstream features (quality analysis, visualization, natural language queries) consume.

## Relevant Documentation

- #[[file:.kiro/specs/knowledge-model-extraction/requirements.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-006-document-type-schemas.md]]
- #[[file:docs/architecture/001-technology-stack.md]]
- #[[file:.kiro/specs/document-ingestion/design.md]]

---

## Architecture

### System Context

```
┌──────────────┐     ┌────────────────────────────────────────────────────┐     ┌──────────────────┐
│   Frontend   │────▶│              Analysis Engine                        │────▶│  Quality Analysis │
│  (Feature 2) │◀────│  (infer type → confirm → extract → verify)          │     │  (Feature 5)      │
└──────────────┘     └────────────────────────────────────────────────────┘     └──────────────────┘
                                      │                    ▲
                                      │                    │
                                      ▼                    │
                              ┌───────────────┐    ┌──────────────┐
                              │  LLM Providers │    │  Ingestion   │
                              │  (Gemini/Groq) │    │  Layer (IR)  │
                              └───────────────┘    └──────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │   Supabase    │
                              │  (PostgreSQL) │
                              └───────────────┘
```

### Internal Module Decomposition

The analysis engine is organized into five internal modules:

1. **LLM Layer** — Centralized abstraction over LiteLLM with fallback, rate limiting, and config tracking.
2. **Prompts** — Versioned prompt templates for type inference, extraction, and relationship identification.
3. **Type Inference** — Classifies the document type using the light model.
4. **Extraction** — Produces the Knowledge Model (elements + relationships) from IR using the primary model.
5. **Verification** — Deterministic text-matching to confirm evidence references exist in the source document.

### Pipeline Flow

```
API: POST /analyze
       │
       ▼
AnalysisService.start_analysis()
       │
       ├── Create analysis session (status: inferring_type)
       │
       ├── TypeInferenceService.infer(ir)
       │       └── LLM call (light model) → suggested type + justification
       │
       ├── Update session (status: awaiting_confirmation)
       │
       └── Return 202 {session_id, suggested_type, justification}

API: POST /confirm-type
       │
       ▼
AnalysisService.confirm_and_extract()
       │
       ├── Update session (status: extracting, confirmed_type)
       │
       ├── ExtractionService.extract(ir, confirmed_type)
       │       └── LLM call (primary model) → raw Knowledge Model
       │
       ├── Parse + validate against Pydantic schema
       │       └── Complete parse failure → mark failed, stop
       │       └── Individual malformed elements → discard with warning
       │
       ├── Remove dangling relationship references
       │
       ├── Update session (status: verifying)
       │
       ├── VerificationService.verify(knowledge_model, ir)
       │       └── Deterministic text matching → mark verified/not-verified
       │
       ├── Persist Knowledge Model + metadata
       │
       ├── Update session (status: completed)
       │
       └── Return 202 {session_id, status: extracting}
```

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `api/v1/analysis.py` | HTTP layer — receives analysis requests | REST endpoints | `AnalysisService` |
| `AnalysisService` | Orchestrates the analysis pipeline | `start_analysis()`, `confirm_and_extract()` | `TypeInferenceService`, `ExtractionService`, `VerificationService`, `StorageService` |
| `LLMClient` | Centralized LLM communication with fallback | `call(prompt, model_tier)` | LiteLLM |
| `TypeInferenceService` | Infers document type from IR | `infer(ir) → TypeSuggestion` | `LLMClient`, prompt templates |
| `ExtractionService` | Extracts Knowledge Model from IR | `extract(ir, doc_type) → KnowledgeModel` | `LLMClient`, prompt templates |
| `VerificationService` | Verifies evidence references (no LLM) | `verify(km, ir) → VerificationResult` | IR chunks |
| Prompt Templates | Versioned instruction sets | Template modules | — |

### Key Interfaces

```python
# --- LLM Abstraction (Req 1) ---
class LLMClient:
    async def call(
        self,
        prompt: str,
        *,
        model_tier: Literal["primary", "light"] = "primary",
        temperature: float = 0.1,
    ) -> str: ...

# --- Type Inference (Req 3) ---
@dataclass
class TypeSuggestion:
    document_type: str | None  # None when confidence is low (Req 3.3)
    suggested_type: str        # Always "generic" when document_type is None
    justification: str
    confidence: float          # Internal, not exposed to user

class TypeInferenceService:
    async def infer(self, ir: IntermediateRepresentation) -> TypeSuggestion: ...

# --- Extraction (Req 5, 6) ---
class ExtractionService:
    async def extract(
        self, ir: IntermediateRepresentation, document_type: str
    ) -> KnowledgeModel: ...

# --- Verification (Req 7) ---
@dataclass
class VerificationResult:
    verified_count: int
    total_count: int
    verification_rate: float
    unverified_element_ids: list[str]

class VerificationService:
    def verify(
        self, knowledge_model: KnowledgeModel, ir: IntermediateRepresentation
    ) -> VerificationResult: ...

# --- Orchestrator (Req 8, 9) ---
class AnalysisService:
    async def start_analysis(self, document_id: str) -> AnalysisSession: ...
    async def confirm_and_extract(self, document_id: str, document_type: str) -> AnalysisSession: ...
    async def get_knowledge_model(self, document_id: str) -> KnowledgeModel | None: ...
    async def get_session(self, document_id: str) -> AnalysisSession | None: ...
```

---

## Data Models

### Knowledge Model (Pydantic)

```python
class SourceRef(BaseModel):
    document_id: str
    chunk_id: str
    page: int | None = None       # Present for PDF (Req 5.5)
    section: str | None = None    # Present for Markdown (Req 5.5)
    evidence: str                 # Verbatim text span from source document (Req 5.4)

class Relation(BaseModel):
    target_id: str
    type: Literal["constrains", "participates_in", "depends_on", "contradicts"]
    description: str | None = None

class KnowledgeElement(BaseModel):
    id: str
    type: Literal["proposito", "concepto", "actor", "regla", "proceso", "restriccion"]
    name: str
    content: str
    source_ref: SourceRef
    relations: list[Relation] = Field(default_factory=list)
    verified: bool = False        # Set by VerificationService (Req 7)

class ExtractionMetadata(BaseModel):
    prompt_version: str           # Req 2.2, 10.3
    model_id: str                 # Req 1.5, 10.3
    temperature: float            # Req 1.4, 10.3
    element_count: int
    relationship_count: int
    verification_rate: float      # Req 7.4
    extracted_at: datetime

class KnowledgeModel(BaseModel):
    document_id: str
    document_type: str
    elements: list[KnowledgeElement]
    extraction_metadata: ExtractionMetadata
```

### Analysis Session (Database)

```sql
CREATE TABLE analysis_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'inferring_type',
    -- Status values: inferring_type, awaiting_confirmation, extracting, verifying, completed, failed
    suggested_type TEXT,
    suggested_type_justification TEXT,
    confirmed_type TEXT,
    knowledge_model JSONB,        -- Full KnowledgeModel serialized (Req 8.5)
    extraction_metadata JSONB,
    error_message TEXT,
    prompt_version TEXT,
    model_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id)           -- One analysis per document (Req 9.7)
);
```

---

## API Design

### POST /api/v1/documents/{document_id}/analyze

Initiates analysis. Returns after type inference completes.

**Response (202):**
```json
{
  "session_id": "uuid",
  "document_id": "uuid",
  "status": "awaiting_confirmation",
  "suggested_type": "prd",
  "suggested_type_justification": "The document contains sections for requirements, user stories, and acceptance criteria typical of a PRD."
}
```

**Error Responses:**
| Status | Condition |
|--------|-----------|
| 404 | Document not found (Req 9.2) |
| 409 | Document not ready / ingestion incomplete (Req 9.1) |
| 409 | Analysis already exists for this document (Req 9.7) |

### POST /api/v1/documents/{document_id}/confirm-type

Confirms the document type and triggers extraction.

**Request:**
```json
{
  "document_type": "prd"
}
```

**Valid values:** `"prd"`, `"technical_spec"`, `"policy_process"`, `"generic"`

**Response (202):**
```json
{
  "session_id": "uuid",
  "document_id": "uuid",
  "status": "extracting",
  "confirmed_type": "prd"
}
```

**Error Responses:**
| Status | Condition |
|--------|-----------|
| 400 | Invalid type value — response lists valid types (Req 4.5) |
| 404 | Document/session not found |
| 409 | Session not in awaiting_confirmation state (Req 4.4) |
| 409 | Analysis already completed (Req 4.4) |

### GET /api/v1/documents/{document_id}/knowledge-model

Returns the Knowledge Model when analysis is complete.

**Response (200):**
```json
{
  "document_id": "uuid",
  "document_type": "prd",
  "elements": [
    {
      "id": "elem-001",
      "type": "proposito",
      "name": "Purpose",
      "content": "Build an intelligent document analysis platform...",
      "source_ref": {
        "document_id": "uuid",
        "chunk_id": "chunk-000",
        "section": "# Purpose",
        "evidence": "Build an intelligent document analysis platform"
      },
      "relations": [],
      "verified": true
    }
  ],
  "extraction_metadata": {
    "prompt_version": "extraction-v1",
    "model_id": "gemini/gemini-2.5-flash-preview-05-20",
    "temperature": 0.1,
    "element_count": 15,
    "relationship_count": 8,
    "verification_rate": 0.93,
    "extracted_at": "2026-07-24T15:30:00Z"
  }
}
```

**Error Responses:**
| Status | Condition |
|--------|-----------|
| 404 | Document not found (Req 9.6) |
| 409 | Analysis not yet completed (Req 9.5) |

---

## Key Technical Decisions

### Decision 1: LLM Model Configuration

**Choice:** Gemini 2.5 Flash (primary), Groq Llama 3.3 70B (light + fallback).

**Reasoning:** Gemini's 1M token context window accommodates full documents without segmentation in most cases. Groq provides fast inference for the lightweight type classification task. Automatic fallback from Gemini to Groq handles rate limits transparently (Req 1.3). Credential validation at startup prevents runtime surprises (Req 1.6).

```python
PRIMARY_MODEL = "gemini/gemini-2.5-flash-preview-05-20"
LIGHT_MODEL = "groq/llama-3.3-70b-versatile"
FALLBACK_MODEL = "groq/llama-3.3-70b-versatile"
```

### Decision 2: Prompt Versioning Strategy

**Choice:** Prompt templates as Python modules with explicit version constants.

**Reasoning:** Each prompt module exports a `VERSION` string and a `build(...)` function. The version is recorded in `ExtractionMetadata` alongside the model used, enabling full auditability (Req 2.2, 10.3). Previous versions are retained as separate modules (e.g., `extraction_v1.py`, `extraction_v2.py`) for comparison and rollback (Req 2.6).

### Decision 3: Document Segmentation

**Choice:** Single-request for most documents; segment at chunk boundaries for oversized ones.

**Reasoning:** With 10 MB max file size and Gemini's 1M token window, most documents fit in a single request. For edge cases, the system splits at IR chunk boundaries into overlapping segments and deduplicates merged results by element name + type (Req 5.7).

### Decision 4: Evidence Verification Algorithm

**Choice:** Deterministic text-matching with fuzzy fallback.

**Reasoning:** Verification must NOT call the LLM (Req 7.5). First attempts exact substring match after whitespace normalization. If that fails, falls back to fuzzy matching (80% similarity threshold) to handle minor formatting differences introduced during extraction. This is a pure function against the IR — no external dependencies.

```python
def verify_evidence(evidence: str, ir_chunks: list[ContentChunkModel]) -> bool:
    normalized_evidence = normalize_whitespace(evidence.strip())
    # 1. Exact match in referenced chunk
    # 2. Exact match in any chunk
    # 3. Fuzzy match (80% threshold) in any chunk
    return found
```

### Decision 5: Synchronous vs Asynchronous Processing

**Choice:** Synchronous for MVP; async-ready architecture.

**Reasoning:** Type inference (light model) is fast (<5s) and runs synchronously within the `/analyze` request. Extraction + verification runs synchronously within `/confirm-type` given Gemini's fast response times. The API already returns 202 and the client can poll status — moving to background tasks requires no API changes if latency becomes an issue.

### Decision 6: Failure and Partial Results Handling

**Choice:** Clean failure with cleanup on error; partial element retention on malformed LLM output.

**Reasoning:** Per Req 5.6, a complete parse failure halts extraction and marks the session as failed. Individual malformed elements within a parseable response are discarded with warnings. Per Req 8.4, any partial results persisted during processing are cleaned up on failure — no incomplete Knowledge Models are retrievable.

---

## Correctness Properties

These invariants must hold for the analysis engine to be considered correct:

### Property 1: Consent Gate

No document content is sent to an LLM provider unless the document has been ingested (status = ready) and analysis has been explicitly initiated via the API. The engine never proactively sends content.

**Validates: Requirements 9.1, 10.2**

### Property 2: Type Confirmation Gate

The extraction pipeline never runs without an explicitly confirmed document type. The system blocks at `awaiting_confirmation` until the user calls `/confirm-type`.

**Validates: Requirements 3.4, 4.1**

### Property 3: Evidence Grounding

Every element in the Knowledge Model has a `source_ref` with a non-empty `evidence` field. No element is persisted without an associated evidence claim. Verification marks whether that claim is grounded but does not remove ungrounded elements.

**Validates: Requirements 5.2, 5.4, 7.1, 7.3**

### Property 4: Relationship Integrity

No relationship references a `target_id` that does not exist in the same Knowledge Model. Dangling references are removed during post-processing before persistence.

**Validates: Requirements 6.5**

### Property 5: Session State Machine

The analysis session status follows a strict state machine: `inferring_type → awaiting_confirmation → extracting → verifying → completed`. No status can be skipped. The `failed` state is reachable from any non-terminal state.

**Validates: Requirements 8.2**

### Property 6: Clean Failure

When an analysis fails at any step, the session is marked as `failed` with an error_message. Any partial Knowledge Model data persisted during processing is cleaned up. No incomplete Knowledge Model is retrievable via the API.

**Validates: Requirements 8.4, 9.5**

### Property 7: Data Minimization

The LLM receives only IR text content (chunk text + structural context) and the system prompt. No user identity, session history, document_id, or metadata beyond the document content is included in prompts.

**Validates: Requirements 2.4, 10.2, 10.4**

### Property 8: Structural Consistency

Given identical inputs (same IR, same model configuration, same prompt version), the system produces structurally consistent Knowledge Models — equivalent elements, relationships, and evidence. The system reduces non-determinism through deterministic prompts, low temperature, schema-constrained generation, and output normalization.

**Validates: Requirements 10.1**

### Property 9: Fallback Transparency

When the primary model fails with a transient error and the fallback model succeeds, the `model_id` in ExtractionMetadata reflects the model that actually produced the result (the fallback), not the one that was attempted first.

**Validates: Requirements 1.3, 1.5, 10.3**

---

## Interaction Flow

```
1. Client calls POST /analyze with document_id
       │
       ├── [document not found] → 404
       ├── [document not ready] → 409
       ├── [analysis already exists] → 409
       │
       ▼
2. Create analysis session (status: inferring_type)
       │
       ▼
3. Call LLM (light model) for type inference
       │── Prompt: first ~2000 chars of IR text
       │── Model: Groq (Req 3.5)
       │
       ├── [LLM fails after fallback] → session failed
       │
       ▼
4. Parse type suggestion
       │── Confidence sufficient → set suggested_type
       │── Confidence low → suggested_type = "generic", document_type = unset (Req 3.3)
       │
       ├── Update session (status: awaiting_confirmation)
       │
       └── Return 202 to client

5. Client calls POST /confirm-type with document_type
       │
       ├── [invalid type] → 400 with valid types list (Req 4.5)
       ├── [wrong state] → 409
       │
       ▼
6. Record confirmed_type, update session (status: extracting)
       │
       ▼
7. Call LLM (primary model) for extraction
       │── Prompt: full IR text + confirmed type + taxonomy + relationship vocab
       │── Model: Gemini (Req 5.1)
       │
       ├── [complete parse failure] → session failed (Req 5.6)
       │
       ▼
8. Validate Knowledge Model against Pydantic schema
       │── Discard malformed elements with warnings (Req 5.6)
       │── Remove dangling relationship references (Req 6.5)
       │── Ensure "contradicts" relations are bidirectional (Req 6.4)
       │
       ├── Update session (status: verifying)
       │
       ▼
9. Evidence verification (deterministic, no LLM — Req 7.5)
       │── For each element: check source_ref.evidence against IR chunks
       │── Mark verified = true/false per element (Req 7.2, 7.3)
       │── Compute verification_rate (Req 7.4)
       │
       ▼
10. Persist Knowledge Model + metadata
       │── Update session (status: completed)
       │
       └── Return 202 to client

11. Client calls GET /knowledge-model
       │
       ├── [not completed] → 409 (Req 9.5)
       │
       └── Return 200 with full Knowledge Model (Req 9.4)
```

---

## Error Handling

| Error Source | Error Type | Behavior | Recovery |
|-------------|-----------|----------|----------|
| Invalid credentials (startup) | Authentication | Raise clear error at startup (Req 1.6) | Fix env variables |
| Invalid credentials (runtime) | Authentication | Fail immediately, no fallback (Req 1.3) | Fix env variables |
| Primary model rate-limited | Transient | Auto-fallback to secondary model (Req 1.3) | Automatic |
| Fallback also fails | Transient | Return error to caller; caller may retry (Req 1.7) | Retry or wait |
| LLM response unparseable (complete) | Extraction | Halt extraction, mark session failed (Req 5.6) | Retry analysis |
| Individual elements malformed | Extraction | Discard elements, retain valid ones (Req 5.6) | None needed |
| Dangling relationship references | Extraction | Remove references silently (Req 6.5) | None needed |
| Document not found | API | Return 404 (Req 9.2, 9.6) | Correct document_id |
| Document not ready | API | Return 409 (Req 9.1) | Wait for ingestion |
| Analysis already exists | API | Return 409 (Req 9.7) | Use existing analysis |
| Invalid type value | API | Return 400 with valid types (Req 4.5) | Correct type |
| Wrong session state | API | Return 409 (Req 4.4, 9.5) | Follow correct flow |

---

## Security Considerations

Aligned with ADR-005 (Privacy and External Processing):

- **Data minimization:** Only IR text content and system prompts are sent to LLM providers. No user metadata, account information, document identifiers, or usage history is included in prompts (Req 2.4, 10.2).
- **No user metadata persisted:** Analysis results store only document content derivatives and extraction metadata. No user identity is attached (Req 10.4).
- **Provider abstraction:** The LLM abstraction layer prevents accidental direct SDK usage. All communication is centralized and auditable (Req 1.1).
- **Credential management:** API keys are read from environment variables, validated at startup. Never logged or included in error messages (Req 1.6).
- **Input from LLM treated as untrusted:** All LLM output is validated against Pydantic schemas before persistence. Malformed output is discarded, not trusted (Req 5.6).

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| LLM Client | Fallback logic, credential validation, parameter tracking | Unit tests with mocked LiteLLM; verify fallback triggers on transient errors, fails on auth errors |
| Prompt Templates | Prompt construction, version identifiers, content boundaries | Unit tests verifying prompt includes taxonomy/vocabulary, excludes user metadata, embeds version |
| Type Inference | Classification parsing, low-confidence handling | Unit tests with mocked LLM responses; verify "generic" suggestion on low confidence |
| Extraction | Schema parsing, malformed element handling, deduplication | Unit tests with mocked LLM responses; verify valid elements retained, malformed discarded |
| Verification | Text matching, fuzzy matching, verification rate calculation | Unit tests with known IR chunks; boundary cases for exact vs. fuzzy vs. not found |
| Analysis Service | Pipeline orchestration, state transitions, failure cleanup | Unit tests with mocked dependencies; verify state machine, cleanup on failure |
| API Endpoints | HTTP contract, status codes, error formats | Integration tests via httpx AsyncClient; verify 202/400/404/409 responses |
| End-to-End | Full flow with mocked LLM | Integration tests: upload → analyze → confirm → poll → retrieve KM |

All integration tests use mocked LLM responses to avoid real API calls during CI.

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| LiteLLM | LLM provider abstraction | Project standard (D-05); handles multi-provider routing and fallback |
| FastAPI | HTTP framework | Project standard; existing backend framework |
| Pydantic v2 | Data validation and Knowledge Model schema | Project standard; validates LLM output before persistence |
| supabase-py | Database client for session persistence | Project standard; existing database layer |
| pytest + httpx | Testing | Project standard; async integration tests |

No additional dependencies beyond the project's established stack are introduced.

---

## File Structure

```
src/backend/
├── app/
│   ├── api/v1/
│   │   ├── documents.py          # Existing ingestion endpoints
│   │   └── analysis.py           # NEW: analyze, confirm-type, knowledge-model endpoints
│   ├── analysis/                  # NEW: Analysis engine module
│   │   ├── __init__.py
│   │   ├── service.py            # AnalysisService orchestrator
│   │   ├── llm_client.py         # LLM abstraction layer (Req 1)
│   │   ├── type_inference.py     # Document type inference (Req 3)
│   │   ├── extraction.py         # Knowledge Model extraction (Req 5, 6)
│   │   ├── verification.py       # Evidence verification (Req 7)
│   │   └── prompts/              # Versioned prompt templates (Req 2)
│   │       ├── __init__.py
│   │       ├── type_inference_v1.py
│   │       └── extraction_v1.py
│   ├── models/
│   │   ├── document.py           # Existing IR models
│   │   └── knowledge_model.py    # NEW: Knowledge Model Pydantic models
│   └── db/
│       └── migrations/
│           ├── 001_create_documents.sql
│           └── 002_create_analysis_sessions.sql  # NEW (Req 8)
└── tests/
    ├── unit/
    │   └── analysis/             # NEW
    │       ├── test_models.py
    │       ├── test_llm_client.py
    │       ├── test_type_inference.py
    │       ├── test_extraction.py
    │       ├── test_verification.py
    │       ├── test_service.py
    │       └── test_prompts.py
    └── integration/
        └── analysis/             # NEW
            └── test_analysis_flow.py
```

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: LLM Abstraction Layer | `llm_client.py`, LiteLLM config, fallback logic, credential validation at startup, caller retry transparency |
| Req 2: Prompt Template System | `prompts/` directory, version constants, build functions, content boundaries (no user metadata) |
| Req 3: Document Type Inference | `type_inference.py`, light model call, TypeSuggestion with unset type on low confidence |
| Req 4: Document Type Confirmation | `POST /confirm-type` endpoint, session state validation, 400 for invalid types |
| Req 5: Knowledge Model Extraction | `extraction.py`, KnowledgeModel Pydantic models, parse failure handling, segmentation for large docs |
| Req 6: Relationship Extraction | Extraction prompt vocabulary, Relation model, bidirectional contradicts, dangling reference removal |
| Req 7: Evidence Verification | `verification.py`, deterministic text matching, fuzzy fallback, verified flag, verification_rate |
| Req 8: Analysis Session Management | `analysis_sessions` table, state machine, JSONB persistence, failure cleanup |
| Req 9: Analysis API Endpoints | `api/v1/analysis.py`, three endpoints, 202/400/404/409 responses |
| Req 10: Reproducibility and Minimization | ExtractionMetadata, controlled parameters, schema-constrained generation, data minimization in prompts |
