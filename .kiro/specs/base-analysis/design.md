# Design — Base Analysis (Análisis Base)

## Overview

This document describes the technical design for the Base Analysis feature (C2). It covers the architecture, data models, API contracts, module structure, and key technical decisions required to implement the approved requirements.

The base analysis is the system's first response to a document upload. It produces a "document card" combining deterministic local processing (title, statistics, organization type, index detection) with a single short LLM call to the light model (summary and classification). The card gives users immediate value — understanding what a document is about and how it's organized — within 5 seconds. This is the foundation of the progressive analysis model (ADR-007), replacing the previous monolithic Knowledge Model extraction pipeline.

## Relevant Documentation

- #[[file:.kiro/specs/base-analysis/requirements.md]]
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-003-document-ingestion.md]]
- #[[file:src/backend/app/models/document.py]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/backend/app/ingestion/service.py]]

---

## Architecture

### System Context

```
┌──────────────┐     ┌────────────────────────────────────────────────────────┐
│   Frontend   │────▶│              Base Analysis Engine                        │
│  (Document   │◀────│  (local processing → LLM call → card persistence)       │
│   Card)      │     │                                                          │
└──────────────┘     └────────────────────────────────────────────────────────┘
                                      │                    ▲
                                      │                    │
                                      ▼                    │
                              ┌───────────────┐    ┌──────────────────┐
                              │  LLM Provider  │    │  Intermediate    │
                              │  (Groq light)  │    │  Representation  │
                              └───────────────┘    │  (Ingestion)     │
                                                   └──────────────────┘
```

### Internal Module Decomposition

The base analysis engine is organized into four internal modules:

1. **BaseAnalysisService** — Orchestrator that coordinates local analysis, LLM analysis, and persistence. Triggered automatically post-ingestion.
2. **LocalAnalyzer** — Deterministic processing of the IR: extracts title, computes statistics, detects organization type, detects existing index, assembles file metadata. No network calls.
3. **LLMAnalyzer** — Single LLM call to the light model for summary (2-3 lines) and classification. Handles timeout and failure gracefully.
4. **BaseAnalysisStorage** — Persistence layer for the DocumentCard (get, upsert, mark_outdated) using Supabase.

### Pipeline Flow

```
API: POST /api/v1/documents/upload (ingestion completes with status=ready)
       │
       ▼
BackgroundTask: BaseAnalysisService.analyze(document_id, ir)
       │
       ├── [card exists with status="completed" and same size_bytes] → return existing
       │
       ├── Step 1: LocalAnalyzer.analyze(ir)
       │       ├── _extract_title(ir)         → first heading or filename
       │       ├── _compute_statistics(ir)    → chunks, sections, levels, index
       │       ├── _detect_organization_type(ir) → numbered_articles | headed_sections | hierarchical_numbering | free_form
       │       └── _build_file_metadata(ir)   → size, format, language
       │       └── Returns: LocalAnalysisResult (always succeeds, <100ms)
       │
       ├── Step 2: LLMAnalyzer.analyze(title, chunks[:10], org_type)
       │       ├── Build prompt (title + org_type + first 2000 chars)
       │       ├── LLMClient.call(prompt, model_tier="light", temperature=0.1)
       │       ├── [timeout >10s] → return None
       │       ├── [LLM error] → return None
       │       ├── [invalid JSON] → return None
       │       └── Returns: LLMAnalysisResult | None
       │
       ├── Step 3: Build DocumentCard
       │       ├── [LLM succeeded] → status="completed", summary + classification set
       │       └── [LLM failed]    → status="partial", summary=null, classification=null
       │
       └── Step 4: BaseAnalysisStorage.upsert_card(card)
              └── Persist to document_cards table

ON RETRY (POST /api/v1/documents/{id}/card/retry-llm):
       ├── Load existing card
       ├── [status="completed"] → 409
       ├── [no card] → 404
       ├── Re-execute LLMAnalyzer.analyze()
       ├── Update card fields (summary, classification, model_id, prompt_version, status)
       └── Persist updated card
```

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `api/v1/card.py` | HTTP layer — GET card, POST retry-llm | REST endpoints | `BaseAnalysisService` |
| `BaseAnalysisService` | Orchestrates local + LLM + persistence | `analyze()`, `retry_llm()` | `LocalAnalyzer`, `LLMAnalyzer`, `BaseAnalysisStorage` |
| `LocalAnalyzer` | Deterministic structural analysis of IR | `analyze(ir) → LocalAnalysisResult` | IR (IntermediateRepresentation) |
| `LLMAnalyzer` | Single LLM call for summary + classification | `analyze(title, chunks, org_type) → LLMAnalysisResult \| None` | `LLMClient` |
| `BaseAnalysisStorage` | CRUD for DocumentCard in Supabase | `get_card()`, `upsert_card()`, `mark_outdated()` | Supabase client |
| `prompts.py` | Versioned prompt template | `PROMPT_TEMPLATE`, `PROMPT_VERSION` | — |

### Key Interfaces

```python
# --- Document Card Models (Req 4) ---

class OrganizationType(str, Enum):
    NUMBERED_ARTICLES = "numbered_articles"
    HEADED_SECTIONS = "headed_sections"
    HIERARCHICAL_NUMBERING = "hierarchical_numbering"
    FREE_FORM = "free_form"

class DocumentClassification(str, Enum):
    NORMATIVE = "normative"
    GUIDE = "guide"
    MANUAL = "manual"
    PROCEDURE = "procedure"
    TECHNICAL = "technical"
    NARRATIVE = "narrative"
    OTHER = "other"

class DocumentCardStatistics(BaseModel):
    total_chunks: int
    sections_detected: int
    hierarchy_levels: int
    has_existing_index: bool

class FileMetadata(BaseModel):
    size_bytes: int
    format: str
    language: str | None = None
    last_modified: datetime | None = None

class DocumentCard(BaseModel):
    id: str
    document_id: str
    title: str
    summary: str | None = None
    classification: DocumentClassification | None = None
    organization_type: OrganizationType
    statistics: DocumentCardStatistics
    file_metadata: FileMetadata
    status: Literal["completed", "failed_llm", "partial"]
    outdated: bool = False
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: datetime
    updated_at: datetime
```

```python
# --- Service Interfaces ---

@dataclass
class LocalAnalysisResult:
    title: str
    statistics: DocumentCardStatistics
    organization_type: OrganizationType
    file_metadata: FileMetadata

@dataclass
class LLMAnalysisResult:
    summary: str
    classification: DocumentClassification
    model_id: str
    prompt_version: str


class LocalAnalyzer:
    """Deterministic structural analysis of the IR. No network calls."""

    def analyze(self, ir: IntermediateRepresentation) -> LocalAnalysisResult:
        """Extract title, statistics, organization type, file metadata from IR.
        Always succeeds. Completes in <100ms for documents up to 10 MB.
        """
        ...

    def _extract_title(self, ir: IntermediateRepresentation) -> str:
        """First heading (by chunk order) from structural_context.section, or filename without extension."""
        for chunk in sorted(ir.chunks, key=lambda c: c.order):
            ctx = chunk.structural_context
            if ctx.get("section"):
                return ctx["section"]
        return ir.metadata.original_filename.rsplit(".", 1)[0]

    def _compute_statistics(self, ir: IntermediateRepresentation) -> DocumentCardStatistics: ...
    def _detect_organization_type(self, ir: IntermediateRepresentation) -> OrganizationType: ...
    def _build_file_metadata(self, ir: IntermediateRepresentation) -> FileMetadata: ...


class LLMAnalyzer:
    """Single LLM call for summary + classification. Returns None on any failure."""

    def __init__(self, llm_client: LLMClient) -> None: ...

    async def analyze(
        self, title: str, chunks: list[ContentChunkModel], organization_type: OrganizationType
    ) -> LLMAnalysisResult | None:
        """Call light model with 10s timeout. Returns None if LLM fails or JSON is invalid."""
        ...


class BaseAnalysisStorage:
    """Persistence for DocumentCard in Supabase."""

    def __init__(self, supabase_client) -> None: ...

    async def get_card(self, document_id: str) -> DocumentCard | None: ...
    async def upsert_card(self, card: DocumentCard) -> None: ...
    async def mark_outdated(self, document_id: str) -> None: ...


class BaseAnalysisService:
    """Orchestrates the full base analysis pipeline."""

    def __init__(self, local_analyzer: LocalAnalyzer, llm_analyzer: LLMAnalyzer, storage: BaseAnalysisStorage) -> None: ...

    async def analyze(self, document_id: str, ir: IntermediateRepresentation) -> DocumentCard:
        """Execute base analysis (local + LLM). Returns completed or partial card.
        Does not raise exceptions — failures result in partial cards.
        """
        ...

    async def retry_llm(self, document_id: str, ir: IntermediateRepresentation) -> DocumentCard:
        """Re-execute only the LLM phase for a partial card.
        Raises CardNotFoundError if no card exists.
        """
        ...
```

---

## Data Models

### DocumentCard (Pydantic v2)

The Pydantic models are defined above in the Interfaces section. Key design decisions:

- `DocumentCard` unifies completed, partial, and failed states via the `status` field.
- `summary` and `classification` are nullable — null when status is "partial" (LLM failed).
- `outdated` flag indicates the document changed since last analysis (Req 6).
- `model_id` and `prompt_version` track which LLM and prompt produced the summary/classification.
- `statistics` and `file_metadata` are stored as JSONB in PostgreSQL for flexibility.

### Database Schema

```sql
CREATE TABLE document_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) UNIQUE,
    title TEXT NOT NULL,
    summary TEXT,
    classification TEXT,
    organization_type TEXT NOT NULL,
    statistics JSONB NOT NULL,
    file_metadata JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'partial',
    outdated BOOLEAN NOT NULL DEFAULT false,
    model_id TEXT,
    prompt_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_document_cards_document_id ON document_cards(document_id);
```

One table, one index. No joins required for card retrieval.

---

## API Design

### GET /api/v1/documents/{document_id}/card

Retrieves the document card.

**Response (200) — Card exists:**
```json
{
  "id": "uuid",
  "documentId": "uuid",
  "title": "Reglamento de Propiedad Horizontal",
  "summary": "Este documento establece las normas de convivencia y administración para propiedades horizontales. Define responsabilidades de propietarios y administración.",
  "classification": "normative",
  "organizationType": "numbered_articles",
  "statistics": {
    "totalChunks": 45,
    "sectionsDetected": 12,
    "hierarchyLevels": 3,
    "hasExistingIndex": true
  },
  "fileMetadata": {
    "sizeBytes": 234500,
    "format": "pdf",
    "language": "es"
  },
  "status": "completed",
  "outdated": false,
  "modelId": "groq/llama-3.3-70b-versatile",
  "promptVersion": "base-analysis-v1",
  "createdAt": "2026-07-26T10:30:00Z",
  "updatedAt": "2026-07-26T10:30:04Z"
}
```

**Error Responses:**

| Status | Condition | Error Code |
|--------|-----------|------------|
| 404 | Document exists but no card yet | `card_not_found` |
| 404 | Document does not exist | `document_not_found` |

### POST /api/v1/documents/{document_id}/card/retry-llm

Re-executes only the LLM phase for a partial card.

**Response (200) — Retry successful:**
Returns updated DocumentCard with status="completed".

**Error Responses:**

| Status | Condition | Error Code |
|--------|-----------|------------|
| 404 | No card exists | `card_not_found` |
| 409 | Card already has status="completed" | `card_already_complete` |

---

## Key Technical Decisions

### Decision 1: Fire-and-Forget via BackgroundTasks

**Choice:** Trigger base analysis as a FastAPI BackgroundTask after successful ingestion, not inline in the ingestion pipeline.

**Reasoning:** The upload endpoint must return immediately with the document_id and status. The base analysis (up to 5 seconds with LLM) should not block the upload response. BackgroundTasks is the simplest mechanism for this in FastAPI without adding a task queue dependency.

### Decision 2: Polling from Frontend

**Choice:** The frontend polls GET /card every 1.5 seconds (max 10 attempts) to detect card availability, rather than using WebSocket or SSE.

**Reasoning:** The card typically appears within 2-5 seconds. Polling for a short window is simpler than maintaining a persistent connection for a one-time event. No additional infrastructure needed. Max polling window is 15 seconds.

### Decision 3: Partial Card as Graceful Degradation

**Choice:** When the LLM fails, persist a partial card with all local data (title, statistics, org type, metadata) and status="partial", rather than blocking or failing entirely.

**Reasoning:** Local processing data is valuable on its own — the user can see structure and statistics immediately. The LLM portion (summary + classification) can be retried independently. This ensures the user always gets value from the upload, even if the AI service is down.

### Decision 4: First 10 Chunks as LLM Context

**Choice:** Send the concatenated text of the first 10 IR chunks (truncated to 2000 characters) as context for the LLM call, rather than the full document.

**Reasoning:** The light model needs just enough context to produce a 2-3 line summary and classify the document. The first 10 chunks cover the introduction/preamble of most documents, which is sufficient for classification. This keeps the prompt short (~500 tokens) and ensures the LLM responds within the 10-second timeout.

### Decision 5: JSON Output from LLM

**Choice:** Require the LLM to output structured JSON (`{"summary": "...", "classification": "..."}`) rather than free-form text.

**Reasoning:** JSON is deterministically parseable. The prompt explicitly requests JSON-only output. If the response isn't valid JSON with the expected fields, it's treated as a failure (partial card). This avoids complex text extraction logic.

### Decision 6: Upsert Semantics for Card Persistence

**Choice:** Use upsert (insert or update by document_id) rather than separate insert and update operations.

**Reasoning:** Simplifies the retry flow — calling upsert with updated fields works whether it's the first save or a retry update. The UNIQUE constraint on document_id prevents duplicates.

### Decision 7: 10-Second LLM Timeout

**Choice:** Apply a 10-second timeout (`asyncio.wait_for`) to the LLM call specifically.

**Reasoning:** ADR-007 specifies the total base analysis should complete in <5 seconds under normal conditions, with a 10-second timeout for the LLM portion. If Groq doesn't respond within 10 seconds, it's better to save a partial card immediately than wait longer. The user can retry the LLM later.

---

## Correctness Properties

### Property 1: Local Processing Independence

*For any* document IR, the LocalAnalyzer SHALL produce a valid LocalAnalysisResult without any network calls, LLM calls, or external service dependencies. The result SHALL be deterministic for the same IR input.

**Validates: Requirements 2.6, 2.7**

### Property 2: Partial Card Completeness

*For any* base analysis execution where the LLM phase fails, the persisted DocumentCard SHALL have: a non-empty title, a valid organization_type, complete statistics (total_chunks, sections_detected, hierarchy_levels, has_existing_index), complete file_metadata (size_bytes, format), and status="partial".

**Validates: Requirements 5.2, 5.3**

### Property 3: Card Uniqueness

*For any* document_id, at most one DocumentCard record SHALL exist in the database. Concurrent or repeated analysis executions for the same document_id SHALL not create duplicate cards.

**Validates: Requirements 4.1, 4.3**

### Property 4: LLM Failure Non-Propagation

*For any* failure in the LLM phase (timeout, service error, invalid JSON, network error), the BaseAnalysisService SHALL NOT raise an exception to the caller. It SHALL persist a partial card and return it.

**Validates: Requirements 3.4, 1.4**

### Property 5: Idempotent Re-Analysis Guard

*For any* document with an existing completed card whose file metadata matches the current document, calling `analyze()` SHALL return the existing card without re-executing local or LLM processing.

**Validates: Requirements 1.3**

### Property 6: Data Minimization

*For any* prompt sent to the LLM during base analysis, the prompt content SHALL contain only: the detected title, the detected organization type, and a text sample from the document. No user identity, session history, account metadata, or document_id SHALL be present.

**Validates: Requirements 3.7**

### Property 7: Performance Bound

*For any* document up to 10 MB, the local processing phase SHALL complete in under 100 milliseconds. Under normal LLM conditions (response < 3 seconds), the total analysis SHALL complete in under 5 seconds.

**Validates: Requirements 2.7, 5.1**

---

## Interaction Flow

```
=== DOCUMENT UPLOAD → CARD AVAILABLE ===

1. Client calls POST /api/v1/documents/upload with file
       │
       ▼
2. IngestionService.ingest() processes document → status="ready"
       │
       ▼
3. Upload endpoint adds BackgroundTask: base_analysis_service.analyze(document_id, ir)
       │
       ├── Returns 200 to client immediately (document_id, status=ready)
       │
       ▼
4. [Background] BaseAnalysisService.analyze(document_id, ir)
       │── Check existing card → [completed + same size] → return existing
       │── LocalAnalyzer.analyze(ir) → LocalAnalysisResult (~<100ms)
       │── LLMAnalyzer.analyze(title, chunks[:10], org_type) → LLMAnalysisResult | None (~1-5s)
       │── Build DocumentCard (completed or partial)
       │── BaseAnalysisStorage.upsert_card(card)
       │
       ▼
5. Card available via GET /api/v1/documents/{document_id}/card


=== FRONTEND POLLING ===

1. Upload response received (document_id)
2. Display DocumentCardSkeleton (loading state)
3. Poll GET /card every 1.5s
       ├── [404] → continue polling (max 10 attempts)
       ├── [200 + status="completed"] → display full card
       ├── [200 + status="partial"] → display local data + retry button
       └── [10 attempts exhausted] → show "taking longer" message + manual retry


=== LLM RETRY ===

1. User clicks "Reintentar análisis" on partial card
2. Client calls POST /retry-llm
       ├── [409] → card already complete (shouldn't happen in normal flow)
       ├── [404] → error
       └── [200] → update card display with summary + classification
```

---

## Error Handling

| Error Source | Error Type | HTTP Status | Behavior | Recovery |
|-------------|-----------|-------------|----------|----------|
| LLM timeout (>10s) | Transient | — | Save partial card | User retries via button |
| LLM rate limit | Transient | — | Save partial card | User retries later |
| LLM service error | Transient | — | Save partial card | User retries via button |
| LLM invalid JSON response | Parse | — | Save partial card | User retries via button |
| LLM authentication error | Config | — | Save partial card | Admin fixes API key |
| Document not found (GET) | Prerequisite | 404 | Return error | Correct document_id |
| Card not found (GET) | Timing | 404 | Return error | Retry later (polling) |
| Card already complete (retry) | Logic | 409 | Return error | No action needed |
| Background task crash | Internal | — | Document stays "ready", no card | Manual re-upload |
| Supabase unavailable | Infrastructure | 500 | Analysis fails silently | Retry later |

---

## Security Considerations

Aligned with ADR-005 (Privacy and External Processing):

- **Data minimization:** Only document text (first 2000 chars), detected title, and organization type are sent to the LLM. No user identity, document_id, session history, or account metadata is included in prompts (Req 3.7).
- **Reuses LLM abstraction:** All LLM communication goes through the existing `LLMClient`, maintaining centralized credential management.
- **LLM output treated as untrusted:** The LLM response is parsed as JSON and validated. Invalid output is treated as a failure — no partial or malformed data reaches the user.
- **No sensitive data in card:** The DocumentCard contains only structural metadata and a short summary. It does not store the full document text.
- **Consent already granted:** The base analysis runs within the consent scope of the document upload (ADR-005). No additional consent prompt is needed.

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| LocalAnalyzer | Title extraction, statistics, org type detection, index detection | Unit tests with synthetic IRs for each org type and edge cases |
| LLMAnalyzer | Prompt construction, timeout handling, JSON parsing, failure paths | Unit tests with mocked LLMClient (success, timeout, invalid JSON) |
| BaseAnalysisStorage | Get, upsert, mark_outdated | Unit tests with mocked Supabase client |
| BaseAnalysisService | Orchestration, idempotency, partial card, retry flow | Unit tests with mocked dependencies |
| API Endpoints | HTTP contract, status codes, error responses | Integration tests via httpx TestClient |
| End-to-End | Upload → card available | Integration test: upload → poll → receive card |

**Property-Based Testing (Hypothesis):**

- Property 1: Local Processing Independence — generate random IRs, verify no exceptions and valid output
- Property 2: Partial Card Completeness — mock LLM failure, verify all local fields present
- Property 3: Card Uniqueness — concurrent analyze calls, verify single card
- Property 5: Idempotent Re-Analysis Guard — call analyze twice, verify single execution

All tests use mocked LLM responses to avoid real API calls during CI.

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| LiteLLM | LLM provider abstraction (via existing LLMClient) | Project standard; light model call |
| FastAPI | HTTP framework + BackgroundTasks | Project standard; async background execution |
| Pydantic v2 | Data validation for DocumentCard and LLM output | Project standard |
| supabase-py | Database client for card persistence | Project standard |
| pytest + httpx | Testing | Project standard |
| Hypothesis | Property-based testing | Already used in the project |

No additional dependencies beyond the project's established stack.

---

## File Structure

```
src/backend/
├── app/
│   ├── api/v1/
│   │   ├── documents.py              # Existing ingestion endpoints (modified: add BackgroundTask)
│   │   └── card.py                   # NEW: GET /card, POST /retry-llm
│   ├── analysis/
│   │   ├── base_analysis/            # NEW: Base analysis module
│   │   │   ├── __init__.py
│   │   │   ├── service.py            # BaseAnalysisService orchestrator
│   │   │   ├── local_analyzer.py     # LocalAnalyzer — deterministic IR processing
│   │   │   ├── llm_analyzer.py       # LLMAnalyzer — light model call
│   │   │   ├── prompts.py            # PROMPT_TEMPLATE + PROMPT_VERSION
│   │   │   └── storage.py            # BaseAnalysisStorage (Supabase)
│   │   ├── llm_client.py             # Existing (reused)
│   │   └── ...                        # Existing modules
│   └── models/
│       ├── document.py                # Existing IR models
│       └── document_card.py           # NEW: DocumentCard, enums, sub-models
└── tests/
    ├── unit/
    │   └── analysis/
    │       └── base_analysis/         # NEW
    │           ├── test_local_analyzer.py
    │           ├── test_llm_analyzer.py
    │           ├── test_storage.py
    │           ├── test_service.py
    │           └── test_card_models.py
    └── integration/
        └── analysis/
            └── test_base_analysis_flow.py  # NEW: upload → card available

src/frontend/
├── src/
│   ├── api/
│   │   └── documentCard.ts           # NEW: fetchCard, retryLlm
│   ├── store/
│   │   └── documentCardStore.ts      # NEW: Zustand store
│   ├── types/
│   │   └── documentCard.ts           # NEW: TypeScript interfaces
│   └── components/
│       └── document-card/            # NEW
│           ├── DocumentCardView.tsx   # Main card display
│           └── DocumentCardSkeleton.tsx  # Loading state

SQL migration:
└── supabase/migrations/
    └── XXX_create_document_cards.sql  # NEW: table + index
```

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Automatic Trigger | BackgroundTask in upload endpoint, `BaseAnalysisService.analyze()`, idempotency check |
| Req 2: Local Processing | `LocalAnalyzer` with `_extract_title`, `_compute_statistics`, `_detect_organization_type`, `_build_file_metadata`; no network calls; <100ms |
| Req 3: LLM Processing | `LLMAnalyzer` with `LLMClient.call(model_tier="light")`, 10s timeout, JSON parsing, PROMPT_VERSION, data minimization |
| Req 4: Document Card Persistence | `DocumentCard` Pydantic model, `document_cards` SQL table, `BaseAnalysisStorage` with upsert semantics, UNIQUE on document_id |
| Req 5: Performance | BackgroundTask (non-blocking), <100ms local, 10s LLM timeout, partial card on failure |
| Req 6: Change Detection | `outdated` field on DocumentCard, `BaseAnalysisStorage.mark_outdated()`, size_bytes comparison |
| Req 7: API Endpoints | `api/v1/card.py` with GET (200/404) and POST retry-llm (200/404/409), error codes |
| Req 8: Frontend Display | `documentCardStore.ts` (Zustand), `DocumentCardView.tsx`, `DocumentCardSkeleton.tsx`, polling logic, retry button, outdated indicator, accessibility |
