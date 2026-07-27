# Implementation Plan: Document Card Redesign (Rediseño de la Card de Documento)

## Overview

Redesign the Document Card to separate instant local analysis (Ficha Técnica) from LLM-generated content (Contenido). Add lingua-py for language detection, textstat for readability metrics, a 4-level classification taxonomy with confidence scoring, and a two-section card layout with collapsibles and tooltips. Maximum 6 tasks as specified. Tests are consolidated in the final task.

## Tasks

- [ ] 1. Add dependencies and create classification/text-stats models
  - [ ] 1.1 Add new dependencies to pyproject.toml
    - Add `lingua-language-detector>=2.0.0` and `textstat>=0.7.0` to project dependencies in `src/backend/pyproject.toml`
    - _Requirements: Req 1, Req 2_

  - [ ] 1.2 Create classification models
    - Create `src/backend/app/models/classification.py` with: `ClassificationScope` enum (institutional, governmental, private, other), `ClassificationPurpose` enum (normative, operational, informational, evidentiary, contractual), `ClassificationGenre` enum (prescriptive, instructive, expository, registral, bilateral), `ClassificationFormat` enum (regulation, policy, manual, procedure, protocol, guide, minutes, contract, other), `DocumentClassificationResult` model (scope, purpose, genre, format, descriptor, per-level confidences, aggregated confidence, display_chain_es)
    - Include bilingual label mappings (SCOPE_LABELS_ES, PURPOSE_LABELS_ES, GENRE_LABELS_ES, FORMAT_LABELS_ES)
    - Include `build_display_chain_es()` method that produces "Institucional → Normativo → Prescriptivo → Reglamento (85%)"
    - _Requirements: Req 3 (criteria 1, 2, 5)_

  - [ ] 1.3 Create TextStats model and update DocumentCard
    - Create `TextStats` Pydantic model in `src/backend/app/models/document_card.py` (or classification.py): word_count, sentence_count, paragraph_count, readability_score, readability_label, readability_formula
    - Update `DocumentCard` model with new nullable fields: `text_stats: TextStats | None = None`, `classification_result: DocumentClassificationResult | None = None`, `topics: list[str] = []`, `audience: str | None = None`, `lifecycle: Literal["living", "frozen"] = "living"`, `is_corporate: bool = True`
    - Keep existing `classification` field for backward compatibility
    - _Requirements: Req 1, Req 9 (criteria 1, 3)_

  - [ ] 1.4 Update frontend TypeScript interfaces
    - Update `src/frontend/src/types/documentCard.ts` with: `TextStats` interface, `ClassificationResult` interface (with displayChainEs), new optional fields on `DocumentCard` (textStats, classificationResult, topics, audience, lifecycle, isCorporate)
    - Ensure all new fields are optional (backward compat with existing cards)
    - _Requirements: Req 5 (criterion 8), Req 9 (criterion 2)_

- [ ] 2. Implement TextStatsAnalyzer and rewrite language detection
  - [ ] 2.1 Create TextStatsAnalyzer module
    - Create `src/backend/app/analysis/base_analysis/text_stats_analyzer.py`
    - Implement `TextStatsAnalyzer` class with `analyze(text: str, language: str) -> TextStats`
    - Word count: `len(text.split())` (native Python)
    - Sentence count: via textstat `sentence_count()`
    - Paragraph count: count double-newline separated blocks
    - Readability: `textstat.fernandez_huerta(text)` for Spanish, `textstat.flesch_reading_ease(text)` for English, raw Flesch for others
    - Label mapping with strict boundary validation: score > 80 "Muy fácil", score > 60 AND ≤ 80 "Fácil", score > 40 AND ≤ 60 "Normal", score > 20 AND ≤ 40 "Difícil", score ≤ 20 "Muy difícil"
    - Handle edge cases: empty text → all zeros, label "No disponible"
    - _Requirements: Req 1 (criteria 1-5)_

  - [ ] 2.2 Rewrite language detection with lingua-py
    - Rewrite `src/backend/app/ingestion/language.py` to use lingua-py (`LanguageDetectorBuilder`)
    - Build detector for minimum set: Spanish, English, Portuguese, French, German, Italian (expandable)
    - Detect on first 5000 characters of text
    - Return ISO 639-1 code (e.g., "es", "en", "pt")
    - If confidence below 30%: return "Indeterminado ({code}, {confidence}%)" — NEVER "Unknown"
    - If detection times out (>100ms), retry with progressively smaller text samples (2500, 1000 characters)
    - Complete in <100ms
    - _Requirements: Req 2 (criteria 1-5)_

- [ ] 3. Update LocalAnalyzer v2 with hints and integrate new modules
  - [ ] 3.1 Update LocalAnalyzer to use lingua-py and TextStatsAnalyzer
    - Modify `src/backend/app/analysis/base_analysis/local_analyzer.py`
    - Replace manual language detection call with new lingua-py based detector
    - Add TextStatsAnalyzer as a dependency, call it during `analyze()`
    - Return `LocalAnalysisResultV2` (extends original with `text_stats` and `classification_hints`)
    - Ensure total local analysis completes in <200ms
    - _Requirements: Req 1 (criterion 2), Req 2 (criterion 5)_

  - [ ] 3.2 Implement classification hint generation
    - Add `_generate_classification_hints(title, organization_type) -> ClassificationHints` method to LocalAnalyzer
    - Implement pattern matching rules: "reglamento|regulación|norma" → institutional/normative/prescriptive/regulation, "manual" → operational/instructive/manual, "procedimiento|proceso" → operational/instructive/procedure, "protocolo" → operational/instructive/protocol, "guía|guia" → operational/instructive/guide, "acta" → evidentiary/registral/minutes, "contrato|convenio|acuerdo" → contractual/bilateral/contract, "política|politica|policy" → normative/prescriptive/policy
    - Organization type "numbered_articles" → genre:prescriptive
    - Implement `is_corporate` logic: corporate by default, private only if explicitly personal/private patterns detected
    - If no patterns match: return empty hints (all None)
    - _Requirements: Req 6 (criteria 1-5)_

- [ ] 4. Update LLMAnalyzer v3 with prompt v3 and classification parsing
  - [ ] 4.1 Create prompt v3
    - Create `src/backend/app/analysis/base_analysis/prompts_v3.py`
    - Define `PROMPT_VERSION = "card-redesign-v3"`
    - Define `PROMPT_TEMPLATE_V3` that requests JSON with: `summary` (2-3 lines), `classification` object (scope, purpose, genre, format, descriptor, per-level confidence 0-100), `topics` (list of 3-5 keywords), `audience` (string), `lifecycle` ("living" or "frozen")
    - Include hints section: "Suggested classification based on local analysis: {hints}. You may override if content disagrees."
    - Include language and document size category as context
    - Do NOT request language, word count, readability, or any local stats
    - _Requirements: Req 4 (criteria 1-3, 6)_

  - [ ] 4.2 Update LLMAnalyzer to v3
    - Modify `src/backend/app/analysis/base_analysis/llm_analyzer.py`
    - Update `analyze()` signature to accept `hints: ClassificationHints` and `language: str`
    - Build prompt using `PROMPT_TEMPLATE_V3` with hints context
    - Parse response JSON for: summary, classification (4 levels + confidences), topics, audience, lifecycle
    - Distinguish between malformed JSON (LLM failure → partial card) and valid JSON with wrong schema (system error → partial card with different error classification for debugging)
    - Validate classification levels against enums: invalid values default to "other" with confidence=0
    - Compute aggregated confidence: `min(level_confidences)` ± hint agreement (+10 if agree, -10 if disagree, capped to [10, 99])
    - Build `DocumentClassificationResult` with `display_chain_es`
    - Determine lifecycle: format in [regulation, policy, manual, procedure, protocol, guide, minutes, contract] → "living"; purpose=informational AND genre=expository → "frozen". If LLM completely fails (no classification data), default to "living". If partial classification explicitly indicates frozen, honor it.
    - Return `LLMAnalysisResultV3 | None` (None on any failure)
    - 10s timeout unchanged
    - _Requirements: Req 3 (criteria 3, 4, 6), Req 4 (criteria 4, 5), Req 7 (criteria 1, 5)_

  - [ ] 4.3 Update service orchestrator
    - Modify `src/backend/app/analysis/base_analysis/service.py`
    - Update `analyze()` to use LocalAnalyzer v2 result (with text_stats and hints)
    - Pass hints and language to LLMAnalyzer v3
    - Persist partial card immediately after local analysis (Ficha Técnica available)
    - Update card to completed when LLM responds
    - Populate new DocumentCard fields: text_stats, classification_result, topics, audience, lifecycle, is_corporate
    - Update storage calls to handle new fields
    - _Requirements: Req 4 (criterion 5), Req 5 (criterion 4), Req 9 (criterion 4)_

  - [ ] 4.4 Update storage for new fields
    - Modify `src/backend/app/analysis/base_analysis/storage.py`
    - Ensure `upsert_card()` serializes new fields (text_stats, classification_result, topics, audience, lifecycle, is_corporate) into JSONB
    - Ensure `get_card()` deserializes with defaults for missing fields (backward compat)
    - No database migration — rely on JSONB flexibility
    - _Requirements: Req 9 (criteria 1, 3)_

- [ ] 5. Rewrite frontend card component
  - [ ] 5.1 Rewrite DocumentCardView with two-section layout
    - Rewrite `src/frontend/src/components/document-card/DocumentCardView.tsx`
    - **Ficha Técnica section** (always visible): format badge, file size (human-readable), language, word count. Collapsible "Más detalles": sentence count, paragraph count, readability (score + label), organization type, sections detected, hierarchy levels, upload date. Each field with tooltip (shadcn Tooltip).
    - **Contenido section**: executive summary (2-3 lines), topic badges (3-5 keywords as shadcn Badge), classification chain with confidence %. Collapsible "Más detalles": purpose, audience, content-mix note (if applicable), lifecycle badge (green "Documento vivo" / blue "Documento congelado").
    - Partial card: Ficha Técnica shows fully, Contenido shows retry button
    - Non-corporate banner: "Este documento no parece ser un documento corporativo..."
    - Backward compat: cards without new fields render legacy layout
    - Use shadcn/ui: Card, Badge, Button, Skeleton, Tooltip, Collapsible
    - Accessibility: keyboard nav, aria-expanded, aria-controls, ARIA live regions, 4.5:1 contrast on badges
    - _Requirements: Req 5 (criteria 1-8), Req 7 (criterion 4)_

  - [ ] 5.2 Simplify ProcessingStatus and adjust UploadPage
    - Simplify `src/frontend/src/components/upload/ProcessingStatus.tsx`: remove language/chunks fields, keep only upload progress bar, filename, and processing step indicator
    - Adjust `src/frontend/src/components/upload/UploadPage.tsx`: seamless transition from ProcessingStatus to DocumentCardView when card becomes available (Ficha Técnica appears instantly, Contenido shows skeleton then fills)
    - _Requirements: Req 8 (criteria 1-4)_

- [ ] 6. Tests (consolidated)
  - [ ] 6.1 Backend unit tests
    - Test TextStatsAnalyzer: word/sentence/paragraph counts for known texts, readability formula selection by language, edge cases (empty text, single word), strict boundary label mapping (verify boundary values like exactly 80, 60, 40, 20)
    - Test language detection: Spanish/English/Portuguese texts correctly identified, 30% confidence threshold behavior, never returns "Unknown", progressive retry with smaller samples on timeout
    - Test classification models: enum serialization, DocumentClassificationResult.build_display_chain_es(), confidence bounds
    - Test classification hints: pattern matching for each document type, is_corporate logic, empty hints when no match
    - Test LLMAnalyzer v3: prompt construction with hints, 4-level parsing, confidence computation (min + bonus/penalty), invalid enum handling defaults to "other", timeout returns None, distinguish malformed JSON vs valid JSON with wrong schema, partial frozen lifecycle honored
    - Test service v2: two-phase persist (partial then completed), backward compat deserialization
    - Test storage: new fields serialized/deserialized, legacy cards get defaults
    - _Requirements: Req 1-4, Req 6, Req 7, Req 9_

  - [ ] 6.2 Frontend component tests
    - Test DocumentCardView: renders Ficha Técnica section with all fields, renders Contenido section when completed, shows retry button when partial, shows skeleton when loading, backward compat (no new fields → legacy render), non-corporate banner shown when is_corporate=false, collapsibles expand/collapse, tooltips appear on hover/focus
    - Test ProcessingStatus simplified: only shows progress + filename
    - Test UploadPage transition: ProcessingStatus → DocumentCardView seamless switch
    - _Requirements: Req 5, Req 8_

  - [ ] 6.3 Integration test
    - Test full flow: upload → local analysis produces partial card with Ficha Técnica → LLM produces completed card with Contenido
    - Test LLM failure: upload → partial card persists, Ficha Técnica available, Contenido shows retry
    - Test backward compat: existing card without new fields loads and renders without errors
    - _Requirements: Req 1-9 (end-to-end validation)_

## Notes

- Maximum 6 tasks as specified in constraints. Tests consolidated in task 6.
- Tasks 1-4 are backend, task 5 is frontend, task 6 is cross-cutting tests.
- No database migration needed — JSONB absorbs new fields with Pydantic defaults.
- lingua-py and textstat are pure Python — no native compilation or system dependencies.
- The base-analysis spec remains as historical reference; this spec evolves the card.
- Existing cards without new fields continue to work via nullable fields + defaults.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 4, "tasks": ["5.1", "5.2"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3"] }
  ]
}
```
