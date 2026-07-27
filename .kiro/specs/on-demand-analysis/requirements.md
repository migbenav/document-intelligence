# Requirements Document

On-Demand Analysis (Análisis Bajo Demanda)

## Introduction

This feature implements the on-demand analysis options (C3) that appear after the base analysis card is displayed. Once the user sees the document card, they can trigger deeper analyses to progressively understand the document's structure, purpose, and quality — without reading it fully.

Each analysis operates at document level using a single LLM call with the full document context (Gemini 2.5 Flash, 1M token context window). This keeps each analysis fast (5-15s), coherent, and simple to implement. Block-level analysis (drilling into individual sections) is a separate feature (C4) triggered on demand per-section in the future.

This feature covers PRD v2 capability C3 (Análisis bajo demanda) and ADR-007 "Nivel 2 — Análisis bajo demanda."

## Relevant Documentation

- #[[file:docs/product/03-prd v2.md]]
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:.kiro/specs/base-analysis/requirements.md]]
- #[[file:.kiro/specs/user-preferences/requirements.md]]
- #[[file:.kiro/steering/language-rules.md]]
- #[[file:src/backend/app/models/document_card.py]]
- #[[file:src/backend/app/analysis/llm_client.py]]

## Feature Boundaries

**In scope:**
- Options panel UI showing available analyses below the document card, each with status indicator.
- Four analysis types at document level: Build Index (C3.1), Section Relations (C3.2), Questions Answered (C3.3), Conclusions & Recommendations (C3.4).
- Each analysis uses a single LLM call with the full document IR as context.
- Results are persisted and not re-executed on unchanged documents.
- Each result element includes a `source_ref` for evidence traceability (ADR-004).
- Analysis availability adapts based on document classification.
- Status tracking per analysis: not_started, in_progress, completed, outdated, failed.
- Results display UI for each analysis type.
- Language-aware: LLM output respects `ui_language` preference.
- Model-aware: uses model from user preferences.

**Out of scope (separate features or future):**
- Block-level analysis / drilling into individual sections (C4 — separate spec).
- Comparing generated index against existing document index.
- Multi-document analysis or cross-document relations.
- Text content suggestions (what the document SHOULD say) — only structural suggestions.
- Exporting analysis results.
- Batch analysis of multiple blocks at once.
- Confidence scores per result.

## Glossary

| Term | Definition |
|------|------------|
| On-Demand_Analysis | A deeper analysis that the user explicitly triggers after seeing the document card. Runs as a single LLM call at document level. |
| Structure_Tree | A hierarchical tree of sections produced by "Build Index". Each node has title, level, role, and a question it answers. |
| Section_Relation | A directed relationship between two sections: constrains, depends_on, complements, or contradicts. |
| Questions_Answered | Questions the document addresses, organized in a cascade: global (document-level purpose) → section-level (chapter objectives). |
| Conclusions | Structural observations about the document's organization and coherence — NOT suggestions about content text. |
| Analysis_Status | State of a specific analysis for a document: not_started, in_progress, completed, outdated, failed. |
| source_ref | Reference to the document text that supports a result: chunk_id(s), text excerpt, section name. |
| Structural_Suggestion | A recommendation about how the document is organized (move section, split chapter, clarify scope) — NOT what the text should say. |

---

## Requirements

### Requirement 1: Options Panel

**User Story:** As a user, I want to see what analyses are available for my document after the card is shown, so that I can choose what to explore next.

#### Acceptance Criteria

1. WHEN the document card is displayed (status "completed" or "partial"), THE UI SHALL show an "Options Panel" below the card listing the available on-demand analyses.
2. EACH analysis option SHALL display: its name, a one-line description of what it produces, and a status indicator (not_started, in_progress, completed, outdated, failed).
3. WHEN the document classification is "narrative", THE options panel SHALL show only "Questions Answered" and "Conclusions & Recommendations". "Build Index" and "Section Relations" SHALL NOT be shown.
4. WHEN the document classification is NOT "narrative" (normative, guide, manual, procedure, technical, other), THE options panel SHALL show all four analysis types.
5. WHEN the document card has status "partial" (no classification available), THE options panel SHALL show all four analysis types (assume non-narrative until classification is confirmed).
6. EACH analysis option with status "not_started" SHALL render as a clickable action button that triggers the analysis.
7. EACH analysis option with status "completed" SHALL render as a navigable link to view results.
8. EACH analysis option with status "in_progress" SHALL show a loading indicator and be non-interactive.
9. EACH analysis option with status "outdated" SHALL display a warning indicator and offer both "View results" and "Re-analyze" actions.
10. EACH analysis option with status "failed" SHALL display an error indicator and a "Retry" button.

**Traceability:**
- ADR-007 Section 6: "Panel de opciones con los análisis disponibles."
- ADR-007 Section 3: Classification adapts available options.
- PRD v2 Flow step 6: "El usuario ve un panel de opciones."

---

### Requirement 2: Build Index (C3.1)

**User Story:** As a user, I want to generate a structural index of my document so that I can understand how it's organized without reading each section.

#### Acceptance Criteria

1. WHEN the user triggers "Build Index", THE system SHALL send the full document IR to the LLM in a single call and produce a hierarchical tree (structure_tree) where each node represents a section or subsection.
2. EACH node in the structure_tree SHALL contain: `id` (unique identifier), `title` (section heading or inferred label), `level` (hierarchy depth starting at 1), `role` (what this section does: defines, classifies, establishes, regulates, recommends, lists, restricts, describes — or null if undetermined), `question_answered` (the question this section answers in the cascade, e.g., "How are purchases requested?"), and `source_ref`.
3. THE structure_tree SHALL preserve the document's original ordering — nodes appear in document order.
4. THE structure_tree SHALL have a maximum depth of 6 levels. Deeper nesting SHALL be flattened to level 6.
5. THE `role` field identifies what the section DOES functionally (establishes a procedure, defines terms, lists restrictions). If a section's role is inconsistent with the document's overall purpose (e.g., a procedural section inside a normative document), this inconsistency is noted but NOT flagged here — it belongs in Conclusions (Req 5).
6. THE `question_answered` field follows a cascade pattern: level 1 nodes answer broad questions about document purpose ("How is procurement managed?"), deeper levels answer progressively specific questions ("What steps apply when requesting a purchase with return?").
7. THE analysis uses ONE LLM call with the full IR content. No per-section iteration.
8. THE result SHALL be persisted in the database. Subsequent requests on an unchanged document SHALL return the stored result without re-execution.

**Traceability:**
- PRD v2 C3.1: "produce un árbol de estructura"
- ADR-007 Section 2: DocumentStructure.structure_tree definition

---

### Requirement 3: Section Relations (C3.2)

**User Story:** As a user, I want to see how different sections of my document relate to each other so that I can understand dependencies and connections.

#### Acceptance Criteria

1. WHEN the user triggers "Section Relations", THE system SHALL send the full document IR to the LLM in a single call and produce a list of relationships between sections.
2. EACH relationship SHALL contain: `source_section` (title or id of the originating section), `target_section` (title or id of the related section), `type` (one of: constrains, depends_on, complements, contradicts), `description` (one-sentence explanation in `ui_language`), and `source_ref`.
3. THE relationship type vocabulary is: `constrains` (limits or restricts), `depends_on` (requires the other to be understood), `complements` (expands on the same topic), `contradicts` (conflicting content).
4. THE system SHALL focus on significant relationships — obvious or trivial connections (like "chapter 2 follows chapter 1") SHALL be excluded.
5. THE system SHALL produce a reasonable number of relationships proportional to document complexity. No hard cap, but the prompt SHALL instruct the LLM to focus on the most important connections (typically 5-30 for most documents).
6. IF "Build Index" has been executed, THE relationships SHALL reference structure_tree node IDs. If not, they reference section titles or chunk ranges.
7. THE analysis uses ONE LLM call. The result SHALL be persisted and not re-executed on unchanged documents.

**Traceability:**
- PRD v2 C3.2: "Identifica cómo se relacionan las partes del documento"
- ADR-007: constrains, depends_on, complements, contradicts vocabulary

---

### Requirement 4: Questions Answered (C3.3)

**User Story:** As a user, I want to know what questions my document addresses so that I can quickly understand its scope and purpose at different levels of detail.

#### Acceptance Criteria

1. WHEN the user triggers "Questions Answered", THE system SHALL send the full document IR to the LLM in a single call and produce a structured list of questions organized in a cascade.
2. THE cascade structure SHALL have: document-level questions (global purpose: "This document explains how to manage X", "What happens in situation Y"), and section-level questions (chapter/major section scope: "Chapter I answers how to request a purchase", "Section 3 explains what steps to follow for a return").
3. DOCUMENT-LEVEL questions (3-5) SHALL describe the document's overall purpose and scope — what someone would understand after reading the whole document.
4. SECTION-LEVEL questions (1-2 per major section) SHALL describe what each section contributes to the document's purpose — they are more specific than document-level but still summarize the section's objective.
5. THE questions SHALL be well-formed questions in `ui_language`, specific to the content (not generic like "What does this section cover?"). Good examples: "Who is responsible for common area maintenance?", "What restrictions apply to unit modifications?"
6. EACH question SHALL include a `source_ref` pointing to the section/chunk that addresses it.
7. THE analysis uses ONE LLM call. The result SHALL be persisted and not re-executed on unchanged documents.
8. THIS analysis SHALL be available for ALL document classifications including narrative.

**Traceability:**
- PRD v2 C3.3: "Genera una lista de las preguntas que el documento aborda."
- PRD v2: "el diferenciador principal"

---

### Requirement 5: Conclusions & Recommendations (C3.4)

**User Story:** As a user, I want structural observations about my document so that I can understand if its organization is coherent and where it could improve.

#### Acceptance Criteria

1. WHEN the user triggers "Conclusions & Recommendations", THE system SHALL send the full document IR to the LLM in a single call and produce structural observations about the document's organization.
2. THE system SHALL produce observations in these categories:
   - `coherence`: whether sections are consistent with the document's stated purpose (e.g., "Section 5 establishes a procedure, but this is a normative document — it mixes purposes").
   - `reordering`: sections that might benefit from different placement.
   - `duplication`: content that appears repeated.
   - `orphan`: sections that don't connect to the document's main purpose.
   - `missing`: structural elements typically expected for this document type but absent.
3. EACH observation SHALL contain: `category` (from above), `description` (explanation in `ui_language`), `suggestion` (a structural recommendation in `document_language`), `section_ref` (which section(s) the observation refers to), and `source_ref`.
4. THE `suggestion` field SHALL be a STRUCTURAL recommendation (move, split, merge, remove, add section) — NOT a content suggestion about what the text should say. Examples: "Consider moving this section before Chapter II since it defines terms used there" — NOT "This paragraph should mention X."
5. THE `suggestion` is written in `document_language` because it references the document's structure using its own terminology.
6. THE system SHALL produce between 3 and 15 observations, prioritized by structural impact. Trivial or obvious observations SHALL be excluded.
7. THE analysis uses ONE LLM call. The result SHALL be persisted and not re-executed on unchanged documents.
8. THIS analysis SHALL be available for ALL document classifications including narrative.

**Traceability:**
- PRD v2 C3.4: "Observaciones sobre la calidad estructural del documento"
- Language rules steering: suggestions in document_language
- ADR-007 Section 3: Available for narrative documents

---

### Requirement 6: Execution Model

**User Story:** As a developer, I need a consistent, simple execution model across all analysis types.

#### Acceptance Criteria

1. EACH analysis SHALL be executed as a single awaited async operation (not a background task). The endpoint waits for the LLM response and returns the result directly. Rationale: with a single LLM call taking 5-15 seconds, a synchronous response is simpler and avoids polling complexity.
2. WHILE waiting for the LLM response, THE frontend SHALL show the analysis option in "in_progress" state (optimistic UI update before the response arrives).
3. WHEN the analysis completes, THE endpoint SHALL return the full result with status "completed" and the system SHALL persist it.
4. WHEN the analysis fails (LLM error, timeout), THE endpoint SHALL return an error response. The frontend shows the option as "failed" with a retry button. No partial results are saved on failure.
5. WHEN an analysis has already been completed and the document has NOT changed, THE endpoint SHALL return the stored result immediately without calling the LLM (idempotency).
6. WHEN the document is re-uploaded and marked as outdated, ALL existing analysis results for that document SHALL be marked as "outdated".
7. WHEN the user requests re-analysis of an outdated result, THE system SHALL execute fresh and replace the stored result.
8. EACH persisted result SHALL include: `model_id`, `prompt_version`, `created_at`, `updated_at`, and `status`.

**Traceability:**
- ADR-007 Section 4: "No se re-ejecuta si ya existe."
- ADR-007 Section 4: "Se marcan como 'posiblemente desactualizado'."

---

### Requirement 7: API Endpoints

**User Story:** As a frontend client, I need API endpoints to trigger analyses and retrieve results.

#### Acceptance Criteria

1. `POST /api/v1/documents/{document_id}/analyses/{analysis_type}` SHALL trigger the analysis and return the result directly. `analysis_type` is one of: `build_index`, `section_relations`, `questions_answered`, `conclusions`.
2. ON SUCCESS, THE endpoint SHALL return 200 with the full analysis result (including all elements with source_refs).
3. IF the analysis already exists with status "completed" and the document is not outdated, THE endpoint SHALL return 200 with the stored result (no LLM call).
4. IF the document does not exist, THE endpoint SHALL return 404 with error code "document_not_found".
5. IF the document has no IR available, THE endpoint SHALL return 409 with error code "document_not_ready".
6. IF the LLM call fails, THE endpoint SHALL return 502 with error code "analysis_failed" and a message describing the failure.
7. `GET /api/v1/documents/{document_id}/analyses` SHALL return a summary of all analysis statuses for the document: `{ build_index: { status, updated_at }, section_relations: { status, updated_at }, questions_answered: { status, updated_at }, conclusions: { status, updated_at } }`.
8. `GET /api/v1/documents/{document_id}/analyses/{analysis_type}` SHALL return the stored result if completed, or `{ status: "not_started" }` if never executed.
9. ALL endpoints SHALL respect user preferences headers: `Accept-Language`, `X-Model-Preference`, `X-Auto-Fallback`.

**Traceability:**
- PRD v2 Flow steps 7-9
- User Preferences spec (Req 5): Backend propagation

---

### Requirement 8: Results Display

**User Story:** As a user, I want to see analysis results clearly so that I can navigate and understand the insights.

#### Acceptance Criteria

1. WHEN "Build Index" is completed, THE UI SHALL display the structure tree as an expandable/collapsible tree view. Each node shows: title, role badge, and the question it answers. Clicking a node reveals its source_ref.
2. WHEN "Section Relations" is completed, THE UI SHALL display relationships as a list grouped by type (constrains, depends_on, complements, contradicts). Each shows source section → target section, description, and expandable source_ref.
3. WHEN "Questions Answered" is completed, THE UI SHALL display two levels: document-level questions prominently at the top, then section-level questions grouped by their parent section. Each question expands to show source_ref.
4. WHEN "Conclusions & Recommendations" is completed, THE UI SHALL display observations grouped by category with description, structural suggestion, and section reference. A clear visual distinction SHALL separate the structural suggestion from the description.
5. ALL result displays SHALL support keyboard navigation and use ARIA labels for accessibility.
6. WHEN a result is "outdated", THE display SHALL show a banner indicating results may not reflect the current document, with a "Re-analyze" button.
7. THE results display SHALL use shadcn/ui components and follow existing frontend patterns.

**Traceability:**
- ADR-007 Section 6: "Indicador de estado por cada análisis."
- ADR-004: source_ref visible and verifiable
- PRD v2 Flow step 8

---

### Requirement 9: Evidence Traceability

**User Story:** As a user, I want to verify any analysis result by seeing the original text that supports it.

#### Acceptance Criteria

1. EVERY result element (tree node, relationship, question, observation) SHALL include a `source_ref` with: `chunk_ids` (list of IR chunk IDs), `text_excerpt` (the relevant text passage, max 500 characters), and `section` (section name where the text appears).
2. WHEN the user expands a source_ref in the UI, THE system SHALL display the text excerpt with section context.
3. THE source_ref SHALL reference actual text from the document's IR. The system SHALL NOT fabricate references.
4. IF the system cannot identify a source reference for a result, IT SHALL set source_ref to null and mark the element as "unverified" in the UI.

**Traceability:**
- ADR-004: "Trust by Evidence: todo resultado es trazable."
- PRD v2 C7: "Cada afirmación incluye referencia al texto fuente."
