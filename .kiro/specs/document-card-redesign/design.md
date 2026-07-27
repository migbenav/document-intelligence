# Design — Document Card Redesign (Rediseño de la Card de Documento)

## Overview

This document describes the technical design for the Document Card Redesign feature. It evolves the original base-analysis card into a two-section layout with a formal 4-level classification taxonomy, leveraging local Python libraries (lingua-py, textstat) to reduce LLM dependency and provide instant technical metrics.

The redesign separates the card into two distinct phases: (1) a "Ficha Técnica" section produced entirely by local processing — language detection via lingua-py, text statistics via textstat, and structural analysis — that appears instantaneously; and (2) a "Contenido" section produced by a single LLM call with a reduced prompt (v3) that only asks for semantic analysis (summary, classification, topics, audience, lifecycle). The LocalAnalyzer v2 generates classification hints from title patterns and organization type, which are passed to the LLM to improve accuracy and produce a confidence score.

## Relevant Documentation

- #[[file:.kiro/specs/document-card-redesign/requirements.md]]
- #[[file:.kiro/specs/base-analysis/design.md]]
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:src/backend/app/analysis/base_analysis/local_analyzer.py]]
- #[[file:src/backend/app/analysis/base_analysis/llm_analyzer.py]]
- #[[file:src/backend/app/analysis/base_analysis/service.py]]
- #[[file:src/backend/app/models/document_card.py]]
- #[[file:src/frontend/src/components/document-card/DocumentCardView.tsx]]

---

## Architecture

### System Context

```
┌──────────────────┐     ┌─────────────────────────────────────────────────────────────┐
│     Frontend     │────▶│              Document Card Engine v2                          │
│  (Two-Section    │◀────│                                                               │
│   Card + Tooltips│     │  LocalAnalyzer v2 ──┐                                        │
│   + Collapsibles)│     │    • lingua-py       │──▶ Ficha Técnica (instant)             │
│                  │     │    • textstat         │                                        │
│                  │     │    • pattern hints    │                                        │
│                  │     │                       │                                        │
│                  │     │  LLMAnalyzer v3 ──────┼──▶ Contenido (async)                  │
│                  │     │    • prompt v3        │                                        │
│                  │     │    • receives hints   │                                        │
└──────────────────┘     └─────────────────────────────────────────────────────────────┘
                                      │                    ▲
                                      ▼                    │
                              ┌───────────────┐    ┌──────────────────┐
                              │  LLM Provider  │    │  Intermediate    │
                              │  (Groq light)  │    │  Representation  │
                              └───────────────┘    │  (Ingestion)     │
                                                   └──────────────────┘
```

### Internal Module Decomposition

The redesigned engine extends the existing base_analysis module with new components:

1. **BaseAnalysisService v2** — Updated orchestrator that coordinates local v2, LLM v3, and persistence. Same trigger (post-ingestion BackgroundTask).
2. **LocalAnalyzer v2** — Enhanced: adds lingua-py language detection, delegates to TextStatsAnalyzer, generates classification hints from patterns.
3. **TextStatsAnalyzer** — New module: word count, sentence count, paragraph count, readability index using textstat library.
4. **LLMAnalyzer v3** — Updated: new prompt v3, receives local hints, returns 4-level classification + topics + audience + lifecycle.
5. **BaseAnalysisStorage** — Updated: handles new fields in JSONB (no schema migration).
6. **ClassificationHintGenerator** — Logic within LocalAnalyzer v2 that maps title patterns and org type to suggested classification levels.

### Pipeline Flow

```
API: POST /api/v1/documents/upload (ingestion completes with status=ready)
       │
       ▼
BackgroundTask: BaseAnalysisService.analyze(document_id, ir)
       │
       ├── [card exists with status="completed" and same size_bytes] → return existing
       │
       ├── Step 1: LocalAnalyzer v2.analyze(ir)
       │       ├── lingua-py: detect_language(text[:5000])    → language (never "Unknown")
       │       ├── TextStatsAnalyzer.analyze(text)            → words, sentences, paragraphs, readability
       │       ├── _extract_title(ir)                         → first heading or filename
       │       ├── _compute_statistics(ir)                    → chunks, sections, levels, index
       │       ├── _detect_organization_type(ir)              → numbered_articles | headed_sections | ...
       │       ├── _generate_classification_hints(title, org_type) → suggested levels + is_corporate
       │       └── Returns: LocalAnalysisResultV2 (always succeeds, <200ms)
       │
       │   ──▶ Ficha Técnica available immediately (persisted as partial card)
       │
       ├── Step 2: LLMAnalyzer v3.analyze(title, chunks[:10], org_type, hints, language)
       │       ├── Build prompt v3 (title + org_type + hints + text sample ≤2000 chars)
       │       ├── LLMClient.call(prompt, model_tier="light", temperature=0.1)
       │       ├── [timeout >10s] → return None
       │       ├── [LLM error] → return None
       │       ├── [invalid JSON] → return None
       │       ├── Parse: summary, classification (4 levels), topics, audience, lifecycle
       │       ├── Compute confidence: min(level_confidences) ± hint_agreement_bonus
       │       └── Returns: LLMAnalysisResultV3 | None
       │
       ├── Step 3: Build DocumentCard v2
       │       ├── [LLM succeeded] → status="completed", all fields set
       │       ├── [LLM failed]    → status="partial", Contenido fields null, lifecycle="living"
       │       └── [LLM partial (some classification data)] → if purpose=informational+genre=expository → lifecycle="frozen"
       │
       └── Step 4: BaseAnalysisStorage.upsert_card(card)
              └── Persist to document_cards table (JSONB absorbs new fields)

ON RETRY (POST /api/v1/documents/{id}/card/retry-llm):
       ├── Load existing card + IR
       ├── [status="completed"] → 409
       ├── [no card] → 404
       ├── Re-execute LLMAnalyzer v3 (with stored hints)
       ├── Update Contenido fields + status
       └── Persist updated card
```

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `BaseAnalysisService` | Orchestrates local v2 + LLM v3 + persistence | `analyze()`, `retry_llm()` | `LocalAnalyzer`, `LLMAnalyzer`, `Storage` |
| `LocalAnalyzer` (v2) | Language + stats + structure + hints | `analyze(ir) → LocalAnalysisResultV2` | IR, lingua-py, TextStatsAnalyzer |
| `TextStatsAnalyzer` | Word/sentence/paragraph/readability | `analyze(text, lang) → TextStats` | textstat library |
| `LLMAnalyzer` (v3) | Summary + classification + topics + audience | `analyze(..., hints) → LLMAnalysisResultV3 \| None` | `LLMClient`, prompts_v3 |
| `BaseAnalysisStorage` | CRUD for DocumentCard v2 | `get_card()`, `upsert_card()`, `mark_outdated()` | Supabase client |
| `prompts_v3.py` | Versioned prompt template v3 | `PROMPT_TEMPLATE_V3`, `PROMPT_VERSION` | — |

### Key Interfaces

```python
# --- Classification Models (Req 3) ---

class ClassificationScope(str, Enum):
    INSTITUTIONAL = "institutional"
    GOVERNMENTAL = "governmental"
    PRIVATE = "private"
    OTHER = "other"

class ClassificationPurpose(str, Enum):
    NORMATIVE = "normative"
    OPERATIONAL = "operational"
    INFORMATIONAL = "informational"
    EVIDENTIARY = "evidentiary"
    CONTRACTUAL = "contractual"

class ClassificationGenre(str, Enum):
    PRESCRIPTIVE = "prescriptive"
    INSTRUCTIVE = "instructive"
    EXPOSITORY = "expository"
    REGISTRAL = "registral"
    BILATERAL = "bilateral"

class ClassificationFormat(str, Enum):
    REGULATION = "regulation"
    POLICY = "policy"
    MANUAL = "manual"
    PROCEDURE = "procedure"
    PROTOCOL = "protocol"
    GUIDE = "guide"
    MINUTES = "minutes"
    CONTRACT = "contract"
    OTHER = "other"

class DocumentClassificationResult(BaseModel):
    scope: ClassificationScope
    purpose: ClassificationPurpose
    genre: ClassificationGenre
    format: ClassificationFormat
    descriptor: str  # Free text: "Reglamento Interno", etc.
    scope_confidence: int  # 0-100
    purpose_confidence: int
    genre_confidence: int
    format_confidence: int
    confidence: int  # min(all level confidences) ± hint agreement
    display_chain_es: str  # "Institucional → Normativo → Prescriptivo → Reglamento (87%)"


# --- Bilingual Display Mapping ---

SCOPE_LABELS_ES = {
    "institutional": "Institucional",
    "governmental": "Gubernamental",
    "private": "Particular",
    "other": "Otro",
}

PURPOSE_LABELS_ES = {
    "normative": "Normativo",
    "operational": "Operativo",
    "informational": "Informativo",
    "evidentiary": "Evidencia",
    "contractual": "Contractual",
}

GENRE_LABELS_ES = {
    "prescriptive": "Prescriptivo",
    "instructive": "Instructivo",
    "expository": "Expositivo",
    "registral": "Registral",
    "bilateral": "Bilateral",
}

FORMAT_LABELS_ES = {
    "regulation": "Reglamento",
    "policy": "Política",
    "manual": "Manual",
    "procedure": "Procedimiento",
    "protocol": "Protocolo",
    "guide": "Guía",
    "minutes": "Acta",
    "contract": "Contrato",
    "other": "Otro",
}
```

```python
# --- Text Statistics (Req 1) ---

class TextStats(BaseModel):
    word_count: int
    sentence_count: int
    paragraph_count: int
    readability_score: float
    readability_label: str  # "Muy fácil", "Fácil", "Normal", "Difícil", "Muy difícil"
    readability_formula: str  # "fernandez-huerta" | "flesch" | "flesch-approximate"


class TextStatsAnalyzer:
    """Local text statistics using textstat + native Python. No network calls."""

    def analyze(self, text: str, language: str) -> TextStats:
        """Compute word count, sentences, paragraphs, readability.
        Uses Fernández-Huerta for Spanish, Flesch for English.
        Completes in <200ms for documents up to 10 MB.
        """
        ...

    def _compute_readability(self, text: str, language: str) -> tuple[float, str, str]:
        """Returns (score, label, formula_name)."""
        ...

    @staticmethod
    def _score_to_label(score: float) -> str:
        """Map score to human label with strict boundary validation:
        >80 → Muy fácil, >60 AND ≤80 → Fácil, >40 AND ≤60 → Normal,
        >20 AND ≤40 → Difícil, ≤20 → Muy difícil.
        Boundaries are exclusive/inclusive to prevent ambiguity.
        """
        ...
```

```python
# --- Local Analysis Result V2 (Reqs 1, 2, 6) ---

@dataclass
class ClassificationHints:
    suggested_scope: ClassificationScope | None = None
    suggested_purpose: ClassificationPurpose | None = None
    suggested_genre: ClassificationGenre | None = None
    suggested_format: ClassificationFormat | None = None
    is_corporate: bool = True
    hint_source: str = ""  # Description of what triggered the hint

@dataclass
class LocalAnalysisResultV2:
    title: str
    statistics: DocumentCardStatistics
    organization_type: OrganizationType
    file_metadata: FileMetadata  # language now from lingua-py
    text_stats: TextStats
    classification_hints: ClassificationHints


class LocalAnalyzer:
    """Enhanced v2: lingua-py + textstat + classification hints."""

    def __init__(self) -> None:
        self._language_detector = ...  # lingua LanguageDetectorBuilder

    def analyze(self, ir: IntermediateRepresentation) -> LocalAnalysisResultV2:
        """Full local analysis with language detection, text stats, and hints.
        Always succeeds. Completes in <200ms for documents up to 10 MB.
        """
        ...

    def _detect_language(self, text: str) -> str:
        """Detect language using lingua-py on first 5000 chars.
        Never returns 'Unknown'. If confidence < 30%, returns 'Indeterminado (xx, NN%)'.
        On timeout, retries with smaller samples (2500, 1000 chars) until within 100ms.
        """
        ...

    def _generate_classification_hints(
        self, title: str, organization_type: OrganizationType
    ) -> ClassificationHints:
        """Pattern-match title keywords and org type to suggest classification."""
        ...
```

```python
# --- LLM Analysis Result V3 (Reqs 3, 4) ---

@dataclass
class LLMAnalysisResultV3:
    summary: str
    classification: DocumentClassificationResult
    topics: list[str]  # 3-5 keywords
    audience: str
    lifecycle: Literal["living", "frozen"]
    model_id: str
    prompt_version: str


class LLMAnalyzer:
    """V3: reduced prompt, receives hints, returns 4-level classification."""

    def __init__(self, llm_client: LLMClient) -> None: ...

    async def analyze(
        self,
        title: str,
        chunks: list[ContentChunkModel],
        organization_type: OrganizationType,
        hints: ClassificationHints,
        language: str,
    ) -> LLMAnalysisResultV3 | None:
        """Call light model with prompt v3. 10s timeout. Returns None on failure.
        Distinguishes malformed JSON (LLM failure) from valid JSON with wrong schema (system error).
        Computes confidence based on LLM self-assessment ± hint agreement.
        """
        ...

    def _compute_confidence(
        self, llm_confidences: dict, hints: ClassificationHints, classification: dict
    ) -> int:
        """Aggregate confidence: min(levels) + bonus if hints agree, penalty if disagree."""
        ...
```

---

## Data Models

### DocumentCard v2 (Extended Pydantic v2)

The DocumentCard model is extended with new nullable fields. Existing cards without these fields remain valid (backward compatible via defaults).

```python
class DocumentCard(BaseModel):
    # --- Existing fields (unchanged) ---
    id: str
    document_id: str
    title: str
    summary: str | None = None
    classification: str | None = None  # Legacy: flat string, kept for backward compat
    organization_type: OrganizationType
    statistics: DocumentCardStatistics
    file_metadata: FileMetadata  # language now populated by lingua-py
    status: Literal["completed", "failed_llm", "partial"]
    outdated: bool = False
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: datetime
    updated_at: datetime

    # --- New fields (v2, nullable for backward compat) ---
    text_stats: TextStats | None = None
    classification_result: DocumentClassificationResult | None = None
    topics: list[str] = []
    audience: str | None = None
    lifecycle: Literal["living", "frozen"] = "living"
    is_corporate: bool = True
```

### Database Persistence (No Migration)

New fields are stored within the existing JSONB columns or as new nullable columns that Supabase/PostgreSQL handles without migration:

- `text_stats` → stored in existing `statistics` JSONB (extended)
- `classification_result` → new key in a JSONB column or new nullable JSONB column
- `topics`, `audience`, `lifecycle`, `is_corporate` → stored in a JSONB "extras" field or as individual nullable columns

Since the project uses JSONB extensively, new fields are absorbed without ALTER TABLE migrations. The Pydantic model handles serialization/deserialization with defaults for missing fields.

---

## API Design

### GET /api/v1/documents/{document_id}/card

Response extended with new fields (backward compatible — new fields may be null):

**Response (200) — Completed card v2:**
```json
{
  "id": "uuid",
  "documentId": "uuid",
  "title": "Reglamento Interno de Trabajo",
  "summary": "Este documento establece las normas internas de trabajo...",
  "classification": "normative",
  "classificationResult": {
    "scope": "institutional",
    "purpose": "normative",
    "genre": "prescriptive",
    "format": "regulation",
    "descriptor": "Reglamento Interno de Trabajo",
    "scopeConfidence": 92,
    "purposeConfidence": 88,
    "genreConfidence": 85,
    "formatConfidence": 90,
    "confidence": 85,
    "displayChainEs": "Institucional → Normativo → Prescriptivo → Reglamento (85%)"
  },
  "organizationType": "numbered_articles",
  "statistics": {
    "totalChunks": 45,
    "sectionsDetected": 12,
    "hierarchyLevels": 3,
    "hasExistingIndex": true
  },
  "textStats": {
    "wordCount": 8450,
    "sentenceCount": 342,
    "paragraphCount": 89,
    "readabilityScore": 45.2,
    "readabilityLabel": "Normal",
    "readabilityFormula": "fernandez-huerta"
  },
  "fileMetadata": {
    "sizeBytes": 234500,
    "format": "pdf",
    "language": "es"
  },
  "topics": ["normativa laboral", "jornada de trabajo", "sanciones disciplinarias"],
  "audience": "Empleados y área de Recursos Humanos",
  "lifecycle": "living",
  "isCorporate": true,
  "status": "completed",
  "outdated": false,
  "modelId": "groq/llama-3.3-70b-versatile",
  "promptVersion": "card-redesign-v3",
  "createdAt": "2026-07-27T10:30:00Z",
  "updatedAt": "2026-07-27T10:30:04Z"
}
```

**Partial card (LLM failed) — Ficha Técnica only:**
```json
{
  "id": "uuid",
  "documentId": "uuid",
  "title": "Reglamento Interno de Trabajo",
  "summary": null,
  "classification": null,
  "classificationResult": null,
  "organizationType": "numbered_articles",
  "statistics": { "totalChunks": 45, "sectionsDetected": 12, "hierarchyLevels": 3, "hasExistingIndex": true },
  "textStats": { "wordCount": 8450, "sentenceCount": 342, "paragraphCount": 89, "readabilityScore": 45.2, "readabilityLabel": "Normal", "readabilityFormula": "fernandez-huerta" },
  "fileMetadata": { "sizeBytes": 234500, "format": "pdf", "language": "es" },
  "topics": [],
  "audience": null,
  "lifecycle": "living",
  "isCorporate": true,
  "status": "partial",
  "outdated": false,
  "modelId": null,
  "promptVersion": null,
  "createdAt": "2026-07-27T10:30:00Z",
  "updatedAt": "2026-07-27T10:30:00Z"
}
```

API endpoints remain the same as base-analysis (GET /card, POST /retry-llm). No new endpoints needed.

---

## Key Technical Decisions

### Decision 1: lingua-py over Manual Stopword Detection

**Choice:** Replace the manual stopword-based language detector (`src/backend/app/ingestion/language.py`) with lingua-py (lingua-language-detector>=2.0.0).

**Reasoning:** The manual detector produces "Unknown" for many documents and only supports Spanish/English. lingua-py supports 75+ languages with high accuracy, never returns unknown (always provides a best guess with confidence), and is a single pip install with no external dependencies. The library operates on the first 5000 characters which is sufficient for reliable detection.

### Decision 2: textstat for Readability

**Choice:** Use textstat>=0.7.0 for readability computation rather than implementing formulas manually.

**Reasoning:** textstat implements Flesch, Fernández-Huerta, and many other formulas with proven correctness. It handles edge cases (empty text, single sentences) gracefully. Adding a well-maintained library avoids reimplementing statistical formulas and their edge cases.

### Decision 3: Classification Hints as Soft Guidance

**Choice:** Local classification hints are passed to the LLM as "suggested" values that the LLM may override, rather than hard constraints.

**Reasoning:** Local pattern matching (title keywords) is simple and may be wrong for documents with misleading titles. The LLM has access to the actual content and can make better judgments. However, when both local and LLM agree, confidence increases — this dual-validation improves trust in the classification. When they disagree, the lower confidence signals uncertainty to the user.

### Decision 4: Confidence as Weakest Link

**Choice:** Display the minimum confidence across all 4 classification levels rather than an average.

**Reasoning:** A chain classification is only as reliable as its weakest link. If scope is 95% confident but format is only 40%, showing 67% average would be misleading. Showing 40% (the weakest) gives the user an honest assessment of overall reliability.

### Decision 5: No Database Migration

**Choice:** Store new fields in existing JSONB columns or as nullable additions that don't require ALTER TABLE.

**Reasoning:** JSONB in PostgreSQL naturally handles schema evolution — new keys are simply absent in old records. The Pydantic model provides defaults (None, empty list, "living") for missing fields. This means zero downtime, no migration scripts, and backward compatibility by construction.

### Decision 6: Two-Phase Card Display

**Choice:** Persist a partial card immediately after local analysis (Ficha Técnica) before the LLM call, then update to completed when LLM responds.

**Reasoning:** The user sees value within milliseconds (file info, language, word count, readability) while the LLM processes. This is a significant UX improvement over the original design where the entire card was either available or not. The partial card now contains substantial useful information thanks to lingua-py and textstat.

### Decision 7: Single Prompt v3 with Structured Output

**Choice:** One LLM call requesting a single JSON object with all semantic fields (summary, classification 4 levels with confidences, topics, audience, lifecycle).

**Reasoning:** Multiple LLM calls would increase latency and cost. The light model (Groq Llama 3.3 70B) can handle a moderately complex structured output in a single call within the 10-second timeout. The prompt is simpler than v1 because it doesn't ask for stats/language (handled locally).

---

## Correctness Properties

### Property 1: Language Never Unknown

*For any* document processed by LocalAnalyzer v2, the detected language SHALL be a valid ISO 639-1 code or "Indeterminado (xx, NN%)" — never the literal string "Unknown" or an empty value.

**Validates: Requirements 2.3**

### Property 2: Text Stats Independence

*For any* document IR, the TextStatsAnalyzer SHALL produce valid TextStats (non-negative counts, score in valid range) without any network calls, LLM calls, or external service dependencies. Empty documents produce zero counts and score 0.

**Validates: Requirements 1.2, 1.3**

### Property 3: Classification Taxonomy Validity

*For any* completed DocumentClassificationResult, each level SHALL contain a valid enum value from its respective enum class. No level SHALL be null or empty in a completed classification.

**Validates: Requirements 3.1, 3.6**

### Property 4: Confidence Bounds

*For any* DocumentClassificationResult, the confidence field SHALL be an integer in [10, 99]. Individual level confidences SHALL be in [0, 100]. The aggregated confidence equals min(level_confidences) ± hint_agreement (capped to [10, 99]).

**Validates: Requirements 3.3, 3.4**

### Property 5: Hint Non-Interference

*For any* document where local hints disagree with LLM classification, the LLM classification SHALL be persisted as-is (hints are advisory only). The disagreement SHALL only affect the confidence score, not the classification values.

**Validates: Requirements 6.3**

### Property 6: Backward Compatibility

*For any* DocumentCard persisted before this redesign (lacking text_stats, classification_result, topics, audience, lifecycle, is_corporate), the system SHALL deserialize it successfully with default values and the frontend SHALL render it without errors.

**Validates: Requirements 9.2, 9.3**

### Property 7: Ficha Técnica Always Available

*For any* card with status in ["completed", "partial", "failed_llm"], the fields title, organization_type, statistics, file_metadata, and text_stats SHALL be non-null (text_stats may be null only for legacy cards pre-redesign).

**Validates: Requirements 5.2**

---

## Interaction Flow

```
=== DOCUMENT UPLOAD → TWO-PHASE CARD ===

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
       │── LocalAnalyzer v2.analyze(ir) → LocalAnalysisResultV2 (~<200ms)
       │      ├── lingua-py language detection
       │      ├── TextStatsAnalyzer (words, sentences, paragraphs, readability)
       │      ├── Title, statistics, org type (same as v1)
       │      └── Classification hints from patterns
       │── Persist partial card (Ficha Técnica available NOW)
       │── LLMAnalyzer v3.analyze(title, chunks[:10], org_type, hints, lang) (~1-5s)
       │      ├── Prompt v3 with hints context
       │      ├── Parse 4-level classification + topics + audience + lifecycle
       │      └── Compute confidence with hint agreement
       │── Update card → status="completed" (or remain "partial" on LLM failure)
       │── BaseAnalysisStorage.upsert_card(card)
       │
       ▼
5. Card available via GET /api/v1/documents/{document_id}/card


=== FRONTEND TWO-PHASE DISPLAY ===

1. Upload response received (document_id)
2. Display ProcessingStatus (progress bar only — simplified)
3. Poll GET /card every 1.5s
       ├── [404] → continue polling (max 10 attempts)
       ├── [200 + status="partial"] →
       │      ├── Hide ProcessingStatus
       │      ├── Show Ficha Técnica section (instant data: format, size, language, words)
       │      ├── Show Contenido section with skeleton (LLM still processing)
       │      └── Continue polling for completed status
       ├── [200 + status="completed"] →
       │      ├── Show Ficha Técnica section
       │      └── Show Contenido section (summary, classification chain, topics, badges)
       └── [10 attempts exhausted + still partial] → show retry button in Contenido


=== CARD SECTIONS ===

┌─────────────────────────────────────────────────────┐
│  📄 Reglamento Interno de Trabajo                   │
├─────────────────────────────────────────────────────┤
│  FICHA TÉCNICA                                      │
│  ┌───────┬──────────┬──────────┬─────────────────┐ │
│  │ PDF   │ 229 KB   │ Español  │ 8,450 palabras  │ │
│  └───────┴──────────┴──────────┴─────────────────┘ │
│  ▸ Más detalles                                     │
│    342 oraciones · 89 párrafos · Legibilidad: Normal│
│    Artículos numerados · 12 secciones · 3 niveles   │
│    Subido: 27 jul 2026                              │
├─────────────────────────────────────────────────────┤
│  CONTENIDO                                          │
│  Este documento establece las normas internas de    │
│  trabajo para todos los empleados...                │
│                                                     │
│  [normativa laboral] [jornada] [sanciones]          │
│                                                     │
│  Institucional → Normativo → Prescriptivo →         │
│  Reglamento (85%)                                   │
│                                                     │
│  ▸ Más detalles                                     │
│    Propósito: Regular la relación laboral           │
│    Audiencia: Empleados y RRHH                      │
│    🟢 Documento vivo                                │
└─────────────────────────────────────────────────────┘
```

---

## Error Handling

| Error Source | Error Type | HTTP Status | Behavior | Recovery |
|-------------|-----------|-------------|----------|----------|
| lingua-py fails (unlikely) | Library | — | Fallback to "Indeterminado" | None needed (graceful) |
| lingua-py timeout (>100ms) | Performance | — | Retry with smaller text sample (2500, 1000 chars) | Auto-handled |
| textstat fails on edge case | Library | — | Set readability to 0, label "No disponible" | None needed |
| LLM timeout (>10s) | Transient | — | Save partial card (Ficha Técnica only) | User retries via button |
| LLM invalid classification levels | Parse | — | Default invalid levels to "other", confidence=0 for that level | Auto-handled |
| LLM rate limit / service error | Transient | — | Save partial card | User retries later |
| LLM invalid JSON response | Parse | — | Save partial card (classified as LLM failure) | User retries via button |
| LLM valid JSON, wrong schema | System | — | Save partial card (classified as system error for debugging) | User retries via button |
| Legacy card without new fields | Schema | — | Deserialize with defaults | Auto-handled |
| Card not found (GET) | Timing | 404 | Return error | Retry later (polling) |
| Card already complete (retry) | Logic | 409 | Return error | No action needed |
| Non-corporate document | Classification | — | Show info banner, all analyses still available | Informational only |

---

## Security Considerations

Aligned with ADR-005 (Privacy and External Processing):

- **Data minimization:** Only document text (first 2000 chars), detected title, organization type, and classification hints (enum values, no user data) are sent to the LLM. No user identity, document_id, session history, or account metadata.
- **lingua-py is fully local:** Language detection runs entirely in-process with no network calls. No document text leaves the server for this analysis.
- **textstat is fully local:** Readability computation is pure computation on text strings. No network calls.
- **LLM output validated:** Classification values are validated against enums. Invalid values default to "other" rather than being stored as-is. This prevents prompt injection via classification fields.
- **Hints are derived, not stored verbatim:** Classification hints are enum values derived from pattern matching, not raw user input. They cannot be used for injection.
- **No sensitive data in card:** The DocumentCard contains structural metadata, a short summary, and classification. Full document text is not stored in the card.

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| TextStatsAnalyzer | Word/sentence/paragraph count, readability formulas | Unit tests with known texts in ES/EN, edge cases (empty, single word) |
| Language Detection | lingua-py integration, never-unknown guarantee | Unit tests with texts in multiple languages, edge cases |
| Classification Hints | Pattern matching, is_corporate logic | Unit tests with various titles and org types |
| LLMAnalyzer v3 | Prompt construction, 4-level parsing, confidence computation, hint agreement | Unit tests with mocked LLMClient |
| Confidence Computation | Min aggregation, bonus/penalty, bounds [10, 99] | Unit tests with various scenarios |
| Backward Compatibility | Legacy cards deserialize correctly | Unit tests with card JSON lacking new fields |
| Frontend Card Sections | Two-section layout, collapsibles, tooltips, badges | Component tests with various card states |
| End-to-End | Upload → partial card (Ficha Técnica) → completed card | Integration test with mocked LLM |

All tests use mocked LLM responses. lingua-py and textstat are tested with real library calls (fast, no network).

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| lingua-language-detector>=2.0.0 | Accurate language detection | Replaces manual stopword detector, never returns "Unknown", supports 75+ languages |
| textstat>=0.7.0 | Readability indices and text statistics | Implements Flesch, Fernández-Huerta, handles edge cases, well-maintained |
| LiteLLM | LLM provider abstraction (existing) | Project standard; light model call |
| FastAPI | HTTP framework + BackgroundTasks (existing) | Project standard |
| Pydantic v2 | Data validation (existing) | Project standard |
| supabase-py | Database client (existing) | Project standard |

New dependencies: **lingua-language-detector**, **textstat**. Both are pure Python with no heavy native dependencies.

---

## File Structure

```
src/backend/
├── app/
│   ├── analysis/
│   │   └── base_analysis/
│   │       ├── __init__.py                # Existing (unchanged)
│   │       ├── service.py                 # UPDATED: orchestrator v2 with two-phase persist
│   │       ├── local_analyzer.py          # UPDATED: lingua-py + TextStatsAnalyzer + hints
│   │       ├── llm_analyzer.py            # UPDATED: prompt v3, 4-level classification
│   │       ├── prompts.py                 # Existing (kept for reference)
│   │       ├── prompts_v3.py              # NEW: PROMPT_TEMPLATE_V3, PROMPT_VERSION
│   │       ├── text_stats_analyzer.py     # NEW: TextStatsAnalyzer (textstat wrapper)
│   │       └── storage.py                 # UPDATED: handle new JSONB fields
│   ├── models/
│   │   ├── document_card.py              # UPDATED: new nullable fields, TextStats
│   │   └── classification.py            # NEW: 4-level taxonomy enums + DocumentClassificationResult
│   └── ingestion/
│       └── language.py                    # REWRITTEN: lingua-py based detection
├── pyproject.toml                         # UPDATED: add lingua-language-detector, textstat

src/frontend/
├── src/
│   ├── types/
│   │   └── documentCard.ts               # UPDATED: new interfaces (TextStats, ClassificationResult)
│   ├── components/
│   │   ├── document-card/
│   │   │   └── DocumentCardView.tsx       # REWRITTEN: two-section layout, collapsibles, tooltips
│   │   └── upload/
│   │       ├── ProcessingStatus.tsx       # SIMPLIFIED: only progress bar + filename
│   │       └── UploadPage.tsx             # ADJUSTED: seamless transition to card
```

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Local Text Statistics | `TextStatsAnalyzer`, textstat library, `TextStats` model, Ficha Técnica "Más detalles" section |
| Req 2: Language Detection | lingua-py in `LocalAnalyzer._detect_language()`, `FileMetadata.language`, never-unknown guarantee |
| Req 3: 4-Level Classification | `DocumentClassificationResult`, 4 enum classes, bilingual labels, confidence computation, `display_chain_es` |
| Req 4: LLM Prompt v3 | `prompts_v3.py`, `LLMAnalyzer` v3, hints as context, single JSON output, 10s timeout |
| Req 5: Card Layout | Frontend `DocumentCardView.tsx` rewrite, two sections, collapsibles, tooltips, backward compat rendering |
| Req 6: Classification Hints | `ClassificationHints` dataclass, `_generate_classification_hints()`, pattern mapping, `is_corporate` logic |
| Req 7: Document Lifecycle | `lifecycle` field in `LLMAnalysisResultV3`, living/frozen logic based on classification, badge in Contenido section |
| Req 8: ProcessingStatus Simplification | `ProcessingStatus.tsx` simplified, seamless transition in `UploadPage.tsx` |
| Req 9: Backward Compatibility | Nullable fields with defaults, no DB migration, legacy card rendering fallback |
