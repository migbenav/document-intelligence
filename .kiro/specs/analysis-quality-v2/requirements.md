# Requirements Document

Analysis Quality v2 (Mejora de Calidad del Análisis)

## Introduction

This feature overhauls the on-demand analysis engine to produce results that reflect the document's functional purpose rather than its visual/heading structure. The current implementation (C3 v1) lists headings as-is, generates content-level questions instead of purpose-level questions, and produces incoherent recommendations that compare unrelated domains. This redesign addresses those fundamental quality gaps.

The core insight: this application analyzes documents to understand their PURPOSE and STRUCTURE as an instrument (normative, procedural, narrative), not to summarize their content. A section's value lies in what it DOES functionally (defines, restricts, enables, controls), not in what it says textually.

Additionally, this feature fixes critical operational issues: the frontend does not show which LLM model actually responded, quota errors are indistinguishable from other failures, language detection fails on certain documents, and the model selector does not always propagate correctly.

## Relevant Documentation

- #[[file:.kiro/specs/on-demand-analysis/design.md]]
- #[[file:.kiro/specs/on-demand-analysis/requirements.md]]
- #[[file:.kiro/specs/base-analysis/design.md]]
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:src/backend/app/analysis/on_demand/prompts/build_index.py]]
- #[[file:src/backend/app/analysis/on_demand/prompts/questions_answered.py]]
- #[[file:src/backend/app/analysis/on_demand/prompts/conclusions.py]]
- #[[file:src/backend/app/analysis/on_demand/prompts/section_relations.py]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/backend/app/analysis/on_demand/service.py]]
- #[[file:src/backend/app/ingestion/language.py]]
- #[[file:src/frontend/src/components/layout/Sidebar.tsx]]

## Feature Boundaries

**In scope:**
- Redesign of all four analysis prompts (build_index, questions_answered, conclusions, section_relations) to focus on functional/purpose analysis.
- Propagation of the actual LLM model_id (from the response) to the frontend.
- Classification of LLM errors (quota vs timeout vs auth) with clear user-facing messages.
- Addition of more LLM models to the selector (Gemini 2.5 Pro, Groq Llama 4 Maverick).
- Fix fallback model configuration (currently all three defaults point to Gemini).
- Improvement of language detection for edge cases.
- Passing document classification as input to on-demand analyzers.
- Updated Pydantic models and TypeScript types to support new result structures.

**Out of scope:**
- UI layout redesign (separate spec: analysis-workspace-ui).
- Navigation between documents (separate spec).
- Block-level analysis (C4).
- Multi-document comparison.
- New analysis types beyond the existing four.

## Glossary

| Term | Definition |
|------|------------|
| Functional_Structure | The logical organization of a document by what each part DOES (defines, restricts, enables, controls), as opposed to its visual heading structure. |
| Purpose_Questions | Questions that reveal the document's logical flow or coverage — what the document establishes as an instrument — not summaries of section content. |
| Domain | A coherent topic area within a document (e.g., "parking rules", "elevator usage"). Contradictions are only meaningful within the same domain. |
| Purpose_Mismatch | When content in a section does not match the document's declared type (e.g., a procedure inside a normative document). |
| Model_Id_Real | The actual LLM model that produced a response (from LLMResponse.model_id), which may differ from the requested model if fallback was triggered. |

---

## Requirements

### Requirement 1: Build Index — Functional Comprehension

**User Story:** As a user, I want the structure analysis to reveal how my document is functionally organized (what it does, not just what it's titled), so I can understand the logical groupings even when they don't match the heading structure.

#### Acceptance Criteria

1. WHEN "Build Index" is executed, THE system SHALL identify the document's FUNCTIONAL ORGANIZATION — grouping content by what it does (purpose, scope, execution, control, etc.) rather than just listing headings.
2. EACH top-level node in the structure tree SHALL represent a functional grouping (e.g., "Propósito y alcance", "Ejecución", "Control y pago") — NOT necessarily a chapter or heading from the document.
3. EACH node SHALL include a field `original_headings: list[str]` that maps back to the actual document headings/chapters that belong to this functional group.
4. WHEN multiple document sections serve the same functional purpose (e.g., mission, vision, objectives all define purpose), THE system SHALL group them under a single functional node.
5. THE `question_answered` field SHALL describe the FUNCTIONAL CONTRIBUTION of the section (e.g., "How is spending controlled?") — NOT a content summary (e.g., NOT "What does chapter 5 say?").
6. THE `role` vocabulary SHALL be expanded to include: `enables`, `restricts`, `controls`, `delegates`, `defines`, `classifies`, `establishes`, `describes`.
7. THE system SHALL first identify the document's overall purpose and type before building the tree, using the classification from the document card if available.
8. THE result SHALL preserve source_refs for traceability.

**Traceability:**
- Replaces Req 2 from on-demand-analysis spec
- ADR-007 structural analysis redesign

---

### Requirement 2: Questions Answered — Document Logic

**User Story:** As a user, I want the questions to reveal the logical flow or coverage of my document (what decisions it enables, what it regulates, what sequence it establishes), not a list of "what each section talks about."

#### Acceptance Criteria

1. WHEN "Questions Answered" is executed, THE system SHALL produce questions that reveal the document's LOGICAL CHAIN or COVERAGE — adapted to the document type.
2. FOR normative documents (rules, policies): questions SHALL follow patterns like "What is permitted? → What is prohibited? → Who enforces it? → What happens on non-compliance?"
3. FOR procedural documents: questions SHALL follow patterns like "Can it be done? → Who decides? → How is it executed? → How is it controlled/paid?"
4. FOR narrative documents: questions SHALL follow patterns like "What is the subject? → What sequence does it follow? → What conclusion does it reach?"
5. THE system SHALL receive the document's classification (from base analysis card) as input and adapt the question style accordingly.
6. IF the document lacks a coherent logic, THE system SHALL include a `coherence_note` field alerting that the document does not follow a clear logical structure.
7. QUESTIONS SHALL NOT be generic (e.g., "What does this section cover?") — they must be SPECIFIC and reveal PURPOSE (e.g., "Who approves expenses above the monthly limit?").
8. THE cascade structure remains: 3-5 document-level questions (logical chain) + section-level questions (what each part contributes to the chain).
9. THE result SHALL preserve source_refs for traceability.

**Traceability:**
- Replaces Req 4 from on-demand-analysis spec
- User example: "Políticas de Gestión del Gasto" → "¿Puede hacerse? → ¿Quién lo decide? → ¿Cómo se ejecuta? → ¿Cómo se paga y se controla?"

---

### Requirement 3: Conclusions — Coherent Domain-Aware Recommendations

**User Story:** As a user, I want structural recommendations that detect real problems: content that doesn't belong (wrong purpose for the document type), paragraphs in the wrong place, titles that don't reflect content, and contradictions within the same topic — not false alerts comparing unrelated domains.

#### Acceptance Criteria

1. WHEN "Conclusions" is executed, THE system SHALL first identify the DOMAINS/TOPICS in the document (e.g., "parking", "elevators", "common areas") and only find contradictions WITHIN the same domain.
2. THE system SHALL detect PURPOSE MISMATCHES: content whose type doesn't match the document's declared classification (e.g., a procedure paragraph inside a normative document).
3. THE system SHALL detect MISPLACED CONTENT: paragraphs that would be better placed in a different section based on semantic affinity and topic distance.
4. THE system SHALL detect TITLE MISMATCHES: headings that do not reflect the actual content of their section.
5. THE system SHALL detect SEQUENCE ISSUES: content that appears in an illogical order (e.g., prerequisites described after execution steps).
6. THE observation categories SHALL be: `purpose_mismatch`, `misplaced_content`, `title_mismatch`, `sequence_issue`, `duplication`, `contradiction`.
7. THE system SHALL require the document classification as input. For narrative documents, focus on logical sequence rather than purpose compliance.
8. THE system SHALL NOT produce false contradictions between independent domains (e.g., parking rules vs elevator rules are NOT contradictory).
9. EACH observation SHALL include `suggestion` in `document_language` — a STRUCTURAL recommendation (move, split, rename, remove) — NOT a content suggestion about what the text should say.
10. THE system SHALL produce 3-15 observations, prioritized by structural impact.

**Traceability:**
- Replaces Req 5 from on-demand-analysis spec
- User example: "alertaba de una contradicción entre reglas de estacionamientos con reglas para ascensores" — this should NOT happen

---

### Requirement 4: Section Relations — Functional Connections

**User Story:** As a user, I want to see how parts of my document relate functionally (what enables what, what restricts what), not trivial sequential relationships.

#### Acceptance Criteria

1. WHEN "Section Relations" is executed, THE system SHALL identify FUNCTIONAL relationships between document sections.
2. THE relationship types SHALL be: `enables` (one section permits/allows what another regulates), `restricts` (one limits what another enables), `requires` (prerequisite dependency), `implements` (one details what another declares), `contradicts` (conflicting content within the same domain).
3. THE system SHALL only flag `contradicts` between sections that address the SAME domain/topic.
4. THE system SHALL NOT produce trivial relationships (e.g., "section 2 follows section 1", "chapter 3 is next").
5. IF "Build Index" v2 has been executed, THE system SHALL use the functional groupings as reference for relationships.
6. THE result SHALL preserve source_refs for traceability.

**Traceability:**
- Replaces Req 3 from on-demand-analysis spec

---

### Requirement 5: Model Transparency and Error Classification

**User Story:** As a user, I want to know which LLM model actually produced each analysis result, and when it fails due to quota exhaustion I want a clear message telling me to switch models — not a generic error.

#### Acceptance Criteria

1. THE backend SHALL propagate the ACTUAL model_id from `LLMResponse.model_id` (not the requested model) through to the persisted `AnalysisRecord` and API response.
2. WHEN an LLM call fails due to rate limit / quota exhaustion (HTTP 429 or "quota" in error), THE system SHALL classify it as `quota_exhausted` error with a message indicating which model hit its quota.
3. WHEN the system falls back to another model, THE response SHALL include `fallback_used: true` and both `requested_model` and `actual_model` fields.
4. THE frontend SHALL display a badge on each analysis result showing which model produced it.
5. THE frontend SHALL display differentiated error messages:
   - Quota: "Se agotó la cuota de [modelo]. Seleccione otro modelo o espere."
   - Timeout: "El análisis tardó demasiado. Intente con un modelo más rápido."
   - Auth: "Error de credenciales para [modelo]. Verifique la configuración."
6. THE API error response SHALL include: `error_code` (quota_exhausted | timeout | auth_error | analysis_failed), `model_id` (which model failed), and `message`.

**Traceability:**
- User report: "sigue usando Gemini y falla cuando llega a la cuota, debería haber un mensaje"
- Current bug: `_dispatch_analyzer` returns `model_override` instead of `response.model_id`

---

### Requirement 6: Model Selection and Fallback Configuration

**User Story:** As a user, I want more model options available and I want the fallback to actually use a DIFFERENT provider when the primary fails.

#### Acceptance Criteria

1. THE available models in the sidebar selector SHALL include: Default (task-assigned), Gemini 2.5 Flash, Gemini 2.5 Pro, Groq Llama 3.3 70B, Groq Llama 4 Maverick.
2. THE `DEFAULT_FALLBACK_MODEL` SHALL be configured to a DIFFERENT provider than `DEFAULT_PRIMARY_MODEL`. If primary is Gemini, fallback SHALL be Groq (and vice-versa).
3. WHEN the user selects a specific model and it fails, THE fallback SHALL use a model from a DIFFERENT provider — not the same model again.
4. THE system SHALL log which model was requested, which responded, and whether fallback was triggered.
5. THE frontend model selector SHALL show brief descriptions of each model's characteristics (speed, context window, cost tier).

**Traceability:**
- User report: "tengo seleccionado el modelo groq pero parece que sigue usando Gemini"
- Current config: all three defaults are "gemini/gemini-2.5-flash"

---

### Requirement 7: Language Detection Improvement

**User Story:** As a user, I want the system to correctly identify my document's language even when it contains technical terms in another language or has limited prose content.

#### Acceptance Criteria

1. THE language detector SHALL expand its sample to 2000 characters (currently 1000).
2. THE language detector SHALL strip numbers, URLs, code-like content, and isolated technical terms before counting stopwords.
3. WHEN the local detector returns UNKNOWN or low confidence, THE base analysis LLM call SHALL explicitly request language confirmation/correction.
4. THE confirmed language (from LLM) SHALL be stored in the document_card and propagated to on-demand analyses.
5. THE system SHALL support at minimum: Spanish, English, Portuguese, and French detection.

**Traceability:**
- User report: "No identifica correctamente el lenguaje en algunos documentos"
- Current limitation: only supports es/en with 1000 char sample

---

### Requirement 8: Classification as Analysis Input

**User Story:** As a developer, I need all on-demand analyzers to receive the document's classification so they can adapt their behavior to the document type.

#### Acceptance Criteria

1. THE `OnDemandAnalysisService.execute()` SHALL load the document_card before executing any analyzer.
2. THE `classification` field from the document_card SHALL be passed to every analyzer as part of the preferences/context.
3. EACH analyzer's prompt SHALL include the document classification and adapt instructions accordingly.
4. IF no classification is available (partial card), THE system SHALL default to "generic" classification.
5. THE `document_language` from the card SHALL also be passed for conclusions (suggestion language).

**Traceability:**
- Dependency for Req 1-4: all prompts need to know the document type
- Current gap: analyzers don't receive classification
