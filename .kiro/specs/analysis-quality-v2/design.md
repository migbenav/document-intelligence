# Design — Analysis Quality v2 (Mejora de Calidad del Análisis)

## Overview

This document describes the technical design for overhauling the on-demand analysis engine. The primary changes are: (1) redesigned prompts that focus on functional/purpose comprehension instead of visual structure listing, (2) propagation of actual model_id through the full stack, (3) classified error handling for LLM failures, (4) improved language detection, and (5) passing document classification to all analyzers.

All changes are backward-compatible at the API level (same endpoints, same response shape with added fields). The database schema (`analysis_results`) does not change — only the content stored in the `result` JSONB column evolves. Frontend types are extended (new optional fields) but existing fields remain.

## Relevant Documentation

- #[[file:.kiro/specs/analysis-quality-v2/requirements.md]]
- #[[file:.kiro/specs/on-demand-analysis/design.md]]
- #[[file:src/backend/app/analysis/on_demand/service.py]]
- #[[file:src/backend/app/analysis/on_demand/index_analyzer.py]]
- #[[file:src/backend/app/analysis/on_demand/prompts/build_index.py]]
- #[[file:src/backend/app/analysis/on_demand/prompts/questions_answered.py]]
- #[[file:src/backend/app/analysis/on_demand/prompts/conclusions.py]]
- #[[file:src/backend/app/analysis/on_demand/prompts/section_relations.py]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/backend/app/ingestion/language.py]]
- #[[file:src/frontend/src/components/layout/Sidebar.tsx]]
- #[[file:src/frontend/src/api/client.ts]]

---

## Architecture

### Change Impact Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│  BACKEND CHANGES                                                         │
│                                                                          │
│  LLMClient (llm_client.py)                                              │
│    ├── NEW: LLMQuotaExhaustedError exception class                      │
│    ├── CHANGE: detect 429/quota errors and raise specific exception      │
│    └── CHANGE: DEFAULT_FALLBACK_MODEL → groq/llama-3.3-70b-versatile    │
│                                                                          │
│  Analyzers (index, relations, questions, conclusions)                    │
│    ├── CHANGE: return AnalyzerResponse instead of raw result             │
│    ├── CHANGE: accept classification parameter                           │
│    └── CHANGE: new prompt templates (v2) with functional focus           │
│                                                                          │
│  OnDemandAnalysisService (service.py)                                    │
│    ├── CHANGE: load document_card before executing analyzer              │
│    ├── CHANGE: pass classification + document_language to analyzers      │
│    └── CHANGE: use actual_model_id from analyzer return value            │
│                                                                          │
│  API Endpoint (analyses.py)                                              │
│    ├── CHANGE: classify exceptions → specific error_code in response     │
│    └── CHANGE: add requested_model + fallback_used to success response   │
│                                                                          │
│  Pydantic Models (on_demand/models.py)                                   │
│    ├── CHANGE: StructureNode + functional_group, original_headings       │
│    ├── CHANGE: QuestionsResult + coherence_note                          │
│    ├── CHANGE: Observation categories updated                            │
│    └── CHANGE: SectionRelation types updated                             │
│                                                                          │
│  Language Detection (ingestion/language.py)                               │
│    ├── CHANGE: expand sample to 2000 chars                               │
│    ├── CHANGE: add Portuguese/French stopwords                           │
│    └── CHANGE: strip noise (numbers, URLs) before analysis               │
│                                                                          │
│  Base Analysis (base_analysis/llm_analyzer.py)                           │
│    └── CHANGE: request language confirmation in LLM prompt               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  FRONTEND CHANGES                                                        │
│                                                                          │
│  Sidebar.tsx                                                             │
│    └── CHANGE: add Gemini 2.5 Pro, Groq Llama 4 Maverick to selector    │
│                                                                          │
│  types/analysis.ts                                                       │
│    ├── CHANGE: StructureNode + functional_group, original_headings       │
│    ├── CHANGE: QuestionsResult + coherence_note                          │
│    ├── CHANGE: Observation categories updated                            │
│    └── CHANGE: AnalysisRecord + actual_model_id, fallback_used           │
│                                                                          │
│  AnalysisResultView.tsx                                                   │
│    └── CHANGE: display model badge per result                            │
│                                                                          │
│  analysisStore.ts                                                        │
│    └── CHANGE: parse classified errors, store error_code + model_id      │
│                                                                          │
│  Error display (new or modified component)                               │
│    └── NEW: differentiated error messages for quota/timeout/auth          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Changes |
|-----------|---------------|---------|
| `AnalyzerResponse` (NEW) | Standard return type for all analyzers | Dataclass with result, model_id, prompt_version, fallback_used |
| `IndexAnalyzer` | Build structure tree from IR | Returns AnalyzerResponse, accepts classification, uses v2 prompt |
| `RelationsAnalyzer` | Identify section relationships | Returns AnalyzerResponse, accepts classification, uses v2 prompt |
| `QuestionsAnalyzer` | Generate question cascade | Returns AnalyzerResponse, accepts classification, uses v2 prompt |
| `ConclusionsAnalyzer` | Produce structural observations | Returns AnalyzerResponse, accepts classification, uses v2 prompt |
| `OnDemandAnalysisService` | Orchestrator | Loads card for classification, uses real model_id |
| `LLMClient` | LLM communication | New LLMQuotaExhaustedError, cross-provider fallback |
| `api/v1/analyses.py` | HTTP layer | Classified error responses (429, 504, 401, 502) |

### Key Interfaces

```python
@dataclass
class AnalyzerResponse:
    """Standard return type for all on-demand analyzers."""
    result: BaseModel
    model_id: str
    prompt_version: str
    fallback_used: bool = False


class IndexAnalyzer:
    """Builds a functional structure tree from a document."""

    async def analyze(
        self,
        ir: IntermediateRepresentation,
        language: str,
        classification: str = "generic",
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> AnalyzerResponse: ...


class OnDemandAnalysisService:
    """Orchestrates on-demand analysis with classification context."""

    def __init__(
        self,
        index_analyzer: IndexAnalyzer,
        relations_analyzer: RelationsAnalyzer,
        questions_analyzer: QuestionsAnalyzer,
        conclusions_analyzer: ConclusionsAnalyzer,
        storage: OnDemandAnalysisStorage,
        ingestion_storage: StorageService,
        card_storage: BaseAnalysisStorage,
    ) -> None: ...

    async def execute(
        self,
        document_id: str,
        analysis_type: AnalysisType,
        preferences: dict,
    ) -> AnalysisRecord: ...


class LLMQuotaExhaustedError(Exception):
    """Raised when LLM returns 429 / quota exhausted."""
    def __init__(self, model_id: str, message: str):
        self.model_id = model_id
        super().__init__(message)
```

---

## Data Models

### Updated Pydantic Models (Build Index v2)

```python
class StructureNode(BaseModel):
    id: str
    title: str
    level: int
    role: str | None
    functional_group: str | None = None
    original_headings: list[str] = []
    question_answered: str | None
    source_ref: SourceRef | None
    children: list["StructureNode"] = []

class IndexResult(BaseModel):
    tree: list[StructureNode]
    document_purpose: str | None = None
```

### Updated Pydantic Models (Questions Answered v2)

```python
class QuestionsResult(BaseModel):
    document_questions: list[AnsweredQuestion]
    section_questions: list[AnsweredQuestion]
    coherence_note: str | None = None
```

### Updated Pydantic Models (Conclusions v2)

```python
class Observation(BaseModel):
    category: str
    description: str
    suggestion: str
    section_ref: str | None
    domain: str | None = None
    source_ref: SourceRef | None

class ConclusionsResult(BaseModel):
    observations: list[Observation]
    domains_identified: list[str] = []
```

### Updated Pydantic Models (Section Relations v2)

```python
class SectionRelation(BaseModel):
    source_section: str
    target_section: str
    type: str
    description: str
    domain: str | None = None
    source_ref: SourceRef | None

class RelationsResult(BaseModel):
    relations: list[SectionRelation]
```

### Updated Pydantic Models (AnalysisRecord)

```python
class AnalysisRecord(BaseModel):
    id: str
    document_id: str
    analysis_type: AnalysisType
    status: AnalysisStatus
    result: dict | None
    model_id: str | None
    requested_model: str | None = None
    fallback_used: bool = False
    prompt_version: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

### Frontend Types

```typescript
interface StructureNode {
  id: string;
  title: string;
  level: number;
  role: string | null;
  functional_group: string | null;
  original_headings: string[];
  question_answered: string | null;
  source_ref: SourceRef | null;
  children: StructureNode[];
}

interface QuestionsResult {
  document_questions: AnsweredQuestion[];
  section_questions: AnsweredQuestion[];
  coherence_note: string | null;
}

interface Observation {
  category: 'purpose_mismatch' | 'misplaced_content' | 'title_mismatch' | 'sequence_issue' | 'duplication' | 'contradiction';
  description: string;
  suggestion: string;
  section_ref: string | null;
  domain: string | null;
  source_ref: SourceRef | null;
}

interface AnalysisRecord {
  id: string;
  document_id: string;
  analysis_type: AnalysisType;
  status: AnalysisStatus;
  result: unknown;
  model_id: string | null;
  requested_model: string | null;
  fallback_used: boolean;
  prompt_version: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface AnalysisError {
  error_code: 'quota_exhausted' | 'timeout' | 'auth_error' | 'analysis_failed';
  model_id?: string;
  message: string;
}
```

---

## API Design

### POST /api/v1/documents/{document_id}/analyses/{analysis_type}

Same endpoint, extended error responses:

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Analysis completed | Full AnalysisRecord with model_id, requested_model, fallback_used |
| 404 | Document not found | `{ "error_code": "document_not_found", "message": "..." }` |
| 409 | IR not available | `{ "error_code": "document_not_ready", "message": "..." }` |
| 429 | LLM quota exhausted | `{ "error_code": "quota_exhausted", "model_id": "...", "message": "..." }` |
| 401 | LLM auth failed | `{ "error_code": "auth_error", "message": "..." }` |
| 504 | LLM timeout | `{ "error_code": "timeout", "message": "..." }` |
| 502 | Other LLM failure | `{ "error_code": "analysis_failed", "message": "..." }` |

---

## Prompt Strategy

### Build Index v2 — Functional Comprehension

The prompt changes fundamentally: instead of "list sections and headings," it asks the LLM to UNDERSTAND the document and produce a functional map.

**Two-phase approach within a single prompt:**
1. First: identify document purpose and type (normative, procedural, narrative, mixed)
2. Then: identify functional groupings and map document sections into them

Key instruction changes:
- "Do NOT simply list headings. Identify what the document DOES and how its parts serve that purpose."
- "Multiple chapters that serve the same function should be grouped under one functional node."
- "The tree represents FUNCTION, not visual layout."

### Questions Answered v2 — Logic Revelation

The prompt adapts based on document classification:
- Includes classification in the system instruction
- Provides type-specific question patterns as examples
- Instructs LLM to find the LOGICAL CHAIN, not describe content
- Includes coherence assessment

### Conclusions v2 — Domain-Aware

The prompt adds a domain identification step:
1. "First, identify the independent domains/topics in this document"
2. "Then, find structural problems WITHIN each domain"
3. "NEVER flag contradictions between independent domains"
4. "Evaluate if each section's PURPOSE matches the document's declared type"

### Section Relations v2 — Functional Connections

The prompt focuses on functional dependency:
- New vocabulary: enables, restricts, requires, implements, contradicts
- "Only flag contradicts between sections addressing the SAME domain"
- "Exclude trivial sequential relationships"

---

## Model Configuration

### Updated Defaults

| Constant | Old Value | New Value |
|----------|-----------|-----------|
| DEFAULT_PRIMARY_MODEL | gemini/gemini-2.5-flash | gemini/gemini-2.5-flash (unchanged) |
| DEFAULT_LIGHT_MODEL | gemini/gemini-2.5-flash | gemini/gemini-2.5-flash (unchanged) |
| DEFAULT_FALLBACK_MODEL | gemini/gemini-2.5-flash | groq/llama-3.3-70b-versatile |

### Available Models (Frontend)

| ID | Name | Description |
|----|------|-------------|
| default | Default (auto) | Gemini Flash para análisis, con fallback a Groq |
| gemini/gemini-2.5-flash | Gemini 2.5 Flash | Rápido, 1M tokens. Ideal para la mayoría de documentos. |
| gemini/gemini-2.5-pro | Gemini 2.5 Pro | Mayor calidad, más lento. Para documentos complejos. |
| groq/llama-3.3-70b-versatile | Groq Llama 3.3 70B | Muy rápido, 128K tokens. Bueno para documentos cortos. |
| groq/meta-llama/llama-4-maverick-17b-128e | Groq Llama 4 Maverick | Balance velocidad/calidad, 128K tokens. |

### Fallback Logic

When the user selects a model and it fails:
- If selected model is from Gemini → fallback to Groq
- If selected model is from Groq → fallback to Gemini
- If "default" → primary is Gemini, fallback is Groq (current flow)

---

## Language Detection Improvement

### Enhanced Local Detector

Changes to `src/backend/app/ingestion/language.py`:
- `_MAX_SAMPLE_LENGTH` increased from 1000 to 2000
- New `_PORTUGUESE_STOPWORDS` set (top 50 Portuguese stopwords)
- New `_FRENCH_STOPWORDS` set (top 50 French stopwords)
- New `_preprocess()` method: strips URLs, number-heavy tokens, camelCase/snake_case before tokenization
- `detect()` updated to score all four languages and return the winner

### LLM Confirmation in Base Analysis

The base analysis LLM prompt is extended with a language confirmation request. If the LLM disagrees with the local detector, the card's `file_metadata.language` is updated.

---

## Key Technical Decisions

### Decision 1: Backward-Compatible Model Extensions

New fields (`functional_group`, `original_headings`, `coherence_note`, `domain`, `fallback_used`, `requested_model`) are all optional with defaults. Existing stored results remain valid. No migration needed for `analysis_results` table — the JSONB column accommodates new fields automatically.

### Decision 2: Prompt Versioning

All new prompts use v2 versions (`build-index-v2`, `questions-answered-v2`, etc.). Old results with v1 prompts remain accessible. The frontend can check `prompt_version` to know which fields are available.

### Decision 3: Classification Dependency

If the document_card is not available (partial or missing), analyzers default to `classification="generic"` which uses the most conservative prompt (similar to current behavior). This ensures the system degrades gracefully.

### Decision 4: Quota Error as Separate HTTP Status

Using 429 (Too Many Requests) for quota errors instead of 502 allows the frontend to clearly differentiate "retry with different model" from "something broke." The frontend already has error classification by status code.

---

## Error Handling

| Error Type | Exception | HTTP Status | Frontend Message |
|------------|-----------|-------------|------------------|
| Quota exhausted | LLMQuotaExhaustedError | 429 | "Se agotó la cuota de {model}. Seleccione otro modelo o espere." |
| Timeout | asyncio.TimeoutError | 504 | "El análisis tardó demasiado. Intente con un modelo más rápido." |
| Auth failure | LLMAuthenticationError | 401 | "Error de credenciales para el modelo. Verifique la configuración." |
| Other failure | Exception | 502 | "El análisis falló. Intente nuevamente." |

---

## File Structure

```
src/backend/app/analysis/on_demand/
├── analyzer_response.py          # NEW: AnalyzerResponse dataclass
├── prompts/
│   ├── build_index.py            # existing v1 (kept for reference)
│   ├── build_index_v2.py         # NEW: functional comprehension prompt
│   ├── questions_answered.py     # existing v1
│   ├── questions_answered_v2.py  # NEW: logic revelation prompt
│   ├── conclusions.py            # existing v1
│   ├── conclusions_v2.py         # NEW: domain-aware prompt
│   ├── section_relations.py      # existing v1
│   └── section_relations_v2.py   # NEW: functional connections prompt
├── index_analyzer.py             # MODIFIED: returns AnalyzerResponse, uses v2 prompt
├── relations_analyzer.py         # MODIFIED: same pattern
├── questions_analyzer.py         # MODIFIED: same pattern
├── conclusions_analyzer.py       # MODIFIED: same pattern
├── service.py                    # MODIFIED: loads card, passes classification
├── models.py                     # MODIFIED: new optional fields
└── storage.py                    # unchanged
```

---

## Correctness Properties

### Property 1: Model ID Accuracy

The `model_id` field in every `AnalysisRecord` SHALL always reflect the actual LLM model that produced the response (from `LLMResponse.model_id`), never the requested model. If `requested_model != model_id`, then `fallback_used` SHALL be `true`.

**Validates: Requirements 5.1, 5.3**

### Property 2: Quota Error Isolation

A `LLMQuotaExhaustedError` SHALL never trigger the fallback mechanism. The user must explicitly choose a different model. Other transient errors (timeout, service unavailable) continue to trigger fallback as before.

**Validates: Requirements 5.2, 6.3**

### Property 3: Classification Graceful Degradation

If the document_card does not exist or has `classification=null`, all analyzers SHALL use `"generic"` as classification, producing results equivalent to the current v1 behavior. No analyzer SHALL crash or return an error due to missing classification.

**Validates: Requirements 8.4**

### Property 4: Backward Compatibility

All new fields in Pydantic models and TypeScript types are optional with defaults. Any existing `AnalysisRecord` with `prompt_version` containing "v1" SHALL continue to deserialize, display, and function correctly without modification.

**Validates: Requirements 1.8, 2.9, 3.10, 4.6**

### Property 5: Domain Boundary Respect

The Conclusions analyzer SHALL never produce an observation with `category="contradiction"` where `source_section` and `target_section` belong to different domains (as identified in `domains_identified`).

**Validates: Requirements 3.8**

### Property 6: Prompt Version Traceability

Every new analysis result SHALL contain `prompt_version` matching the v2 version string of the prompt that produced it. This enables the frontend to determine which fields are available in the result.

**Validates: Requirements 5.1, 8.3**

---

## Testing Strategy

### Unit Tests (per task)

Each task includes specific unit tests that mock LLMClient and Supabase. Key areas:
- Model propagation: verify `response.model_id` flows through to `AnalysisRecord`
- Error classification: verify correct exception types and HTTP status codes
- Prompt construction: verify prompts include classification, functional instructions, domain constraints
- Model validation: verify new optional fields parse correctly with and without values

### Integration Tests

- API endpoint tests with httpx TestClient verifying:
  - Correct error_code in 429/504/401/502 responses
  - Success response includes `requested_model` and `fallback_used`
  - Classification flows from card to analyzer prompt

### Backward Compatibility Tests

- Load stored v1 analysis results and verify they display without error
- Verify frontend components render both v1 (without new fields) and v2 (with new fields) results

### Manual Validation

- Execute each analysis type on a real document and verify:
  - Build Index produces functional groupings, not heading lists
  - Questions reveal document logic, not content summaries
  - Conclusions don't flag cross-domain contradictions
  - Relations show functional connections, not sequential trivial relations

---

## Traceability to Requirements

| Requirement | Components Affected |
|-------------|-------------------|
| Req 1: Build Index functional | index_analyzer.py, prompts/build_index_v2.py, models.py (StructureNode), IndexTreeView.tsx |
| Req 2: Questions logic | questions_analyzer.py, prompts/questions_answered_v2.py, models.py (QuestionsResult), QuestionsCascadeView.tsx |
| Req 3: Conclusions domain-aware | conclusions_analyzer.py, prompts/conclusions_v2.py, models.py (Observation), ConclusionsView.tsx |
| Req 4: Relations functional | relations_analyzer.py, prompts/section_relations_v2.py, models.py (SectionRelation), RelationsListView.tsx |
| Req 5: Model transparency | analyzer_response.py, service.py, analyses.py, analysisStore.ts, AnalysisResultView.tsx |
| Req 6: Model selection/fallback | llm_client.py, Sidebar.tsx, preferencesStore.ts |
| Req 7: Language detection | language.py, llm_analyzer.py (base analysis) |
| Req 8: Classification as input | service.py, all four analyzers |
