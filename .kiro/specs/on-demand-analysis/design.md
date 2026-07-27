# Design — On-Demand Analysis (Análisis Bajo Demanda)

## Overview

This document describes the technical design for the On-Demand Analysis feature (C3). It covers the architecture, data models, API contracts, prompt strategy, module structure, and key technical decisions for implementing four document-level analyses that the user triggers individually after seeing the base analysis card.

Each analysis type sends the full document IR to the primary LLM (Gemini 2.5 Flash) in a single call, waits for the response synchronously, and returns the structured result. This approach maximizes coherence (the LLM sees the whole document), minimizes complexity (no polling, no batching), and delivers results in 5-15 seconds.

## Relevant Documentation

- #[[file:.kiro/specs/on-demand-analysis/requirements.md]]
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:.kiro/specs/base-analysis/design.md]]
- #[[file:.kiro/specs/user-preferences/design.md]]
- #[[file:.kiro/steering/language-rules.md]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/backend/app/models/document.py]]
- #[[file:src/backend/app/models/document_card.py]]

---

## Architecture

### System Context

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Browser                                       │
│                                                                            │
│  ┌────────────┐   ┌──────────────────────────────────────────────────┐   │
│  │  Sidebar   │   │  Main Content                                     │   │
│  │ (prefs)    │   │                                                    │   │
│  └────────────┘   │  ┌────────────────────────────────┐               │   │
│                    │  │  Document Card                  │               │   │
│                    │  └────────────────────────────────┘               │   │
│                    │  ┌────────────────────────────────┐               │   │
│                    │  │  Options Panel                  │               │   │
│                    │  │  [Build Index] [Relations]      │               │   │
│                    │  │  [Questions]   [Conclusions]    │               │   │
│                    │  └────────────────────────────────┘               │   │
│                    │  ┌────────────────────────────────┐               │   │
│                    │  │  Analysis Results Display       │               │   │
│                    │  └────────────────────────────────┘               │   │
│                    └──────────────────────────────────────────────────┘   │
│                                                                            │
│  Zustand: useAnalysisStore                                                │
│    ├── statuses: Record<AnalysisType, AnalysisStatus>                     │
│    └── results: Record<AnalysisType, AnalysisResult | null>               │
└──────────────────────────────────────────────────────────────────────────┘
                         │
                         │  POST /analyses/{type} (sync, waits 5-15s)
                         │  GET /analyses (status summary)
                         │  GET /analyses/{type} (stored result)
                         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        Backend (FastAPI)                                    │
│                                                                            │
│  api/v1/analyses.py                                                        │
│    ├── POST: check stored → if fresh, return → else call LLM → persist    │
│    ├── GET all: return status summary                                      │
│    └── GET one: return stored result                                       │
│                                                                            │
│  OnDemandAnalysisService                                                   │
│    ├── execute(document_id, analysis_type, ir, preferences)                │
│    ├── get_result(document_id, analysis_type)                              │
│    └── get_all_statuses(document_id)                                       │
│                                                                            │
│  Analyzers (one per type):                                                 │
│    ├── IndexAnalyzer.analyze(ir, language) → StructureTree                 │
│    ├── RelationsAnalyzer.analyze(ir, language, index?) → list[Relation]            │
│    ├── QuestionsAnalyzer.analyze(ir, language) → QuestionsCascade          │
│    └── ConclusionsAnalyzer.analyze(ir, lang, doc_lang) → list[Conclusion] │
│                                                                            │
│  OnDemandAnalysisStorage                                                   │
│    ├── get_result(document_id, type) → AnalysisRecord | None               │
│    ├── save_result(record) → None                                          │
│    └── mark_all_outdated(document_id) → None                               │
│                                                                            │
│  LLMClient.call(prompt, model_tier="primary", ...)                         │
└──────────────────────────────────────────────────────────────────────────┘
```

### Internal Module Decomposition

1. **OnDemandAnalysisService** — Orchestrator that coordinates execution, idempotency checks, and persistence for all four analysis types.
2. **IndexAnalyzer** — Builds the structure tree from the full IR via a single LLM call.
3. **RelationsAnalyzer** — Identifies section relationships via a single LLM call.
4. **QuestionsAnalyzer** — Generates the cascade of questions via a single LLM call.
5. **ConclusionsAnalyzer** — Produces structural observations via a single LLM call.
6. **OnDemandAnalysisStorage** — Persistence layer for analysis results in Supabase.
7. **Prompt templates** — One versioned prompt per analysis type.

### Execution Flow (same for all four types)

```
Client: POST /api/v1/documents/{id}/analyses/{type}
       │
       ▼
Endpoint: get_request_preferences(request) → prefs
       │
       ├── Storage: get_result(document_id, type)
       │     ├── [exists + completed + not outdated] → return 200 stored result
       │     └── [not exists OR outdated OR failed]  → continue to LLM
       │
       ├── Storage: get IR from ingestion storage
       │     └── [no IR] → return 409 "document_not_ready"
       │
       ├── Analyzer: analyze(ir, language, model_override, auto_fallback)
       │     ├── Build prompt with full IR text + instructions
       │     ├── LLMClient.call(prompt, model_tier="primary", ...)
       │     ├── Parse JSON response into typed result
       │     └── [failure] → raise → endpoint returns 502
       │
       ├── Storage: save_result(record)
       │
       └── Return 200 with full result
```

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `api/v1/analyses.py` | HTTP layer — trigger, get status, get result | REST endpoints | `OnDemandAnalysisService`, `RequestPreferences` |
| `OnDemandAnalysisService` | Orchestrates idempotency + analyzer dispatch + persistence | `execute()`, `get_result()`, `get_all_statuses()` | Analyzers, Storage, IngestionStorage |
| `IndexAnalyzer` | Build structure tree from IR | `analyze(ir, ...) → IndexResult` | `LLMClient` |
| `RelationsAnalyzer` | Identify section relationships | `analyze(ir, ...) → RelationsResult` | `LLMClient`, `IndexResult` (optional) |
| `QuestionsAnalyzer` | Generate question cascade | `analyze(ir, ...) → QuestionsResult` | `LLMClient` |
| `ConclusionsAnalyzer` | Produce structural observations | `analyze(ir, ...) → ConclusionsResult` | `LLMClient` |
| `OnDemandAnalysisStorage` | CRUD for analysis results in Supabase | `get_result()`, `save_result()`, `mark_all_outdated()` | Supabase client |
| `prompts/` | Versioned prompt templates per type | `PROMPT_*` constants | — |

### Key Interfaces

```python
# --- Analysis Types ---

class AnalysisType(str, Enum):
    BUILD_INDEX = "build_index"
    SECTION_RELATIONS = "section_relations"
    QUESTIONS_ANSWERED = "questions_answered"
    CONCLUSIONS = "conclusions"


class AnalysisStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OUTDATED = "outdated"
    FAILED = "failed"


# --- Source Reference (shared across all results) ---

class SourceRef(BaseModel):
    chunk_ids: list[str]
    text_excerpt: str  # max 500 chars
    section: str | None = None


# --- Build Index Result ---

class StructureNode(BaseModel):
    id: str
    title: str
    level: int  # 1-6
    role: str | None  # defines, classifies, establishes, regulates, recommends, lists, restricts, describes
    question_answered: str | None  # cascade question this section answers
    source_ref: SourceRef | None
    children: list["StructureNode"] = []

class IndexResult(BaseModel):
    tree: list[StructureNode]  # top-level nodes


# --- Section Relations Result ---

class SectionRelation(BaseModel):
    source_section: str  # title or node id
    target_section: str
    type: str  # constrains, depends_on, complements, contradicts
    description: str  # in ui_language
    source_ref: SourceRef | None

class RelationsResult(BaseModel):
    relations: list[SectionRelation]


# --- Questions Answered Result ---

class AnsweredQuestion(BaseModel):
    question: str  # in ui_language
    level: str  # "document" or "section"
    section_title: str | None  # which section answers it (None for document-level)
    source_ref: SourceRef | None

class QuestionsResult(BaseModel):
    document_questions: list[AnsweredQuestion]  # 3-5 global purpose questions
    section_questions: list[AnsweredQuestion]   # 1-2 per major section


# --- Conclusions Result ---

class Observation(BaseModel):
    category: str  # coherence, reordering, duplication, orphan, missing
    description: str  # in ui_language
    suggestion: str  # structural suggestion in document_language
    section_ref: str | None  # which section(s) it refers to
    source_ref: SourceRef | None

class ConclusionsResult(BaseModel):
    observations: list[Observation]  # 3-15 items


# --- Persisted Record ---

class AnalysisRecord(BaseModel):
    id: str  # UUID
    document_id: str
    analysis_type: AnalysisType
    status: AnalysisStatus
    result: dict | None  # JSON-serialized result (IndexResult, RelationsResult, etc.)
    model_id: str | None
    prompt_version: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

```typescript
// --- Frontend Types ---

type AnalysisType = 'build_index' | 'section_relations' | 'questions_answered' | 'conclusions';
type AnalysisStatus = 'not_started' | 'in_progress' | 'completed' | 'outdated' | 'failed';

interface SourceRef {
  chunk_ids: string[];
  text_excerpt: string;
  section: string | null;
}

interface StructureNode {
  id: string;
  title: string;
  level: number;
  role: string | null;
  question_answered: string | null;
  source_ref: SourceRef | null;
  children: StructureNode[];
}

interface SectionRelation {
  source_section: string;
  target_section: string;
  type: 'constrains' | 'depends_on' | 'complements' | 'contradicts';
  description: string;
  source_ref: SourceRef | null;
}

interface AnsweredQuestion {
  question: string;
  level: 'document' | 'section';
  section_title: string | null;
  source_ref: SourceRef | null;
}

interface Observation {
  category: 'coherence' | 'reordering' | 'duplication' | 'orphan' | 'missing';
  description: string;
  suggestion: string;
  section_ref: string | null;
  source_ref: SourceRef | null;
}

interface AnalysisStatusSummary {
  build_index: { status: AnalysisStatus; updated_at: string | null };
  section_relations: { status: AnalysisStatus; updated_at: string | null };
  questions_answered: { status: AnalysisStatus; updated_at: string | null };
  conclusions: { status: AnalysisStatus; updated_at: string | null };
}

// Store
interface AnalysisStore {
  statuses: AnalysisStatusSummary | null;
  results: Partial<Record<AnalysisType, unknown>>;
  activeAnalysis: AnalysisType | null;  // which one is in_progress
  error: string | null;

  fetchStatuses: (documentId: string) => Promise<void>;
  triggerAnalysis: (documentId: string, type: AnalysisType) => Promise<void>;
  fetchResult: (documentId: string, type: AnalysisType) => Promise<void>;
  reset: () => void;
}
```

---

## Data Models

### Database Schema

```sql
-- Migration: 005_create_analysis_results
-- One row per (document_id, analysis_type) combination

CREATE TABLE analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id),
    analysis_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    result JSONB,
    model_id TEXT,
    prompt_version TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(document_id, analysis_type)
);

CREATE INDEX idx_analysis_results_document_id ON analysis_results(document_id);
```

Key design decisions:
- `result` is JSONB — each analysis type stores its own structure (tree, relations list, questions, observations).
- UNIQUE constraint on `(document_id, analysis_type)` ensures one result per type per document.
- `status` tracks lifecycle without needing a separate status table.
- No FK to `document_cards` — analyses can exist independently of the card.

---

## API Design

### POST /api/v1/documents/{document_id}/analyses/{analysis_type}

Triggers an analysis (or returns cached result).

**Request:**
- Path params: `document_id` (UUID), `analysis_type` (build_index | section_relations | questions_answered | conclusions)
- Headers: `Accept-Language`, `X-Model-Preference`, `X-Auto-Fallback`
- No request body.

**Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Analysis completed (fresh or cached) | Full typed result + metadata |
| 404 | Document not found | `{ error: "document_not_found" }` |
| 409 | IR not available | `{ error: "document_not_ready" }` |
| 502 | LLM call failed | `{ error: "analysis_failed", message: "..." }` |

**Success response body (200):**
```json
{
  "analysis_type": "build_index",
  "status": "completed",
  "result": { /* IndexResult | RelationsResult | QuestionsResult | ConclusionsResult */ },
  "model_id": "gemini/gemini-2.5-flash",
  "prompt_version": "build-index-v1",
  "created_at": "2026-07-26T15:00:00Z",
  "updated_at": "2026-07-26T15:00:12Z"
}
```

### GET /api/v1/documents/{document_id}/analyses

Returns status summary for all analysis types.

**Response (200):**
```json
{
  "build_index": { "status": "completed", "updated_at": "2026-07-26T15:00:12Z" },
  "section_relations": { "status": "not_started", "updated_at": null },
  "questions_answered": { "status": "not_started", "updated_at": null },
  "conclusions": { "status": "not_started", "updated_at": null }
}
```

### GET /api/v1/documents/{document_id}/analyses/{analysis_type}

Returns the stored result for a specific analysis type.

**Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Result exists (completed or outdated) | Full result + metadata |
| 200 | Not yet executed | `{ "analysis_type": "...", "status": "not_started", "result": null }` |
| 404 | Document not found | `{ error: "document_not_found" }` |

---

## Prompt Strategy

### Approach: Single Call with Full Document

Each analysis sends the complete document text (all IR chunks concatenated) to Gemini 2.5 Flash. This is viable because:
- Max document size is 10 MB ≈ ~3M characters ≈ ~750K tokens
- Gemini 2.5 Flash supports 1M token context window
- A single call provides maximum coherence (LLM sees all relationships, all sections)
- Eliminates batching, merging, and partial result complexity

### Prompt Structure (all four types)

```
Respond in {response_language}.

{type-specific instructions}

--- DOCUMENT CONTENT ---
{full concatenated IR text with section markers}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{json_schema}
```

### Per-Type Prompt Details

**Build Index:**
- Instruction: Analyze the document structure and produce a hierarchical tree of sections.
- For each node: identify title, hierarchy level, functional role, and the question this section answers.
- The question_answered follows a cascade: top-level = document purpose, deeper = section objective.
- Prompt version: `build-index-v1`

**Section Relations:**
- Instruction: Identify significant relationships between document sections.
- Focus on: explicit references, implicit dependencies, complementary content, contradictions.
- Exclude trivial connections (sequential order is not a relationship).
- Prompt version: `section-relations-v1`

**Questions Answered:**
- Instruction: Identify what questions this document answers, organized in a cascade.
- Document-level (3-5): what the whole document explains/addresses.
- Section-level (1-2 per major section): what each section contributes.
- Questions must be specific and actionable, not generic.
- Prompt version: `questions-answered-v1`

**Conclusions & Recommendations:**
- Instruction: Analyze the document's structural coherence and produce observations.
- Categories: coherence (purpose mixing), reordering, duplication, orphan sections, missing elements.
- `description` in {response_language}, `suggestion` in {document_language}.
- Suggestions are STRUCTURAL only (move, split, merge, add section) — NOT content text.
- Prompt version: `conclusions-v1`

### Text Preparation

The IR is serialized for the prompt as:

```
[Section: {structural_context.section or "Untitled"}] (chunk {order})
{text}

[Section: ...] (chunk {order})
{text}
...
```

This preserves section boundaries and ordering while being token-efficient.

---

## Key Technical Decisions

### Decision 1: Synchronous Execution (No Polling)

**Choice:** The POST endpoint awaits the LLM response and returns the result directly (5-15 seconds). No background task, no polling loop.

**Reasoning:** Each analysis is a single LLM call. The response time (5-15s) is within acceptable HTTP timeout ranges. Synchronous execution eliminates: polling infrastructure, in_progress database states that can get stuck, race conditions on concurrent triggers, and cleanup for orphaned tasks. The frontend shows a loading state optimistically while waiting.

**Tradeoff:** The HTTP connection stays open for 5-15 seconds. This is acceptable because the user explicitly triggered the analysis and expects to wait.

### Decision 2: Full Document in One Prompt

**Choice:** Send the entire IR (all chunks concatenated) as context in a single LLM call, instead of chunking or iterating per section.

**Reasoning:** Gemini's 1M token context window accommodates any document within the 10 MB limit. One call means: the LLM sees all relationships and context, results are coherent across the whole document, no need for batching or merging partial results, and simpler error handling. Performance is also better (one 10s call vs. many 3s calls).

### Decision 3: JSONB Storage for Heterogeneous Results

**Choice:** Store all analysis results in a single `analysis_results` table with a JSONB `result` column, rather than separate tables per type.

**Reasoning:** Four analysis types with different result schemas would require four tables. A single table with JSONB gives: uniform status queries across types, simple mark_all_outdated, and easy addition of new analysis types in the future without migrations. The tradeoff (no column-level querying on result fields) is acceptable because results are always read in full.

### Decision 4: Idempotency by Document + Type + Outdated Check

**Choice:** Before calling the LLM, check if a completed, non-outdated result exists. If yes, return it immediately.

**Reasoning:** LLM calls are expensive (time and API cost). The same analysis on an unchanged document produces equivalent results. The idempotency check (one DB query) is O(1) and avoids redundant work.

### Decision 5: Outdated Propagation on Re-Upload

**Choice:** When a document is re-uploaded and the card is marked outdated, all analysis_results for that document are also marked outdated. They remain viewable but the user is prompted to re-analyze.

**Reasoning:** Analysis results depend on the document content. If the document changed, results may be stale. Marking as outdated (not deleting) preserves the previous insights while signaling they need refresh.

### Decision 6: Timeout of 30 Seconds per Analysis

**Choice:** Apply a 30-second `asyncio.wait_for` timeout on each LLM call (vs. 10s for base analysis).

**Reasoning:** On-demand analyses process the full document (potentially 100K+ tokens of context) which takes longer than the base analysis (2000 chars). 30 seconds provides margin for large documents while still failing fast enough to not leave the user hanging indefinitely. The user chose to wait.

---

## Correctness Properties

### Property 1: Idempotent Execution

*For any* document that has not changed (not outdated), triggering the same analysis type multiple times SHALL return the identical stored result without making additional LLM calls.

**Validates: Requirements 6.5**

### Property 2: Complete Source Traceability

*For any* result element (tree node, relation, question, observation) that includes a non-null source_ref, THE referenced chunk_ids SHALL correspond to actual chunks in the document's IR.

**Validates: Requirements 9.3**

### Property 3: Classification-Based Availability

*For any* document classified as "narrative", THE options panel SHALL NOT present "Build Index" or "Section Relations" as triggerable options. Attempting to call these via API for a narrative document SHALL still work (no hard block on backend) but the UI SHALL NOT expose them.

**Validates: Requirements 1.3, 1.4**

### Property 4: Cascade Question Hierarchy

*For any* "Questions Answered" result, document-level questions SHALL be broader in scope than section-level questions. No section-level question SHALL be more general than a document-level question.

**Validates: Requirements 4.2, 4.3, 4.4**

### Property 5: Structural-Only Suggestions

*For any* observation in "Conclusions & Recommendations", the `suggestion` field SHALL describe a structural change (move, split, merge, add, remove section) and SHALL NOT prescribe what text content should say.

**Validates: Requirements 5.4**

### Property 6: Language Rule Compliance

*For any* analysis result: `description` and `question` fields SHALL be in `ui_language`; `suggestion` fields in Conclusions SHALL be in `document_language`; `text_excerpt` in source_ref SHALL be in the document's original language (unchanged).

**Validates: Requirements 4.5, 5.4, 5.5****; Language rules steering**

---

## Interaction Flow

```
=== USER TRIGGERS "BUILD INDEX" ===

1. Document card displayed (status=completed, classification=normative)
2. Options Panel shows all 4 options with status "not_started"
3. User clicks "Build Index"
       │
       ▼
4. Frontend: useAnalysisStore.triggerAnalysis(documentId, 'build_index')
       ├── Sets activeAnalysis = 'build_index' (shows spinner on button)
       ├── Calls POST /analyses/build_index
       │
       ▼
5. Backend: check storage → no existing result
       ├── Load IR from ingestion storage
       ├── Build prompt with full document text
       ├── LLMClient.call(prompt, model_tier="primary") — waits ~10s
       ├── Parse JSON → IndexResult
       ├── Save to analysis_results table
       │
       ▼
6. Response: 200 with IndexResult
       │
       ▼
7. Frontend: store result, update status to "completed"
       └── Display structure tree in results area


=== USER VIEWS ALREADY-COMPLETED ANALYSIS ===

1. Options Panel shows "Build Index" as "completed"
2. User clicks to view
       │
       ▼
3. Frontend: fetchResult(documentId, 'build_index')
       ├── Calls GET /analyses/build_index
       │
       ▼
4. Backend: return stored result (no LLM call)
       │
       ▼
5. Frontend: display tree


=== DOCUMENT RE-UPLOADED (OUTDATED) ===

1. User re-uploads document (different size_bytes)
2. Base analysis marks card as outdated
3. Backend: mark_all_outdated(document_id) on analysis_results
4. Frontend: Options Panel shows analyses as "outdated" with warning
5. User clicks "Re-analyze" on Build Index
       │
       ▼
6. POST /analyses/build_index → executes fresh (ignores stored outdated result)
       └── Stores new result, clears outdated flag
```

---

## Error Handling

| Error Source | Condition | HTTP Status | Behavior | Recovery |
|-------------|-----------|-------------|----------|----------|
| LLM timeout (>30s) | Model overloaded | 502 | Return error, no result saved | User retries |
| LLM rate limit | Quota exceeded | 502 | Return error with message | User waits and retries |
| LLM invalid JSON | Model produced unparseable output | 502 | Return error, log raw response | User retries (may succeed with different model) |
| LLM authentication | Bad API key | 502 | Return error | Admin fixes key |
| Document not found | Invalid document_id | 404 | Return error | Correct ID |
| IR not available | Document processing incomplete | 409 | Return error | Wait for ingestion |
| Analysis type invalid | Typo in URL | 422 | Validation error | Fix URL |
| Model override unknown | Invalid model string | 502 | LiteLLM error → fallback or error | Change model preference |

---

## Security Considerations

- **Data minimization:** The full document text is sent to the LLM, but no user identity, session history, or account metadata is included. Only document content and prompt instructions.
- **Consent scope:** On-demand analyses are within the consent granted during upload (ADR-005). The user already agreed to external processing.
- **LLM output as untrusted:** All JSON responses are parsed and validated against expected schemas. Invalid fields are rejected.
- **No sensitive data in results:** Analysis results contain structural metadata and text excerpts — no new information beyond what's in the document itself.
- **source_ref validation:** The system only returns text excerpts that exist in the stored IR. Hallucinated references are detectable (chunk_id validation).

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| IndexAnalyzer | Prompt construction, JSON parsing, tree structure validation | Unit tests with mocked LLMClient |
| RelationsAnalyzer | Prompt construction, relation parsing, type validation | Unit tests with mocked LLMClient |
| QuestionsAnalyzer | Prompt construction, cascade structure, level validation | Unit tests with mocked LLMClient |
| ConclusionsAnalyzer | Prompt construction, category validation, language split | Unit tests with mocked LLMClient |
| OnDemandAnalysisService | Idempotency, outdated handling, error propagation | Unit tests with mocked storage + analyzers |
| OnDemandAnalysisStorage | Get, save, mark_outdated | Unit tests with mocked Supabase |
| API Endpoints | HTTP contract, status codes, preference headers | Integration tests via httpx TestClient |
| Frontend Store | Status management, trigger flow, error handling | Unit tests with mocked fetch |
| Options Panel | Renders correct options per classification, status indicators | Component tests with Testing Library |
| Results Display | Tree rendering, relation list, questions cascade, observations | Component tests with Testing Library |

---

## File Structure

```
src/backend/
├── app/
│   ├── api/v1/
│   │   └── analyses.py                    # NEW: POST trigger, GET status, GET result
│   ├── analysis/
│   │   └── on_demand/                     # NEW: On-demand analysis module
│   │       ├── __init__.py
│   │       ├── service.py                 # OnDemandAnalysisService orchestrator
│   │       ├── index_analyzer.py          # Build Index analyzer
│   │       ├── relations_analyzer.py      # Section Relations analyzer
│   │       ├── questions_analyzer.py      # Questions Answered analyzer
│   │       ├── conclusions_analyzer.py    # Conclusions analyzer
│   │       ├── storage.py                 # OnDemandAnalysisStorage (Supabase)
│   │       ├── models.py                  # Result Pydantic models
│   │       └── prompts/                   # Versioned prompt templates
│   │           ├── __init__.py
│   │           ├── build_index.py
│   │           ├── section_relations.py
│   │           ├── questions_answered.py
│   │           └── conclusions.py
│   ├── middleware/
│   │   └── preferences.py                # EXISTING: RequestPreferences
│   └── db/migrations/
│       └── 005_create_analysis_results.sql  # NEW
├── tests/
│   ├── unit/analysis/on_demand/           # NEW
│   │   ├── test_index_analyzer.py
│   │   ├── test_relations_analyzer.py
│   │   ├── test_questions_analyzer.py
│   │   ├── test_conclusions_analyzer.py
│   │   ├── test_service.py
│   │   └── test_storage.py
│   └── integration/analysis/
│       └── test_on_demand_flow.py         # NEW

src/frontend/
├── src/
│   ├── api/
│   │   └── analyses.ts                   # NEW: trigger, getStatuses, getResult
│   ├── store/
│   │   └── analysisStore.ts              # NEW: Zustand store
│   ├── types/
│   │   └── analysis.ts                   # NEW: TypeScript interfaces
│   └── components/
│       └── analysis/                     # NEW
│           ├── OptionsPanel.tsx           # Options buttons with status
│           ├── AnalysisResultView.tsx     # Router to type-specific views
│           ├── IndexTreeView.tsx          # Expandable tree
│           ├── RelationsListView.tsx      # Grouped relation list
│           ├── QuestionsCascadeView.tsx   # Cascade display
│           ├── ConclusionsView.tsx        # Grouped observations
│           └── SourceRefPopover.tsx       # Shared source_ref display
├── tests/
│   ├── components/analysis/
│   │   └── OptionsPanel.test.tsx         # NEW
│   └── store/
│       └── analysisStore.test.ts         # NEW
```

---

## Database Changes

**One new table** via migration `005_create_analysis_results.sql`. No changes to existing tables. The `mark_all_outdated` operation updates this table when a document is re-uploaded.

**Integration with existing outdated flow:** When `BaseAnalysisStorage.mark_outdated(document_id)` is called on re-upload, `OnDemandAnalysisStorage.mark_all_outdated(document_id)` must also be called. This is wired in the upload endpoint or the base analysis service.

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Options Panel | `OptionsPanel.tsx`, `useAnalysisStore.statuses`, classification-based filtering, status indicators |
| Req 2: Build Index | `IndexAnalyzer`, `build_index.py` prompt, `StructureNode` model, tree with role + question_answered |
| Req 3: Section Relations | `RelationsAnalyzer`, `section_relations.py` prompt, `SectionRelation` model, vocabulary enforcement |
| Req 4: Questions Answered | `QuestionsAnalyzer`, `questions_answered.py` prompt, `AnsweredQuestion` model, cascade structure |
| Req 5: Conclusions | `ConclusionsAnalyzer`, `conclusions.py` prompt, `Observation` model, structural-only suggestions, language split |
| Req 6: Execution Model | `OnDemandAnalysisService.execute()`, sync await, idempotency check, outdated marking, error handling |
| Req 7: API Endpoints | `api/v1/analyses.py`, POST trigger, GET summary, GET single, preference headers |
| Req 8: Results Display | `IndexTreeView`, `RelationsListView`, `QuestionsCascadeView`, `ConclusionsView`, shadcn/ui |
| Req 9: Evidence Traceability | `SourceRef` model, `SourceRefPopover.tsx`, chunk_id validation, "unverified" marking |
