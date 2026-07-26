# Requirements Document

Base Analysis (Análisis Base)

## Introduction

This feature implements the automatic base analysis that runs immediately after a document is ingested. It produces a "document card" — a concise structural summary combining local processing (no LLM) with a short LLM call to the light model (Groq). The card gives the user an immediate understanding of what the document is about, how it's organized, and what type of document it is, all within 5 seconds of upload.

The base analysis is the first level of the progressive analysis model defined in ADR-007. It replaces the previous monolithic Knowledge Model extraction with a fast, two-phase approach: deterministic local processing for structural data, and a single LLM call for summary and classification. The result is persisted as the document's "card" and serves as the foundation for all subsequent on-demand analyses.

This feature covers PRD v2 capability C2 (Análisis base) and ADR-007 "Nivel 1 — Análisis base."

## Relevant Documentation

- #[[file:docs/product/03-prd v2.md]]
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-003-document-ingestion.md]]
- #[[file:src/backend/app/ingestion/service.py]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/backend/app/models/document.py]]

## Feature Boundaries

**In scope:**
- Automatic trigger of base analysis after successful document ingestion.
- Local processing (no LLM): title extraction, statistics computation, organization type detection, existing index detection, file metadata assembly.
- LLM processing (light model): document summary (2-3 lines) and classification.
- DocumentCard model and database persistence.
- Graceful degradation: partial card (local-only) when LLM fails.
- Retry mechanism for LLM-only re-execution on partial cards.
- API endpoints: GET card, POST retry-llm.
- Frontend: card display component with loading, partial, and complete states.
- Change detection by file metadata (size_bytes, last_modified).
- Prompt versioning for the LLM call.

**Out of scope (belongs to other features or future iterations):**
- On-demand analyses (build index, relationships, questions, conclusions) — separate spec (C3).
- Document structure tree visualization — depends on "Build Index" analysis (C3.1).
- LLM selector UI — separate spec (C5).
- Block-level analysis — separate spec (C4).
- Change detection by content hash — deferred beyond MVP.
- Multi-document analysis.
- Natural language queries over the card.

## Glossary

| Term | Definition |
|------|------------|
| Document_Card | The structured summary produced by the base analysis: title, summary, classification, statistics, organization type, file metadata, and status. Persisted in the `document_cards` table. |
| Base_Analysis | The first level of progressive analysis (ADR-007 Nivel 1). Combines local processing with a single LLM call to produce the Document_Card in < 5 seconds. |
| Local_Processing | The deterministic phase of base analysis that extracts structural information from the IR without any network or LLM calls. |
| LLM_Processing | The phase that sends a short prompt (~500 tokens of context) to the light model (Groq) to obtain a summary and classification. |
| Organization_Type | How the document is structurally organized: numbered articles, headed sections, hierarchical numbering, or free-form. |
| Document_Classification | The functional category of the document: normative, guide, manual, procedure, technical, narrative, or other. Determines which on-demand analyses are relevant. |
| Partial_Card | A Document_Card with status="partial" that contains only local processing results (title, statistics, organization type, file metadata) because the LLM call failed or timed out. |
| IR | Intermediate Representation — the format-agnostic structured text produced by the ingestion layer (ADR-003). The base analysis operates exclusively on this. |
| Light_Model | The LLM model tier used for base analysis (currently Groq Llama 3.3 70B via LiteLLM), optimized for speed on simple tasks. |

---

## Requirements

### Requirement 1: Automatic Trigger

**User Story:** As a user, I want the base analysis to execute automatically when I upload a document so that I see the document card without any additional action.

#### Acceptance Criteria

1. WHEN a document completes ingestion with status "ready", THE system SHALL automatically trigger the base analysis for that document without requiring any additional user interaction beyond the processing consent already granted during upload (ADR-005).
2. WHEN the base analysis is triggered, THE system SHALL execute it asynchronously (as a background task) so that the upload API response is returned immediately without waiting for the analysis to complete.
3. IF a Document_Card with status "completed" already exists for the document and the document's file metadata (size_bytes) has not changed, THEN THE system SHALL NOT re-execute the base analysis and SHALL return the existing card.
4. IF the base analysis fails for any reason, THE document's ingestion status SHALL remain "ready" — the failure does not affect the document record itself.

**Traceability:**
- PRD v2 C2: "Al cargar un documento, el sistema produce automáticamente en < 5 segundos."
- PRD v2 Flow step 4: "El sistema ejecuta el análisis base (< 5 segundos)."
- ADR-007 Nivel 1: "Se ejecuta automáticamente al cargar el documento."
- ADR-005: Consent already granted during upload covers this processing.

---

### Requirement 2: Local Processing

**User Story:** As a user, I want to see structural information about my document instantly so that I can understand its organization even if the AI service is unavailable.

#### Acceptance Criteria

1. WHEN the base analysis executes its local processing phase on a document's IR, THE system SHALL extract the document title by: (a) using the first heading found in the IR chunks' `structural_context.section` field, or (b) if no heading exists, using the original filename without its file extension.
2. WHEN the local processing phase computes statistics, THE system SHALL produce: the total number of chunks in the IR, the count of unique sections detected (distinct values of `structural_context.section`), and the maximum hierarchy level found (from `structural_context.level` fields, defaulting to 1 if no levels are present).
3. WHEN the local processing phase detects the organization type, THE system SHALL classify the document as one of: `numbered_articles` (when chunks contain patterns matching `Art.\s*\d+`, `Artículo\s+\d+`, or `ARTICULO`), `headed_sections` (when chunks have `structural_context.level` values indicating heading hierarchy), `hierarchical_numbering` (when chunks contain patterns matching `\d+\.\d+` numbering schemes), or `free_form` (when none of the above patterns are detected). The first matching pattern in priority order (numbered_articles > headed_sections > hierarchical_numbering > free_form) determines the type.
4. WHEN the local processing phase checks for an existing index, THE system SHALL detect the presence of a table of contents by identifying chunks in the first 20% of the document that contain patterns characteristic of an index: short lines with trailing page numbers, lines with repeated dots or dashes as separators, or chunks whose `structural_context.section` contains terms like "índice", "contenido", "table of contents", or "contents" (case-insensitive).
5. WHEN the local processing phase assembles file metadata, THE system SHALL include: `size_bytes` from the IR metadata, `format` from the IR metadata (markdown, plain_text, or pdf), and `language` from the IR metadata (es, en, or unknown).
6. THE local processing phase SHALL NOT make any network calls, LLM calls, or external service calls. It operates exclusively on the in-memory IR data.
7. THE local processing phase SHALL complete in under 100 milliseconds for documents up to 10 MB (the maximum supported file size).

**Traceability:**
- ADR-007 Nivel 1 "Sin LLM (instantáneo)": title, statistics, organization type, hierarchy levels, existing index, file metadata.
- PRD v2 C2: "Estadísticas: número de páginas, bloques/párrafos, secciones detectadas."
- ADR-003: IR as the sole input for analysis.

---

### Requirement 3: LLM Processing

**User Story:** As a user, I want a brief summary and classification of my document so that I can understand its purpose and type at a glance.

#### Acceptance Criteria

1. WHEN the base analysis executes its LLM processing phase, THE system SHALL send a single prompt to the light model (via `LLMClient.call(prompt, model_tier="light", temperature=0.1)`) containing: the detected title, the detected organization type, and a text sample from the document (concatenated text of up to the first 10 IR chunks, truncated to a maximum of 2000 characters).
2. WHEN the LLM responds successfully, THE system SHALL parse the response to extract: a `summary` field containing 2-3 lines describing what the document is about and its objective, and a `classification` field containing one of: normative, guide, manual, procedure, technical, narrative, or other.
3. IF the LLM call does not complete within 10 seconds, THEN THE system SHALL cancel the call and treat it as a failure — proceeding to create a partial card without summary or classification.
4. IF the LLM call fails for any reason (timeout, rate limit, service error, network error, authentication error), THEN THE system SHALL log the failure and proceed to create a partial card without summary or classification. The failure SHALL NOT propagate as an exception to the caller.
5. IF the LLM response cannot be parsed as valid JSON with the expected fields (summary and classification), THEN THE system SHALL treat it as a failure and proceed to create a partial card.
6. THE LLM prompt SHALL be stored in a dedicated module with a `PROMPT_VERSION` constant (initial value: "base-analysis-v1") that is recorded in the Document_Card for auditability.
7. THE system SHALL NOT send user metadata, account information, session history, or any data beyond the document text sample and the system prompt to the LLM (ADR-005 minimization).

**Traceability:**
- ADR-007 Nivel 1 "Con LLM (una llamada corta, modelo ligero)": summary 2-3 lines, classification.
- PRD v2 C2: "Resumen: bloque de 2-3 líneas", "Clasificación: qué tipo de documento es."
- ADR-007 Risks: "Usar modelo ligero (Groq), prompt mínimo (~500 tokens), timeout de 10s."
- ADR-005: Minimization — only text + prompts sent.

---

### Requirement 4: Document Card Persistence

**User Story:** As a user, I want the analysis results saved so that I don't have to wait for re-analysis when I return to a document.

#### Acceptance Criteria

1. WHEN the base analysis completes (either fully or partially), THE system SHALL persist the Document_Card to the database with all available fields. The card is associated with the document via `document_id` (unique constraint — one card per document).
2. WHEN a Document_Card is persisted, IT SHALL include: `id` (UUID), `document_id` (FK), `title`, `summary` (null if partial), `classification` (null if partial), `organization_type`, `statistics` (JSON object with total_chunks, sections_detected, hierarchy_levels, has_existing_index), `file_metadata` (JSON object with size_bytes, format, language), `status` ("completed", "partial", or "failed_llm"), `model_id` (the LLM model identifier that produced the summary, null if partial), `prompt_version` (null if partial), `created_at`, and `updated_at`.
3. WHEN a Document_Card already exists for a document and a new analysis is triggered (due to document change or explicit retry), THE system SHALL update the existing record (upsert semantics) rather than creating a duplicate.
4. WHEN a partial card exists and the user triggers an LLM retry that succeeds, THE system SHALL update the existing card's `summary`, `classification`, `model_id`, `prompt_version`, `status` (to "completed"), and `updated_at` fields without modifying the local processing fields.

**Traceability:**
- ADR-007 Section 4 "Persistencia y capas acumulativas": "El análisis base se guarda siempre como la ficha del documento."
- PRD v2 C6: "Todo análisis completado se guarda y no se re-ejecuta al volver."
- PRD v2 Flow step 10: "Al volver al documento, todo lo previamente analizado está disponible sin re-ejecutar."

---

### Requirement 5: Performance

**User Story:** As a user, I want to see the document card within 5 seconds of uploading so that I get immediate value from the system.

#### Acceptance Criteria

1. WHEN the base analysis executes under normal conditions (LLM service available, response time < 3 seconds), THE total elapsed time from trigger to persisted card SHALL be less than 5 seconds.
2. IF the LLM response time exceeds 10 seconds, THEN THE system SHALL timeout the LLM call and persist a partial card. The partial card (local data only) SHALL be available within 1 second of the analysis trigger.
3. WHEN the system persists a partial card due to LLM failure, THE partial card SHALL contain all local processing results (title, statistics, organization type, file metadata) and SHALL be immediately usable by the frontend.
4. THE system SHALL NOT block the upload response waiting for the base analysis to complete. The upload returns immediately; the card becomes available asynchronously.

**Traceability:**
- PRD v2 C2: "Al cargar un documento, el sistema produce automáticamente en < 5 segundos."
- ADR-007 Nivel 1: "Análisis base (automático, rápido, < 5 segundos)."
- ADR-007 Risks: "Si falla, mostrar solo la parte sin LLM."

---

### Requirement 6: Change Detection

**User Story:** As a user, I want to know when a document has changed since its last analysis so that I can decide whether to re-analyze it.

#### Acceptance Criteria

1. WHEN a document is re-uploaded and its `size_bytes` differs from the value stored in the existing Document_Card's `file_metadata.size_bytes`, THE system SHALL mark the existing card as "possibly outdated" by setting an `outdated` flag or equivalent indicator.
2. WHEN a card is marked as possibly outdated, THE system SHALL NOT automatically re-execute the base analysis. The user must explicitly request re-analysis.
3. WHEN the user requests re-analysis of an outdated card, THE system SHALL execute the full base analysis (local + LLM) and update the card with new results, clearing the outdated indicator.

**Traceability:**
- ADR-007 Section 4: "Si el documento cambia (detectable por last_modified + size_bytes), los análisis previos se marcan como 'posiblemente desactualizado'. El usuario decide si re-ejecutar."
- PRD v2 C6: "Si el documento cambia, los análisis se marcan como 'posiblemente desactualizado'."

---

### Requirement 7: API Endpoints

**User Story:** As a frontend client, I need API endpoints to retrieve the document card and retry failed LLM analysis so that I can build the card display UI.

#### Acceptance Criteria

1. WHEN `GET /api/v1/documents/{document_id}/card` is called for a document that has a persisted Document_Card, THE API SHALL return 200 with the full card object serialized as JSON (all fields from Requirement 4 criterion 2).
2. WHEN `GET /api/v1/documents/{document_id}/card` is called for a document that exists but has no card yet (analysis still in progress or not triggered), THE API SHALL return 404 with an error body containing error code "card_not_found" and a message indicating the card is not yet available.
3. WHEN `GET /api/v1/documents/{document_id}/card` is called with a document_id that does not correspond to any existing document, THE API SHALL return 404 with an error body containing error code "document_not_found".
4. WHEN `POST /api/v1/documents/{document_id}/card/retry-llm` is called for a document whose card has status "partial" or "failed_llm", THE API SHALL re-execute only the LLM processing phase and return 200 with the updated card.
5. WHEN `POST /api/v1/documents/{document_id}/card/retry-llm` is called for a document whose card has status "completed", THE API SHALL return 409 with an error body containing error code "card_already_complete" and a message indicating the card does not need LLM retry.
6. WHEN `POST /api/v1/documents/{document_id}/card/retry-llm` is called for a document with no existing card, THE API SHALL return 404 with an error body containing error code "card_not_found".

**Traceability:**
- PRD v2 Flow steps 4-5: System executes analysis and shows card.
- ADR-007 Risks: "Si falla, mostrar solo la parte sin LLM" (retry mechanism).

---

### Requirement 8: Frontend Display

**User Story:** As a user, I want to see the document card immediately after upload with clear visual indicators of its state so that I understand what information is available and what might be pending.

#### Acceptance Criteria

1. WHEN a document upload completes successfully, THE UI SHALL display a loading skeleton for the document card and begin polling `GET /card` every 1.5 seconds until the card is available (maximum 10 attempts, 15 seconds total).
2. WHEN the card is retrieved with status "completed", THE UI SHALL display: the document title prominently, the 2-3 line summary, the classification as a badge/chip, the organization type, statistics (total chunks, sections detected, hierarchy levels, has existing index), and file metadata (size, format, language).
3. WHEN the card is retrieved with status "partial", THE UI SHALL display: all local processing fields (title, organization type, statistics, file metadata) and a clearly labeled action button ("Reintentar análisis" / "Retry analysis") in place of the summary and classification areas. The UI SHALL NOT display empty or placeholder text for the missing fields.
4. WHEN the user clicks the retry button on a partial card, THE UI SHALL call the retry-llm endpoint, display a loading indicator on the retry area, and update the card display with the new results upon success.
5. IF polling exhausts all 10 attempts without receiving a card, THE UI SHALL display an informational message indicating the analysis is taking longer than expected and offer a manual retry button.
6. THE document card component SHALL use shadcn/ui components (Card, Badge, Button, Skeleton) and follow existing frontend patterns (Tailwind CSS, React + TypeScript, Zustand store).
7. THE document card component SHALL be accessible: all interactive elements are keyboard-navigable, loading states are announced via ARIA live regions, and badge/chip elements use sufficient color contrast (WCAG 2.1 AA minimum 4.5:1 for text).

**Traceability:**
- ADR-007 Section 6 "Interfaz de usuario": "Ficha del documento visible inmediatamente tras la carga."
- PRD v2 Flow step 5: "Se muestra la ficha del documento."
- PRD v2 C2: Card fields specification.
