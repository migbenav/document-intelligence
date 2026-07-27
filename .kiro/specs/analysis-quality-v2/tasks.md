# Implementation Plan: Analysis Quality v2

## Overview

Overhaul the on-demand analysis engine to focus on functional/purpose comprehension, fix model transparency and error handling, improve language detection, and expand available models. All changes are backward-compatible — existing stored results remain valid, new fields are optional with defaults.

## Tasks

- [x] 1. Fix model_id propagation and create AnalyzerResponse dataclass
  - [x] 1.1 Create AnalyzerResponse dataclass
    - Create `src/backend/app/analysis/on_demand/analyzer_response.py`
    - Define `AnalyzerResponse` dataclass with fields: `result` (BaseModel), `model_id` (str — actual model from LLMResponse), `prompt_version` (str), `fallback_used` (bool, default False)
    - This is the standard return type for all four analyzers
    - _Requirements: Req 5 (criterion 1)_

  - [x] 1.2 Update IndexAnalyzer to return AnalyzerResponse
    - Modify `src/backend/app/analysis/on_demand/index_analyzer.py`
    - Change `analyze()` return type from `IndexResult` to `AnalyzerResponse`
    - Capture `response.model_id` from `LLMResponse` after LLM call
    - Determine `fallback_used` by comparing `response.model_id` with requested model
    - Return `AnalyzerResponse(result=result, model_id=response.model_id, prompt_version=PROMPT_VERSION, fallback_used=...)`
    - _Requirements: Req 5 (criterion 1)_

  - [x] 1.3 Update RelationsAnalyzer, QuestionsAnalyzer, ConclusionsAnalyzer to return AnalyzerResponse
    - Same pattern as 1.2 for each of the three remaining analyzers
    - Modify `relations_analyzer.py`, `questions_analyzer.py`, `conclusions_analyzer.py`
    - Each captures `response.model_id` and returns `AnalyzerResponse`
    - _Requirements: Req 5 (criterion 1)_

  - [x] 1.4 Update OnDemandAnalysisService to use AnalyzerResponse
    - Modify `src/backend/app/analysis/on_demand/service.py`
    - Change `_dispatch_analyzer` return type from `tuple` to `AnalyzerResponse`
    - In `execute()`: use `response.model_id` (actual) for `AnalysisRecord.model_id`
    - Add `requested_model` and `fallback_used` fields to `AnalysisRecord` construction
    - _Requirements: Req 5 (criteria 1, 3)_

  - [x] 1.5 Update AnalysisRecord model with new fields
    - Modify `src/backend/app/analysis/on_demand/models.py`
    - Add `requested_model: str | None = None` field
    - Add `fallback_used: bool = False` field
    - These are optional with defaults for backward compat
    - _Requirements: Req 5 (criteria 1, 3)_

  - [x] 1.6 Write unit tests for model_id propagation
    - Create `tests/unit/analysis/on_demand/test_model_propagation.py`
    - Test: analyzer returns actual model_id from LLMResponse (mock LLMClient)
    - Test: service uses actual model_id in AnalysisRecord (not model_override)
    - Test: fallback_used is True when response.model_id differs from requested
    - _Requirements: Req 5 (criteria 1, 3)_

- [x] 2. Classify LLM errors and update API responses
  - [x] 2.1 Create LLMQuotaExhaustedError exception
    - Modify `src/backend/app/analysis/llm_client.py`
    - Add `LLMQuotaExhaustedError(Exception)` with `model_id: str` attribute
    - Add `_is_quota_error(self, error)` method: check for "429", "quota", "rate_limit" in error string or isinstance RateLimitError
    - In `call()`: before treating as generic transient error, check if it's quota-specific and raise `LLMQuotaExhaustedError` instead
    - Quota errors should NOT trigger fallback (user should choose a different model)
    - _Requirements: Req 5 (criterion 2)_

  - [x] 2.2 Update API endpoint with classified error responses
    - Modify `src/backend/app/api/v1/analyses.py`
    - Import `LLMQuotaExhaustedError`, `LLMAuthenticationError` from llm_client
    - Import `asyncio.TimeoutError`
    - Add specific except blocks (before generic Exception):
      - `LLMQuotaExhaustedError` → 429 with `{"error_code": "quota_exhausted", "model_id": ..., "message": ...}`
      - `asyncio.TimeoutError` → 504 with `{"error_code": "timeout", "message": ...}`
      - `LLMAuthenticationError` → 401 with `{"error_code": "auth_error", "message": ...}`
      - Generic `Exception` → 502 with `{"error_code": "analysis_failed", "message": ...}`
    - Add `requested_model` and `fallback_used` to success 200 response
    - _Requirements: Req 5 (criteria 2, 6)_

  - [x] 2.3 Update frontend error handling
    - Modify `src/frontend/src/api/analyses.ts`
    - Extend `handleErrorResponse` to parse `error_code` and `model_id` from response body
    - Create `AnalysisApiError` subclass or extend with `errorCode` and `modelId` fields
    - Handle new status codes: 429 (quota), 504 (timeout), 401 (auth)
    - _Requirements: Req 5 (criteria 5, 6)_

  - [x] 2.4 Display classified errors in UI
    - Modify `src/frontend/src/store/analysisStore.ts`: store `errorCode` and `errorModelId` in state
    - Modify `src/frontend/src/components/upload/UploadPage.tsx` or create a new `AnalysisError` component
    - Display differentiated messages based on error_code:
      - quota_exhausted: "Se agotó la cuota de {model}. Seleccione otro modelo o espere."
      - timeout: "El análisis tardó demasiado. Intente con un modelo más rápido."
      - auth_error: "Error de credenciales para el modelo. Verifique la configuración."
      - analysis_failed: "El análisis falló. Intente nuevamente."
    - Add i18n keys for all error messages (es.json, en.json)
    - _Requirements: Req 5 (criterion 5)_

  - [x] 2.5 Display model badge on analysis results
    - Modify `src/frontend/src/components/analysis/AnalysisResultView.tsx`
    - Add a small Badge showing `model_id` (shortened: "gemini-2.5-flash", "llama-3.3")
    - If `fallback_used` is true, show "(fallback)" suffix
    - Pass `model_id` and `fallback_used` from the analysis record to the view
    - _Requirements: Req 5 (criterion 4)_

  - [x] 2.6 Write tests for error classification
    - Create `tests/unit/analysis/test_llm_quota_error.py`
    - Test: RateLimitError with "429" raises LLMQuotaExhaustedError
    - Test: quota error does NOT trigger fallback
    - Test: other transient errors still trigger fallback
    - Test: API endpoint returns correct status codes and error_codes
    - _Requirements: Req 5 (criteria 2, 6)_

- [x] 3. Update model configuration and fallback logic
  - [x] 3.1 Fix DEFAULT_FALLBACK_MODEL
    - Modify `src/backend/app/analysis/llm_client.py`
    - Change `DEFAULT_FALLBACK_MODEL = "groq/llama-3.3-70b-versatile"` (was "gemini/gemini-2.5-flash")
    - This ensures that when Gemini hits quota, the fallback actually uses a different provider
    - _Requirements: Req 6 (criterion 2)_

  - [x] 3.2 Implement cross-provider fallback logic
    - Modify `LLMClient.call()` fallback section
    - When `model_override` specifies a Groq model and fails → fallback to Gemini
    - When `model_override` specifies a Gemini model and fails → fallback to Groq
    - Add helper `_get_fallback_for(model_id: str) -> str` that picks the opposite provider
    - _Requirements: Req 6 (criterion 3)_

  - [x] 3.3 Add new models to frontend selector
    - Modify `src/frontend/src/components/layout/Sidebar.tsx`
    - Add to AVAILABLE_MODELS array:
      - `{ id: 'gemini/gemini-2.5-pro', nameKey: ..., descriptionKey: ... }`
      - `{ id: 'groq/meta-llama/llama-4-maverick-17b-128e', nameKey: ..., descriptionKey: ... }`
    - Add i18n keys for new model names and descriptions (es.json, en.json)
    - _Requirements: Req 6 (criteria 1, 5)_

  - [x] 3.4 Write tests for cross-provider fallback
    - Add tests to `tests/unit/analysis/test_llm_client.py`
    - Test: Groq model fails → fallback uses Gemini
    - Test: Gemini model fails → fallback uses Groq
    - Test: quota error does NOT trigger fallback (separate from transient)
    - _Requirements: Req 6 (criteria 2, 3)_

- [x] 4. Pass classification to analyzers (infrastructure)
  - [x] 4.1 Add BaseAnalysisStorage dependency to OnDemandAnalysisService
    - Modify `src/backend/app/analysis/on_demand/service.py`
    - Add `card_storage: BaseAnalysisStorage` to `__init__` parameters
    - In `execute()`: call `card_storage.get_card(document_id)` to load classification
    - Extract `classification` (default "generic") and `document_language` from card
    - Pass both to `_dispatch_analyzer` and then to each analyzer
    - _Requirements: Req 8 (criteria 1, 2, 4, 5)_

  - [x] 4.2 Wire BaseAnalysisStorage in application factory
    - Modify `src/backend/app/main.py`
    - Pass `base_analysis_storage` to `OnDemandAnalysisService.__init__` as `card_storage`
    - _Requirements: Req 8 (criterion 1)_

  - [x] 4.3 Update analyzer signatures to accept classification
    - Modify all four analyzers: add `classification: str = "generic"` parameter to `analyze()`
    - Each analyzer will use classification in prompt (implemented in tasks 5-8)
    - For now, accept the parameter without changing prompt behavior
    - _Requirements: Req 8 (criterion 3)_

  - [x] 4.4 Write tests for classification propagation
    - Create `tests/unit/analysis/on_demand/test_classification_input.py`
    - Test: service loads card and passes classification to analyzer
    - Test: missing card results in "generic" classification
    - Test: document_language from card is passed correctly
    - _Requirements: Req 8 (criteria 1-5)_

- [x] 5. Redesign Build Index prompt — functional comprehension
  - [x] 5.1 Update StructureNode model with new fields
    - Modify `src/backend/app/analysis/on_demand/models.py`
    - Add `functional_group: str | None = None` to StructureNode
    - Add `original_headings: list[str] = []` to StructureNode
    - Add `document_purpose: str | None = None` to IndexResult
    - Update `role` field validators to accept new values: `enables`, `restricts`, `controls`, `delegates`
    - _Requirements: Req 1 (criteria 2, 3, 6)_

  - [x] 5.2 Rewrite Build Index prompt template
    - Create `src/backend/app/analysis/on_demand/prompts/build_index_v2.py`
    - Set `PROMPT_VERSION = "build-index-v2"`
    - Prompt structure:
      1. "You are analyzing a {classification} document. Its purpose is to {purpose_hint_by_classification}."
      2. "First, identify the document's OVERALL PURPOSE in one sentence."
      3. "Then, identify FUNCTIONAL GROUPINGS — how the document organizes its functions. Do NOT simply list headings."
      4. "Multiple chapters serving the same function belong in ONE functional node."
      5. "For each node: what does this part DO functionally (not what it says)?"
    - Include classification-specific hints (normative → "establishes rules", procedure → "describes steps", etc.)
    - JSON schema includes new fields (functional_group, original_headings, document_purpose)
    - _Requirements: Req 1 (criteria 1-8)_

  - [x] 5.3 Update IndexAnalyzer to use v2 prompt
    - Modify `src/backend/app/analysis/on_demand/index_analyzer.py`
    - Import from `prompts/build_index_v2` instead of `prompts/build_index`
    - Include `classification` in prompt formatting
    - Validate against updated IndexResult model
    - _Requirements: Req 1 (criteria 1, 7)_

  - [x] 5.4 Update frontend IndexTreeView for new fields
    - Modify `src/frontend/src/types/analysis.ts`: add `functional_group`, `original_headings`, `document_purpose` to types
    - Modify `src/frontend/src/components/analysis/IndexTreeView.tsx`:
      - Show `functional_group` as a subtle label on level-1 nodes
      - Show `original_headings` in a tooltip or expandable detail when node is expanded
      - Show `document_purpose` at the top of the tree as a summary line
    - _Requirements: Req 1 (criteria 2, 3)_

  - [x] 5.5 Write tests for Build Index v2
    - Create `tests/unit/analysis/on_demand/test_index_v2.py`
    - Test: prompt includes classification and functional instructions
    - Test: IndexResult with functional_group and original_headings parses correctly
    - Test: document_purpose field is present in result
    - Test: role values include new vocabulary (enables, restricts, controls, delegates)
    - _Requirements: Req 1 (criteria 1-8)_

- [x] 6. Redesign Questions Answered prompt — document logic
  - [x] 6.1 Update QuestionsResult model
    - Modify `src/backend/app/analysis/on_demand/models.py`
    - Add `coherence_note: str | None = None` to QuestionsResult
    - _Requirements: Req 2 (criterion 6)_

  - [x] 6.2 Rewrite Questions Answered prompt template
    - Create `src/backend/app/analysis/on_demand/prompts/questions_answered_v2.py`
    - Set `PROMPT_VERSION = "questions-answered-v2"`
    - Prompt structure:
      1. "This is a {classification} document."
      2. Classification-specific instructions:
         - normative: "Identify the REGULATORY LOGIC: What does it regulate? What is permitted? What is prohibited? Who enforces? What are consequences?"
         - procedure: "Identify the PROCESS LOGIC: Can it be done? Who decides? How is it executed? How is it controlled?"
         - narrative: "Identify the NARRATIVE LOGIC: What is the subject? What sequence does it follow? What conclusion is reached?"
         - generic: "Identify the FUNCTIONAL LOGIC: What does this document establish and how does it organize that purpose?"
      3. "Questions must reveal the LOGICAL CHAIN of the document — not describe what each section says."
      4. "If the document does not have a coherent logic, include a coherence_note explaining why."
    - JSON schema includes coherence_note
    - _Requirements: Req 2 (criteria 1-9)_

  - [x] 6.3 Update QuestionsAnalyzer to use v2 prompt
    - Modify `src/backend/app/analysis/on_demand/questions_analyzer.py`
    - Import from `prompts/questions_answered_v2`
    - Include `classification` in prompt formatting
    - Validate against updated QuestionsResult model
    - _Requirements: Req 2 (criteria 1, 5)_

  - [x] 6.4 Update frontend QuestionsCascadeView for coherence_note
    - Modify `src/frontend/src/types/analysis.ts`: add `coherence_note` to QuestionsResult type
    - Modify `src/frontend/src/components/analysis/QuestionsCascadeView.tsx`:
      - If `coherence_note` is present, show an Alert/warning banner at the top
    - Add i18n key for coherence warning label
    - _Requirements: Req 2 (criterion 6)_

  - [x] 6.5 Write tests for Questions Answered v2
    - Create `tests/unit/analysis/on_demand/test_questions_v2.py`
    - Test: prompt includes classification
    - Test: normative classification produces regulatory-style instructions in prompt
    - Test: QuestionsResult with coherence_note parses correctly
    - Test: questions are not generic (test prompt instructs specificity)
    - _Requirements: Req 2 (criteria 1-9)_

- [x] 7. Redesign Conclusions prompt — domain-aware coherence
  - [x] 7.1 Update Observation model and ConclusionsResult
    - Modify `src/backend/app/analysis/on_demand/models.py`
    - Change Observation `category` allowed values to: `purpose_mismatch`, `misplaced_content`, `title_mismatch`, `sequence_issue`, `duplication`, `contradiction`
    - Add `domain: str | None = None` to Observation
    - Add `domains_identified: list[str] = []` to ConclusionsResult
    - _Requirements: Req 3 (criteria 1, 6)_

  - [x] 7.2 Rewrite Conclusions prompt template
    - Create `src/backend/app/analysis/on_demand/prompts/conclusions_v2.py`
    - Set `PROMPT_VERSION = "conclusions-v2"`
    - Prompt structure:
      1. "This is a {classification} document."
      2. "Step 1: Identify the INDEPENDENT DOMAINS/TOPICS in this document (e.g., parking, elevators, common areas)."
      3. "Step 2: For each domain and for the document as a whole, evaluate:"
         - "Does each section's PURPOSE match the document type? (purpose_mismatch)"
         - "Is each paragraph in the RIGHT PLACE by semantic affinity? (misplaced_content)"
         - "Do TITLES reflect their actual content? (title_mismatch)"
         - "Is the ORDER logical? (sequence_issue)"
         - "Is there DUPLICATED content? (duplication)"
         - "Are there CONTRADICTIONS within the SAME domain? (contradiction)"
      4. "CRITICAL: NEVER flag contradictions between INDEPENDENT domains. Parking rules and elevator rules are different domains."
      5. "For narrative documents: focus on logical sequence and narrative coherence, not purpose compliance."
    - JSON schema includes domains_identified and domain per observation
    - _Requirements: Req 3 (criteria 1-10)_

  - [x] 7.3 Update ConclusionsAnalyzer to use v2 prompt
    - Modify `src/backend/app/analysis/on_demand/conclusions_analyzer.py`
    - Import from `prompts/conclusions_v2`
    - Include `classification` in prompt formatting
    - Validate against updated ConclusionsResult model
    - _Requirements: Req 3 (criteria 1, 7)_

  - [x] 7.4 Update frontend ConclusionsView for new categories
    - Modify `src/frontend/src/types/analysis.ts`: update Observation category union type and add `domain`, `domains_identified`
    - Modify `src/frontend/src/components/analysis/ConclusionsView.tsx`:
      - Group observations by domain (if domain is set) or by category
      - Show domain labels as section headers
      - Update category badges to use new category names with appropriate colors
    - Add i18n keys for new category names
    - _Requirements: Req 3 (criteria 1, 6)_

  - [x] 7.5 Write tests for Conclusions v2
    - Create `tests/unit/analysis/on_demand/test_conclusions_v2.py`
    - Test: prompt includes classification and domain identification step
    - Test: prompt explicitly forbids cross-domain contradictions
    - Test: ConclusionsResult with domains_identified parses correctly
    - Test: new categories validate correctly
    - _Requirements: Req 3 (criteria 1-10)_

- [x] 8. Redesign Section Relations prompt — functional connections
  - [x] 8.1 Update SectionRelation model
    - Modify `src/backend/app/analysis/on_demand/models.py`
    - Change `type` allowed values to: `enables`, `restricts`, `requires`, `implements`, `contradicts`
    - Add `domain: str | None = None` to SectionRelation
    - _Requirements: Req 4 (criteria 1, 2)_

  - [x] 8.2 Rewrite Section Relations prompt template
    - Create `src/backend/app/analysis/on_demand/prompts/section_relations_v2.py`
    - Set `PROMPT_VERSION = "section-relations-v2"`
    - Prompt structure:
      1. "This is a {classification} document."
      2. "Identify FUNCTIONAL relationships between document sections:"
         - "enables: one section permits/allows what another regulates"
         - "restricts: one section limits what another enables"
         - "requires: one section is a prerequisite for another"
         - "implements: one section details/operationalizes what another declares"
         - "contradicts: conflicting content within the SAME domain (never cross-domain)"
      3. "EXCLUDE trivial relationships (sequential order, adjacency)."
      4. "If Build Index structure is available, use functional group names as references."
    - If `index_result` is provided, include structure_tree summary in prompt
    - _Requirements: Req 4 (criteria 1-6)_

  - [x] 8.3 Update RelationsAnalyzer to use v2 prompt
    - Modify `src/backend/app/analysis/on_demand/relations_analyzer.py`
    - Import from `prompts/section_relations_v2`
    - Include `classification` in prompt formatting
    - Validate against updated RelationsResult model
    - _Requirements: Req 4 (criteria 1, 5)_

  - [x] 8.4 Update frontend RelationsListView for new types
    - Modify `src/frontend/src/types/analysis.ts`: update SectionRelation type union and add `domain`
    - Modify `src/frontend/src/components/analysis/RelationsListView.tsx`:
      - Update grouping to use new type names (enables, restricts, requires, implements, contradicts)
      - Update type labels and colors
    - Add i18n keys for new relation type names
    - _Requirements: Req 4 (criteria 1, 2)_

  - [x] 8.5 Write tests for Section Relations v2
    - Create `tests/unit/analysis/on_demand/test_relations_v2.py`
    - Test: prompt includes classification
    - Test: prompt excludes trivial relationships instruction
    - Test: new relation types validate correctly
    - Test: contradicts only flagged for same domain (prompt includes instruction)
    - _Requirements: Req 4 (criteria 1-6)_

- [x] 9. Improve language detection
  - [x] 9.1 Expand local language detector
    - Modify `src/backend/app/ingestion/language.py`
    - Change `_MAX_SAMPLE_LENGTH = 2000` (was 1000)
    - Add `_PORTUGUESE_STOPWORDS` set (top 50 Portuguese stopwords)
    - Add `_FRENCH_STOPWORDS` set (top 50 French stopwords)
    - Add `DetectedLanguage.PORTUGUESE` and `DetectedLanguage.FRENCH` to enum in `models/document.py`
    - Add preprocessing: strip URLs (`re.sub(r'https?://\S+', '', text)`), strip number-heavy tokens, strip camelCase/snake_case tokens before tokenization
    - Update `detect()` to score all four languages and return the winner
    - _Requirements: Req 7 (criteria 1, 2, 5)_

  - [x] 9.2 Add LLM language confirmation to base analysis
    - Modify `src/backend/app/analysis/base_analysis/llm_analyzer.py`
    - Add to the LLM prompt: "Also confirm or correct the detected document language. The system detected: {detected_language}. If incorrect, provide the correct ISO 639-1 code."
    - Parse language confirmation from LLM response
    - If LLM provides a different language, update the card's `file_metadata.language`
    - _Requirements: Req 7 (criteria 3, 4)_

  - [x] 9.3 Write tests for improved language detection
    - Modify `tests/unit/ingestion/test_language.py`
    - Test: sample expanded to 2000 chars
    - Test: Portuguese text correctly detected
    - Test: French text correctly detected
    - Test: text with URLs and numbers → noise stripped before detection
    - Test: technical Spanish document with English terms → detected as Spanish
    - _Requirements: Req 7 (criteria 1-5)_

- [x] 10. Integration verification and cleanup
  - [x] 10.1 Run full backend test suite
    - Execute `python -m pytest tests/ -v` from backend directory
    - Fix any test failures caused by the model changes (updated return types, new parameters)
    - Update existing tests that mock analyzers to use new AnalyzerResponse return type
    - _Requirements: All_

  - [x] 10.2 Run frontend build and type check
    - Execute `npm run build` from frontend directory
    - Fix any TypeScript errors from updated types
    - Verify all components compile with new optional fields
    - _Requirements: All_

  - [x] 10.3 Verify backward compatibility
    - Confirm old analysis results (with v1 prompt_version) still load and display correctly
    - New optional fields (functional_group, coherence_note, domain, etc.) default gracefully when absent
    - Frontend handles both v1 and v2 results without errors
    - _Requirements: Design Decision 1 (backward compat)_

## Notes

- Each task references specific requirements (Req N criterion M) for traceability
- Tasks 1-4 are infrastructure (model propagation, errors, fallback, classification plumbing)
- Tasks 5-8 are the core prompt redesigns (one per analysis type)
- Task 9 is language detection improvement
- Task 10 is integration verification
- All backend tests use mocked LLM responses and mocked Supabase client
- No new dependencies beyond the project's established stack
- No database migrations needed — JSONB columns absorb new fields automatically
- Existing v1 prompt results remain valid and displayable

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.5"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["1.6", "2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.2", "3.3"] },
    { "id": 4, "tasks": ["2.4", "2.5", "2.6", "3.4"] },
    { "id": 5, "tasks": ["4.1", "4.2", "4.3"] },
    { "id": 6, "tasks": ["4.4", "5.1", "6.1", "7.1", "8.1"] },
    { "id": 7, "tasks": ["5.2", "6.2", "7.2", "8.2"] },
    { "id": 8, "tasks": ["5.3", "6.3", "7.3", "8.3"] },
    { "id": 9, "tasks": ["5.4", "6.4", "7.4", "8.4"] },
    { "id": 10, "tasks": ["5.5", "6.5", "7.5", "8.5"] },
    { "id": 11, "tasks": ["9.1", "9.2"] },
    { "id": 12, "tasks": ["9.3", "10.1", "10.2", "10.3"] }
  ]
}
```
