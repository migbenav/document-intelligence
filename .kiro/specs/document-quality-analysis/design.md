# Design — Document Quality Analysis

## Overview

This document describes the technical design for the Document Quality Analysis feature (Feature 5). It covers the architecture, data models, API contracts, module structure, and key technical decisions required to implement the approved requirements.

The quality analysis engine is the system's reasoning core. It consumes the completed Knowledge Model (produced by Feature 3) and evaluates the document across three quality dimensions: internal inconsistencies (contradictions and ambiguities), completeness gaps (relative to the document type schema), and actionable improvement suggestions. This is the primary differentiator of the MVP (ADR-001): the system not only extracts knowledge but reasons about its quality.

## Relevant Documentation

- #[[file:.kiro/specs/document-quality-analysis/requirements.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/design.md]]
- #[[file:docs/decisions/ADR-001-mvp-scope.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-006-document-type-schemas.md]]

---

## Architecture

### System Context

```
┌──────────────┐     ┌────────────────────────────────────────────────────────┐
│   Frontend   │────▶│            Quality Analysis Engine                      │
│  (Feature 5  │◀────│  (contradictions → ambiguities → completeness →         │
│   UI panel)  │     │   suggestions → evidence verification)                  │
└──────────────┘     └────────────────────────────────────────────────────────┘
                                      │                    ▲
                                      │                    │
                                      ▼                    │
                              ┌───────────────┐    ┌──────────────────┐
                              │  LLM Providers │    │  Knowledge Model │
                              │  (Gemini/Groq) │    │  (Feature 3)     │
                              └───────────────┘    └──────────────────┘
                                      │                    ▲
                                      ▼                    │
                              ┌───────────────┐    ┌──────────────────┐
                              │   Supabase    │    │  IR (Ingestion)  │
                              │  (PostgreSQL) │    │  (Feature 1)     │
                              └───────────────┘    └──────────────────┘
```

### Internal Module Decomposition

The quality analysis engine is organized into six internal modules:

1. **QualityAnalysisService** — Orchestrator that coordinates the full pipeline and manages session state.
2. **ContradictionDetector** — Identifies contradictions from explicit `contradicts` relationships + LLM-based deeper analysis.
3. **AmbiguityDetector** — Identifies ambiguous/vague statements using LLM analysis with KM context.
4. **CompletenessEvaluator** — Compares KM elements against document type schemas (skipped for Generic).
5. **SuggestionGenerator** — Produces actionable improvement recommendations from findings.
6. **FindingVerifier** — Verifies evidence text spans in findings using the existing deterministic text-matching algorithm.

### Pipeline Flow

```
API: POST /quality-analysis  (trigger)
       │
       ├── [document not found] → 404
       ├── [KM not completed] → 409
       ├── [analysis in progress] → 409 (analysis_in_progress)
       │
       ▼
QualityAnalysisService.run_analysis()
       │
       ├── Create/reset quality analysis record (status: analyzing)
       │
       ├── Step 1: ContradictionDetector.detect()
       │       ├── Collect explicit contradicts relationships (structural, no LLM)
       │       └── LLM call (primary model) → additional contradictions
       │
       ├── Step 2: AmbiguityDetector.detect()
       │       └── LLM call (primary model) → ambiguity findings
       │
       ├── Step 3: CompletenessEvaluator.evaluate()  [skipped for Generic]
       │       └── Compare KM elements vs. document type schema → missing/partial findings
       │
       ├── Step 4: SuggestionGenerator.generate()
       │       └── LLM call (primary model) → suggestions from findings
       │
       ├── Step 5: FindingVerifier.verify_all()
       │       └── Deterministic text-matching on all source_refs → set evidence_verified
       │
       ├── Persist results + metadata
       │
       ├── Update status → "completed"
       │
       └── Return results

ON FAILURE at any step:
       ├── Preserve explicit-relationship contradictions as partial results (Req 1.6)
       ├── Clean up all other partial results
       ├── Mark status → "failed" with error message
       └── Return error on next GET

API: GET /quality-analysis  (retrieve)
       │
       ├── [document not found] → 404
       ├── [KM not completed] → 409
       ├── [analysis completed] → 200 (return cached results)
       ├── [analysis in progress] → 202 (return current phase)
       ├── [analysis failed] → 500 (return error details)
       └── [no analysis triggered yet] → 404
```

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `api/v1/quality.py` | HTTP layer — POST to trigger, GET to retrieve quality analysis | REST endpoints (POST + GET) | `QualityAnalysisService` |
| `QualityAnalysisService` | Orchestrates the quality pipeline, manages state | `run_analysis()`, `get_results()` | All detectors, `AnalysisStorageService`, `FindingVerifier` |
| `ContradictionDetector` | Detects contradictions (structural + LLM) | `detect(km, ir) → list[Inconsistency]` | `LLMClient`, KM relationships |
| `AmbiguityDetector` | Detects ambiguous statements | `detect(km, ir) → list[Inconsistency]` | `LLMClient`, KM elements + IR |
| `CompletenessEvaluator` | Evaluates document completeness vs. schema (uses LLM for partial assessment) | `evaluate(km, doc_type) → list[MissingElement]` | `LLMClient`, Document type schemas |
| `SuggestionGenerator` | Generates improvement suggestions | `generate(findings, km) → list[Suggestion]` | `LLMClient`, all findings |
| `FindingVerifier` | Verifies evidence in findings | `verify_all(findings, ir) → findings` | IR chunks (reuses verification algorithm) |
| Prompt Templates | Versioned instruction sets for each analysis type | Template modules | — |

### Key Interfaces

```python
# --- Finding Models (Req 1, 2, 3, 4, 7) ---
class FindingSourceRef(BaseModel):
    """Evidence reference in a quality finding."""
    document_id: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    evidence: str  # Max 500 characters
    evidence_verified: bool = False  # Set by FindingVerifier (Req 7.5)

class Inconsistency(BaseModel):
    """A contradiction or ambiguity finding."""
    id: str
    type: Literal["contradiction", "ambiguity"]
    description: str  # Max 500 characters
    severity: Literal["high", "medium", "low"]
    affected_element_ids: list[str]  # KM element IDs involved
    source_refs: list[FindingSourceRef]  # At least 1; at least 2 for contradictions
    involves_unverified_elements: bool = False  # Req 8.4
    all_evidence_unverified: bool = False  # Req 7.7
    from_explicit_relationship: bool = False  # True for structural contradictions

class MissingElement(BaseModel):
    """A finding for missing or partial document content."""
    id: str
    classification: Literal["missing", "partial"]
    expected_element: str  # Element name from schema
    description: str
    severity: Literal["high", "medium", "low"]
    schema_reference: str  # Document type that defines the expectation

class Suggestion(BaseModel):
    """An actionable improvement recommendation."""
    id: str
    description: str  # Max 300 characters
    category: Literal["structure", "clarity", "completeness", "consistency"]
    priority: Literal["high", "medium", "low"]
    related_finding_ids: list[str] = []  # Optional references to findings
    source_refs: list[FindingSourceRef] = []  # At least 1 (Req 7.6)
    all_evidence_unverified: bool = False

class QualityAnalysisMetadata(BaseModel):
    """Metadata for reproducibility and auditing."""
    prompt_versions: dict[str, str]  # {analysis_type: version}
    model_id: str
    temperature: float
    document_type: str
    started_at: datetime
    completed_at: datetime
    finding_counts: dict[str, int]  # {contradictions, ambiguities, missing_elements, suggestions}

class QualityAnalysisResult(BaseModel):
    """Complete quality analysis output."""
    document_id: str
    status: Literal["analyzing", "completed", "failed"]
    inconsistencies: list[Inconsistency] = []
    missing_elements: list[MissingElement] = []
    suggestions: list[Suggestion] = []
    metadata: QualityAnalysisMetadata | None = None
    error_message: str | None = None
    error_phase: str | None = None
```

```python
# --- Service Interfaces ---

class ContradictionDetector:
    """Detects contradictions from structural relationships and LLM analysis."""

    def __init__(self, llm_client: LLMClient) -> None: ...

    async def detect(
        self,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
    ) -> list[Inconsistency]:
        """Detect contradictions in the Knowledge Model.

        Step 1: Collect explicit `contradicts` relationships as confirmed findings.
        Step 2: Call LLM to detect additional semantic contradictions.

        On LLM failure, returns only the explicit-relationship contradictions (Req 1.6).
        """
        ...


class AmbiguityDetector:
    """Detects ambiguous/vague statements using LLM analysis."""

    def __init__(self, llm_client: LLMClient) -> None: ...

    async def detect(
        self,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
    ) -> list[Inconsistency]:
        """Detect ambiguities in the document.

        Uses KM elements and IR text to identify:
        - Undefined terms
        - Vague quantifiers
        - Unclear pronoun antecedents
        - Unspecified conditions
        """
        ...


class CompletenessEvaluator:
    """Evaluates document completeness against type schemas."""

    def __init__(self, llm_client: LLMClient) -> None: ...

    async def evaluate(
        self,
        knowledge_model: KnowledgeModel,
        document_type: str,
    ) -> list[MissingElement]:
        """Compare KM elements against the document type schema.

        Schema matching (present vs missing) is deterministic.
        The "partial" classification uses LLM to assess content depth
        via the completeness_evaluation_v1.py prompt.

        Returns empty list for "generic" type (Req 3.3).
        Returns error indication for empty Knowledge Models (Req 3.6).
        """
        ...


class SuggestionGenerator:
    """Generates actionable improvement suggestions from findings."""

    def __init__(self, llm_client: LLMClient) -> None: ...

    async def generate(
        self,
        inconsistencies: list[Inconsistency],
        missing_elements: list[MissingElement],
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
    ) -> list[Suggestion]:
        """Generate suggestions based on findings.

        Guarantees at least one suggestion per high-severity finding (Req 4.4).
        Maximum 20 suggestions per run (Req 4.6).
        """
        ...


class FindingVerifier:
    """Verifies evidence text spans in findings against the IR."""

    def verify_all(
        self,
        inconsistencies: list[Inconsistency],
        suggestions: list[Suggestion],
        ir: IntermediateRepresentation,
    ) -> tuple[list[Inconsistency], list[Suggestion]]:
        """Verify source_ref evidence in all findings.

        Uses the same deterministic text-matching algorithm as
        VerificationService (Feature 3, Req 7). Sets evidence_verified
        on each source_ref and all_evidence_unverified on findings.
        """
        ...


class QualityAnalysisService:
    """Orchestrates the complete quality analysis pipeline."""

    def __init__(
        self,
        contradiction_detector: ContradictionDetector,
        ambiguity_detector: AmbiguityDetector,
        completeness_evaluator: CompletenessEvaluator,
        suggestion_generator: SuggestionGenerator,
        finding_verifier: FindingVerifier,
        storage: AnalysisStorageService,
    ) -> None: ...

    async def run_analysis(self, document_id: str) -> QualityAnalysisResult:
        """Run the full quality analysis pipeline.

        Prerequisites: completed KM (Req 8.1).
        Timeout: 120 seconds (Req 6.7).
        """
        ...

    async def get_results(self, document_id: str) -> QualityAnalysisResult | None:
        """Retrieve existing quality analysis results (idempotent, Req 5.8)."""
        ...
```

---

## Data Models

### Quality Analysis Findings (Pydantic)

The Pydantic models are defined above in the Interfaces section. Key design decisions:

- `Inconsistency` unifies contradictions and ambiguities under a single model with a `type` discriminator.
- `FindingSourceRef` extends the existing `SourceRef` pattern with `evidence_verified` for Trust by Evidence.
- `MissingElement` does not require `source_ref` (the element is absent by definition).
- `Suggestion` always includes at least one `source_ref` pointing to the context that triggered it.
- `all_evidence_unverified` is a finding-level flag derived from source_ref verification.

### Document Type Schemas (Configuration)

```python
# schemas.py — Expected elements per document type (from ADR-006)

DOCUMENT_TYPE_SCHEMAS: dict[str, list[dict[str, str]]] = {
    "prd": [
        {"name": "propósito", "description": "Document purpose and product goal", "importance": "high"},
        {"name": "usuarios/actores", "description": "Target users and actors", "importance": "high"},
        {"name": "requisitos funcionales", "description": "Functional requirements", "importance": "high"},
        {"name": "restricciones", "description": "Constraints and limitations", "importance": "medium"},
        {"name": "criterios de éxito", "description": "Success criteria and metrics", "importance": "medium"},
    ],
    "technical_spec": [
        {"name": "propósito", "description": "Specification purpose and scope", "importance": "high"},
        {"name": "alcance", "description": "System scope and boundaries", "importance": "high"},
        {"name": "componentes/conceptos", "description": "System components and key concepts", "importance": "high"},
        {"name": "interfaces", "description": "API interfaces and contracts", "importance": "medium"},
        {"name": "restricciones", "description": "Technical constraints", "importance": "medium"},
        {"name": "decisiones", "description": "Design decisions and rationale", "importance": "low"},
    ],
    "policy_process": [
        {"name": "propósito", "description": "Policy/process purpose", "importance": "high"},
        {"name": "alcance", "description": "Scope of applicability", "importance": "high"},
        {"name": "actores/roles", "description": "Involved actors and roles", "importance": "high"},
        {"name": "reglas", "description": "Business rules and policies", "importance": "high"},
        {"name": "procesos", "description": "Process steps and workflows", "importance": "medium"},
        {"name": "excepciones", "description": "Exceptions and edge cases", "importance": "low"},
    ],
}
```

### Database Schema

Quality analysis results are stored as a JSONB column on the existing `analysis_sessions` table:

```sql
-- Migration: add quality_analysis column to analysis_sessions
ALTER TABLE analysis_sessions
    ADD COLUMN quality_analysis JSONB DEFAULT NULL,
    ADD COLUMN quality_status TEXT DEFAULT NULL,
    ADD COLUMN quality_error_message TEXT DEFAULT NULL,
    ADD COLUMN quality_started_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN quality_completed_at TIMESTAMPTZ DEFAULT NULL;

-- quality_status values: NULL (not started), 'analyzing', 'completed', 'failed'
-- quality_analysis contains the full QualityAnalysisResult serialized as JSONB

COMMENT ON COLUMN analysis_sessions.quality_analysis IS
    'Full quality analysis results (inconsistencies, missing_elements, suggestions, metadata)';
COMMENT ON COLUMN analysis_sessions.quality_status IS
    'Quality analysis state: NULL | analyzing | completed | failed';
```

**Rationale for extending `analysis_sessions` vs. separate table:** The quality analysis is a 1:1 extension of the existing analysis session. It always references the same document and depends on the same KM. A separate table would require joins and foreign keys for no architectural benefit at the MVP scale.

---

## API Design

### POST /api/v1/documents/{document_id}/quality-analysis

Triggers a new quality analysis run. Returns 202 on success.

**Response (202) — Analysis triggered:**
```json
{
  "document_id": "uuid",
  "status": "analyzing_contradictions"
}
```

**Error Responses:**

| Status | Condition | Error Code |
|--------|-----------|------------|
| 404 | Document not found | `not_found` |
| 409 | Knowledge Model extraction not completed | `km_not_completed` |
| 409 | Quality analysis already in progress | `analysis_in_progress` |
| 500 | Internal server error | `internal_error` |

**409 response (KM not completed):**
```json
{
  "error": "km_not_completed",
  "message": "Quality analysis requires a completed Knowledge Model. Current analysis status: extracting."
}
```

**409 response (analysis in progress):**
```json
{
  "error": "analysis_in_progress",
  "message": "Quality analysis is already running for this document. Wait for it to complete or fail before re-triggering."
}
```

### GET /api/v1/documents/{document_id}/quality-analysis

Retrieves quality analysis results. Does not trigger analysis.

**Response (200) — Analysis completed (retrieval):**
```json
{
  "document_id": "uuid",
  "status": "completed",
  "inconsistencies": [
    {
      "id": "inc-001",
      "type": "contradiction",
      "description": "Section 3.1 states max response time is 200ms, while Section 5.2 requires responses within 500ms for the same endpoint.",
      "severity": "high",
      "affected_element_ids": ["elem-005", "elem-012"],
      "source_refs": [
        {
          "document_id": "uuid",
          "chunk_id": "chunk-003",
          "section": "## Performance Requirements",
          "evidence": "All API endpoints must respond within 200ms",
          "evidence_verified": true
        },
        {
          "document_id": "uuid",
          "chunk_id": "chunk-008",
          "section": "## SLA Definitions",
          "evidence": "Response time SLA: 500ms for standard endpoints",
          "evidence_verified": true
        }
      ],
      "involves_unverified_elements": false,
      "all_evidence_unverified": false,
      "from_explicit_relationship": true
    }
  ],
  "missing_elements": [
    {
      "id": "miss-001",
      "classification": "missing",
      "expected_element": "criterios de éxito",
      "description": "PRD documents should define measurable success criteria.",
      "severity": "medium",
      "schema_reference": "prd"
    }
  ],
  "suggestions": [
    {
      "id": "sug-001",
      "description": "Add a section defining measurable success criteria with specific KPIs and target values.",
      "category": "completeness",
      "priority": "medium",
      "related_finding_ids": ["miss-001"],
      "source_refs": [
        {
          "document_id": "uuid",
          "chunk_id": "chunk-001",
          "section": "## Introduction",
          "evidence": "This document defines the product requirements",
          "evidence_verified": true
        }
      ],
      "all_evidence_unverified": false
    }
  ],
  "metadata": {
    "prompt_versions": {
      "contradiction_detection": "contradiction-v1",
      "ambiguity_detection": "ambiguity-v1",
      "completeness_evaluation": "completeness-v1",
      "suggestion_generation": "suggestion-v1"
    },
    "model_id": "gemini/gemini-2.5-flash-preview-05-20",
    "temperature": 0.1,
    "document_type": "prd",
    "started_at": "2026-07-28T10:00:00Z",
    "completed_at": "2026-07-28T10:01:15Z",
    "finding_counts": {
      "contradictions": 2,
      "ambiguities": 3,
      "missing_elements": 1,
      "suggestions": 5
    }
  }
}
```

**Response (202) — Analysis in progress:**
```json
{
  "document_id": "uuid",
  "status": "analyzing_contradictions"
}
```

Status values during analysis: `"analyzing_contradictions"`, `"analyzing_ambiguities"`, `"analyzing_completeness"`, `"generating_suggestions"`.

**Error Responses (GET):**

| Status | Condition | Error Code |
|--------|-----------|------------|
| 404 | Document not found or no analysis triggered | `not_found` |
| 409 | Knowledge Model extraction not completed | `km_not_completed` |
| 500 | Quality analysis failed | `analysis_failed` |

**409 response:**
```json
{
  "error": "km_not_completed",
  "message": "Quality analysis requires a completed Knowledge Model. Current analysis status: extracting."
}
```

**500 response (analysis failed):**
```json
{
  "error": "analysis_failed",
  "message": "Quality analysis failed during ambiguity detection: LLM service unavailable.",
  "phase": "analyzing_ambiguities"
}
```

---

## Key Technical Decisions

### Decision 1: Pipeline Ordering

**Choice:** Contradictions (structural) → Contradictions (LLM) → Ambiguities → Completeness → Suggestions → Evidence Verification.

**Reasoning:** Structural contradictions are extracted first (zero LLM cost, deterministic) so they can be preserved as partial results on failure. LLM-based contradiction detection follows because it extends the structural pass. Ambiguities require a separate LLM call. Completeness is purely structural (no LLM) and runs after the LLM steps to avoid blocking on failures. Suggestions run last because they consume all prior findings as input. Evidence verification is the final step, applied to all findings before persistence.

**Phase-transition DB writes:** Each phase transition (e.g., "analyzing_contradictions" → "analyzing_ambiguities") requires a DB write to update `quality_status` so the GET endpoint can report progress to polling clients. This adds ~4 extra DB writes per analysis run. This is acceptable for MVP given the analysis itself takes 30–90 seconds of LLM time, making the sub-millisecond DB writes negligible overhead.

### Decision 2: Reuse Existing LLMClient

**Choice:** Reuse the `LLMClient` from Feature 3 for all LLM calls.

**Reasoning:** The quality analysis pipeline needs the same capabilities: primary model for deep analysis, automatic fallback on transient errors, credential validation, and model tracking. No new LLM abstractions are needed. The `LLMClient.call()` interface with `model_tier` and `temperature` parameters covers all quality analysis needs.

### Decision 3: Storage Strategy — Extend analysis_sessions

**Choice:** Add `quality_analysis` JSONB column + status columns to the existing `analysis_sessions` table.

**Reasoning:** Quality analysis is a 1:1 relationship with the analysis session. The same document always has exactly one quality analysis result. A separate table would require foreign key management and joins for no benefit. The JSONB column stores the full `QualityAnalysisResult` including findings, metadata, and counts. Status tracking columns (`quality_status`, `quality_started_at`, `quality_completed_at`, `quality_error_message`) enable the API to report progress without deserializing the full JSONB.

### Decision 4: Completeness Evaluation — Deterministic Matching with LLM for Partial Assessment

**Choice:** Completeness evaluation uses a deterministic mapping from KM element types to schema expectations for present/missing classification. The "partial" classification uses LLM to assess content depth.

**Reasoning:** The document type schemas define expected element types (e.g., PRD expects "propósito", "actores", "requisitos funcionales"). The Knowledge Model already categorizes elements by type. The evaluator matches KM element types against schema expectations using string matching and heuristics — this is fast, deterministic, and reproducible for determining present vs. missing. However, classifying an element as "partial" (content exists but covers fewer than half of the sub-aspects implied by its schema definition) requires semantic understanding of content depth that cannot be done with simple string matching. For this, the evaluator uses the `completeness_evaluation_v1.py` prompt to ask the LLM whether a present element adequately covers its schema definition or only partially addresses it.

### Decision 5: Timeout Mechanism

**Choice:** asyncio-based timeout of 120 seconds wrapping the full pipeline, with `asyncio.shield()` protecting the failure cleanup from cancellation.

**Reasoning:** Per Req 6.7, if quality analysis doesn't complete within 120 seconds, it should be marked as failed. Using `asyncio.wait_for()` around the pipeline execution provides clean cancellation. On timeout, the service marks the record as failed with a timeout error message. The `asyncio.shield()` around `_mark_failed` prevents the cleanup coroutine from being cancelled if the parent task is cancelled during timeout handling — without it, the database update to record the failure could be interrupted, leaving the record stuck in "analyzing" forever.

```python
import asyncio

async def run_analysis(self, document_id: str) -> QualityAnalysisResult:
    try:
        result = await asyncio.wait_for(
            self._execute_pipeline(document_id),
            timeout=120.0,
        )
        return result
    except asyncio.TimeoutError:
        await asyncio.shield(
            self._mark_failed(document_id, "Quality analysis timed out after 120 seconds")
        )
        raise
```

### Decision 6: Prompt Strategy — Separate Prompts per Analysis Type

**Choice:** Four separate prompt modules: `contradiction_detection_v1.py`, `ambiguity_detection_v1.py`, `completeness_evaluation_v1.py`, `suggestion_generation_v1.py`.

**Reasoning:** Each analysis type requires different instructions, different JSON output schemas, and different context. Separate prompts allow independent iteration and versioning. Each prompt module exports a `VERSION` constant and a `build()` function, following the established pattern from Feature 3. The contradiction detection prompt includes KM elements and relationships. The ambiguity prompt includes KM elements and raw IR text. The completeness evaluation prompt is used by `CompletenessEvaluator` for partial coverage assessment — when an element is present but the evaluator needs to determine if it adequately covers the schema definition or only partially addresses it. The suggestion prompt includes all findings.

### Decision 7: Partial Results on LLM Failure

**Choice:** On LLM failure, preserve contradictions collected from explicit `contradicts` relationships but discard all other partial results.

**Reasoning:** Per Req 1.6, explicit-relationship contradictions are deterministic and already collected before the LLM step. They provide value to the user even when the LLM is unavailable. Other findings (ambiguities, LLM-detected contradictions, suggestions) are discarded because incomplete results could be misleading. The quality_status is set to "failed" so the user knows the analysis is incomplete.

### Decision 8: Separate POST (Trigger) and GET (Retrieve) Endpoints

**Choice:** Two endpoints: `POST /quality-analysis` to trigger analysis and `GET /quality-analysis` to retrieve results.

**Reasoning:** This follows REST semantics — GET is safe and idempotent (never triggers side effects), POST is used for state-changing operations. This is consistent with the existing API pattern: `POST /{id}/analyze` triggers KM extraction, `GET /{id}/knowledge-model` retrieves results. The behavior of each endpoint is clear: POST validates prerequisites and starts the pipeline (returns 202), GET reports current state (200 completed, 202 in progress, 404 not found/not triggered, 409 KM not ready, 500 failed). Re-triggering after failure or completion uses POST again — the service resets and re-runs. If POST is called while analysis is already in progress (`quality_status = "analyzing"`), the endpoint returns 409 with error code `analysis_in_progress` — the user must wait for the current run to complete or fail before re-triggering.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Explicit Contradictions Pass-Through

*For any* Knowledge Model containing explicit `contradicts` relationships between elements, the quality analysis output SHALL include one Inconsistency finding of type "contradiction" for each such relationship, with `from_explicit_relationship = true`, regardless of LLM availability or response.

**Validates: Requirements 1.1, 1.3, 1.6**

### Property 2: Finding Structural Completeness

*For any* Inconsistency finding of type "contradiction", the finding SHALL contain at least 2 source_refs with non-empty evidence (max 500 chars each), at least 2 affected_element_ids, a description of max 500 characters, and a valid severity level. *For any* Inconsistency of type "ambiguity", the finding SHALL contain at least 1 source_ref and a description explaining at least 2 interpretations.

**Validates: Requirements 1.2, 2.2, 7.1, 7.2, 7.3**

### Property 3: Generic Type Completeness Skip

*For any* document with confirmed type "generic", the quality analysis SHALL return an empty `missing_elements` list AND still execute contradiction and ambiguity detection (non-empty results possible for those categories).

**Validates: Requirements 3.3, 8.6**

### Property 4: Suggestion Count Bound

*For any* quality analysis run, the number of suggestions in the output SHALL be at most 20.

**Validates: Requirements 4.6**

### Property 5: Suggestion Coverage of High-Severity Findings

*For any* quality analysis result containing high-severity findings (contradictions, ambiguities, or missing elements with severity "high"), the number of suggestions SHALL be at least equal to the number of high-severity findings.

**Validates: Requirements 4.4**

### Property 6: Clean Failure State

*For any* quality analysis that transitions to "failed" status, the `quality_analysis` JSONB field SHALL contain ONLY explicit-relationship contradictions (with `from_explicit_relationship = true`) if any were collected before the failure, and no other findings. The `quality_error_message` SHALL be non-empty with max 1000 characters.

**Validates: Requirements 6.2, 6.4**

### Property 7: Evidence Verification Determinism

*For any* finding with source_refs, applying the deterministic text-matching algorithm against the same IR produces the same `evidence_verified` values. *For any* finding where all source_refs have `evidence_verified = false`, the finding-level `all_evidence_unverified` attribute SHALL be `true`.

**Validates: Requirements 7.5, 7.7**

### Property 8: Knowledge Model Prerequisite Gate

*For any* document whose analysis session status is not "completed", attempting to run quality analysis SHALL return an error without creating or modifying any quality analysis record.

**Validates: Requirements 8.1, 6.1**

### Property 9: Data Minimization

*For any* prompt sent to the LLM during quality analysis, the prompt content SHALL contain only Knowledge Model elements, relationships, IR text chunks referenced by those elements, the document type schema (for completeness), and system instructions. No user identity, session ID, account metadata, or document_id is included.

**Validates: Requirements 9.2, 10.7**

### Property 10: Idempotent Retrieval

*For any* completed quality analysis, calling the GET endpoint multiple times SHALL return byte-for-byte identical JSON responses without re-triggering the analysis pipeline.

**Validates: Requirements 5.8**

### Property 11: Pydantic Validation Gate

*For any* LLM response that fails validation against the expected Pydantic response model for its analysis type, the corresponding analysis step SHALL be treated as failed with a parsing error indication.

**Validates: Requirements 10.2, 10.3**

---

## Interaction Flow

```
=== TRIGGER (POST /api/v1/documents/{document_id}/quality-analysis) ===

1. Client calls POST /api/v1/documents/{document_id}/quality-analysis
       │
       ├── [document not found] → 404
       ├── [analysis session not found] → 404
       ├── [analysis session status ≠ "completed"] → 409 (km_not_completed)
       ├── [quality_status = "analyzing"] → 409 (analysis_in_progress)
       │
       ▼
2. Set quality_status = "analyzing", quality_started_at = now()
       │── If previous results exist (completed/failed), reset and clear them
       │
       ▼
3. Return 202 with initial status
       │
       ▼
4. (Background) Run pipeline...

=== RETRIEVE (GET /api/v1/documents/{document_id}/quality-analysis) ===

1. Client calls GET /api/v1/documents/{document_id}/quality-analysis
       │
       ├── [document not found] → 404
       ├── [analysis session not found] → 404
       ├── [analysis session status ≠ "completed"] → 409 (km_not_completed)
       ├── [quality_status = NULL (not triggered)] → 404
       ├── [quality_status = "completed"] → 200 (return cached results)
       ├── [quality_status = "analyzing"] → 202 (return current phase)
       ├── [quality_status = "failed"] → 500 (return error)
       │
       └── Return appropriate response

=== PIPELINE EXECUTION (background after POST) ===

3. Load Knowledge Model + IR from database
       │── Retrieve KM from analysis_sessions.knowledge_model
       │── Retrieve IR chunks from document_chunks
       │
       ▼
4. ContradictionDetector.detect(km, ir)
       │── Update phase → "analyzing_contradictions"
       │── Step 4a: Collect explicit contradicts relationships → confirmed findings
       │── Step 4b: Build contradiction detection prompt (KM elements + relations)
       │── Step 4c: Call LLM (primary model, temperature 0.1)
       │── Step 4d: Parse response against Pydantic model
       │
       ├── [LLM fails] → preserve structural contradictions, continue with partial
       ├── [Parse fails] → mark step failed
       │
       ▼
5. AmbiguityDetector.detect(km, ir)
       │── Update phase → "analyzing_ambiguities"
       │── Step 5a: Build ambiguity detection prompt (KM elements + IR text)
       │── Step 5b: Call LLM (primary model, temperature 0.1)
       │── Step 5c: Parse response against Pydantic model
       │
       ├── [LLM or parse fails] → mark failed, preserve explicit contradictions
       │
       ▼
6. CompletenessEvaluator.evaluate(km, doc_type)
       │── Update phase → "analyzing_completeness"
       │── [doc_type = "generic"] → skip, return empty list
       │── Step 6a: Load schema for confirmed document type
       │── Step 6b: Match KM element types against expected elements
       │── Step 6c: Classify each expected element as present/partial/missing
       │
       ▼
7. SuggestionGenerator.generate(findings, km, ir)
       │── Update phase → "generating_suggestions"
       │── Step 7a: Build suggestion prompt (all findings + KM context)
       │── Step 7b: Call LLM (primary model, temperature 0.1)
       │── Step 7c: Parse response, enforce max 20 suggestions
       │── Step 7d: Verify >= 1 suggestion per high-severity finding
       │
       ├── [LLM or parse fails] → mark failed
       │
       ▼
8. FindingVerifier.verify_all(inconsistencies, suggestions, ir)
       │── For each source_ref in each finding:
       │     verify evidence text span against IR chunks
       │     set evidence_verified = true/false
       │── Set all_evidence_unverified on findings where all refs are unverified
       │
       ▼
9. Mark elements with involves_unverified_elements where applicable (Req 8.4)
       │
       ▼
10. Persist results
       │── Serialize QualityAnalysisResult to JSONB
       │── Update analysis_sessions: quality_analysis, quality_status = "completed",
       │   quality_completed_at = now()
       │
       └── Return QualityAnalysisResult
```

---

## Error Handling

| Error Source | Error Type | Behavior | Recovery |
|-------------|-----------|----------|----------|
| Document not found | API | Return 404 | Correct document_id |
| KM not completed | Prerequisite | Return 409 (km_not_completed) | Wait for KM extraction to complete |
| Analysis already in progress | State conflict | Return 409 (analysis_in_progress) on POST | Wait for current analysis to complete or fail |
| Primary LLM rate-limited | Transient | Auto-fallback to secondary model via LLMClient | Automatic |
| Both LLM models fail | Transient | Mark quality_status = "failed", preserve explicit contradictions | Retry via POST |
| LLM response unparseable | Extraction | Mark step as failed, set quality_status = "failed" | Retry via POST |
| Pipeline timeout (>120s) | Timeout | Mark quality_status = "failed" with timeout message (asyncio.shield ensures cleanup) | Retry via POST |
| Empty Knowledge Model | Prerequisite | Skip completeness, report error in results | Re-run Feature 3 extraction |
| Schema not found for doc type | Configuration | Fail completeness step entirely | Fix configuration |
| Analysis not yet triggered | State | Return 404 on GET | Trigger via POST first |
| Analysis already completed | State | Return 200 with cached results on GET (idempotent) | No action needed |
| Analysis previously failed | State | Return 500 with error details on GET | Retry via POST |

---

## Security Considerations

Aligned with ADR-005 (Privacy and External Processing):

- **Data minimization:** Only KM elements, relationships, IR text chunks, and system prompts are sent to LLM providers. No user identity, session history, document identifiers, or account metadata is included in prompts (Req 9.2).
- **No user metadata persisted:** Quality analysis results store only document content derivatives and analysis metadata. No user identity is attached.
- **Reuses LLM abstraction:** All LLM communication goes through the existing `LLMClient`, maintaining centralized credential management and audit trail.
- **LLM output treated as untrusted:** All LLM responses are validated against Pydantic schemas before persistence. Invalid output is rejected and reported as a failure.
- **Evidence verification:** Source_refs are verified against the actual document text to detect hallucinated evidence. Unverified findings are clearly marked.

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| ContradictionDetector | Structural pass, LLM parsing, partial results on failure | Unit tests with mocked LLM; property tests for structural contradictions pass-through |
| AmbiguityDetector | LLM response parsing, finding structure | Unit tests with mocked LLM responses |
| CompletenessEvaluator | Schema matching, present/partial/missing classification, generic skip | Property tests: for any KM + schema, correct classification; unit tests for edge cases |
| SuggestionGenerator | Suggestion structure, count bounds, high-severity coverage | Property tests: max 20, >= 1 per high-severity; unit tests with mocked LLM |
| FindingVerifier | Evidence text-matching, all_evidence_unverified flag | Property tests reusing verification algorithm; unit tests for boundary cases |
| QualityAnalysisService | Pipeline orchestration, state transitions, timeout, failure cleanup | Unit tests with mocked dependencies; property tests for state machine |
| API Endpoint | HTTP contract, status codes, idempotent retrieval | Integration tests via httpx AsyncClient |
| End-to-End | Full pipeline with mocked LLM | Integration tests: KM ready → trigger → poll → retrieve results |

**Property-Based Testing (fast-check / Hypothesis):**

The following correctness properties will be tested using property-based testing (minimum 100 iterations):

- Property 1: Explicit contradictions always appear in output (Hypothesis with generated KMs)
- Property 2: Finding structural completeness (all required fields present)
- Property 3: Generic type returns empty missing_elements
- Property 4: Suggestion count ≤ 20
- Property 5: At least one suggestion per high-severity finding
- Property 6: Failed status has no partial results (except explicit contradictions)
- Property 7: Evidence verification is deterministic
- Property 8: KM prerequisite blocks analysis

**Property Test Library:** Hypothesis (Python PBT library, already compatible with pytest)

**Test Configuration:**
- Minimum 100 iterations per property test
- Each property test tagged with: `Feature: document-quality-analysis, Property {N}: {title}`

All integration tests use mocked LLM responses to avoid real API calls during CI.

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| LiteLLM | LLM provider abstraction (via existing LLMClient) | Project standard; already configured for Feature 3 |
| FastAPI | HTTP framework | Project standard; existing backend framework |
| Pydantic v2 | Data validation for findings and LLM output parsing | Project standard; validates untrusted LLM output |
| supabase-py | Database client for session persistence | Project standard; existing database layer |
| pytest + httpx | Testing | Project standard; async integration tests |
| Hypothesis | Property-based testing | Python standard PBT library; integrates with pytest |

No additional dependencies beyond the project's established stack and Hypothesis for testing.

---

## File Structure

```
src/backend/
├── app/
│   ├── api/v1/
│   │   ├── documents.py              # Existing ingestion endpoints
│   │   ├── analysis.py               # Existing KM analysis endpoints
│   │   └── quality.py                # NEW: quality-analysis endpoint
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── service.py                # Existing AnalysisService (extended for quality)
│   │   ├── llm_client.py             # Existing LLMClient (reused)
│   │   ├── type_inference.py         # Existing
│   │   ├── extraction.py             # Existing
│   │   ├── verification.py           # Existing (reused by FindingVerifier)
│   │   ├── quality/                   # NEW: Quality analysis module
│   │   │   ├── __init__.py
│   │   │   ├── service.py            # QualityAnalysisService orchestrator
│   │   │   ├── contradiction_detector.py
│   │   │   ├── ambiguity_detector.py
│   │   │   ├── completeness_evaluator.py
│   │   │   ├── suggestion_generator.py
│   │   │   ├── finding_verifier.py
│   │   │   └── schemas.py            # Document type schemas (ADR-006)
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── type_inference_v1.py       # Existing
│   │       ├── extraction_v1.py           # Existing
│   │       ├── contradiction_detection_v1.py  # NEW
│   │       ├── ambiguity_detection_v1.py      # NEW
│   │       ├── completeness_evaluation_v1.py  # NEW
│   │       └── suggestion_generation_v1.py    # NEW
│   ├── models/
│   │   ├── document.py               # Existing IR models
│   │   ├── knowledge_model.py        # Existing KM models
│   │   └── quality_analysis.py       # NEW: Finding Pydantic models
│   └── db/
│       └── migrations/
│           ├── 001_create_documents.sql
│           ├── 002_create_analysis_sessions.sql
│           └── 003_add_quality_analysis.sql   # NEW
└── tests/
    ├── unit/
    │   └── analysis/
    │       ├── quality/                       # NEW
    │       │   ├── test_contradiction_detector.py
    │       │   ├── test_ambiguity_detector.py
    │       │   ├── test_completeness_evaluator.py
    │       │   ├── test_suggestion_generator.py
    │       │   ├── test_finding_verifier.py
    │       │   ├── test_quality_service.py
    │       │   └── test_quality_models.py
    │       └── ... (existing tests)
    ├── property/                               # NEW
    │   └── analysis/
    │       └── test_quality_properties.py     # Property-based tests
    └── integration/
        └── analysis/
            ├── test_analysis_flow.py          # Existing
            └── test_quality_flow.py           # NEW
```

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Contradiction Detection | `ContradictionDetector`, structural pass + LLM pass, `contradiction_detection_v1.py` prompt, partial results preservation on failure |
| Req 2: Ambiguity Detection | `AmbiguityDetector`, `ambiguity_detection_v1.py` prompt, 4 ambiguity categories in prompt instructions |
| Req 3: Completeness Evaluation | `CompletenessEvaluator`, `schemas.py` document type schemas, `completeness_evaluation_v1.py` prompt, generic type skip logic |
| Req 4: Suggestion Generation | `SuggestionGenerator`, `suggestion_generation_v1.py` prompt, max 20 cap, high-severity coverage guarantee |
| Req 5: Quality Analysis API | `api/v1/quality.py`, POST endpoint to trigger + GET endpoint to retrieve, 200/202/404/409/500 responses, 409 for analysis_in_progress on POST, metadata in response |
| Req 6: Session Management | `QualityAnalysisService`, `quality_status`/`quality_analysis` columns on `analysis_sessions`, state machine (analyzing → completed/failed), 120s timeout, overwrite on re-trigger via POST |
| Req 7: Evidence Traceability | `FindingVerifier`, `FindingSourceRef` with `evidence_verified`, `all_evidence_unverified` flag, reuse of verification algorithm |
| Req 8: Integration with KM | Prerequisite check (KM status = "completed"), KM elements as primary context, `contradicts` relationships as starting point, `involves_unverified_elements` flag |
| Req 9: Reproducibility & Minimization | `QualityAnalysisMetadata` with prompt versions + model_id + temperature, data minimization in prompts, temperature ≤ 0.1 default |
| Req 10: Quality Analysis Prompts | 4 versioned prompt modules, Pydantic response validation, schema inclusion for typed documents, prompt versioning pattern from Feature 3 |
