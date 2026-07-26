# Implementation Plan: User Preferences (Preferencias de Usuario)

## Overview

Implement the User Preferences feature: a collapsible left sidebar with language selector, LLM model selector, and auto-fallback toggle. Preferences persist in localStorage and propagate to the backend via HTTP headers. All prompt templates are updated to respect the selected language. Backend in Python (FastAPI + Pydantic v2), frontend in TypeScript (React + Zustand + Tailwind + shadcn/ui).

## Tasks

- [ ] 1. Create preferences Zustand store with localStorage persistence
  - [ ] 1.1 Create usePreferencesStore
    - Create `src/frontend/src/store/preferencesStore.ts`
    - State: `language: 'es' | 'en'`, `model: string`, `autoFallback: boolean`
    - Actions: `setLanguage(lang)`, `setModel(model)`, `setAutoFallback(enabled)`
    - On creation: read from `localStorage.getItem('user_preferences')`, parse JSON, merge with defaults
    - On every setter: `localStorage.setItem('user_preferences', JSON.stringify(state))`
    - Handle invalid/missing localStorage gracefully (fall back to defaults)
    - Defaults: `{ language: 'es', model: 'default', autoFallback: true }`
    - _Requirements: Req 2 (criterion 3), Req 3 (criterion 2), Req 4 (criterion 4)_

  - [ ] 1.2 Write unit tests for preferencesStore
    - Create `src/frontend/tests/store/preferencesStore.test.ts`
    - Test initialization with empty localStorage → defaults applied
    - Test initialization with valid stored preferences → values loaded
    - Test initialization with corrupted JSON → defaults applied
    - Test setLanguage persists to localStorage
    - Test setModel persists to localStorage
    - Test setAutoFallback persists to localStorage
    - Test preference values survive store re-creation (simulating page reload)
    - _Requirements: Req 2 (criterion 3), Req 3 (criterion 2), Req 4 (criterion 4)_

- [ ] 2. Wire language from preferences store to TranslationProvider
  - [ ] 2.1 Update main.tsx with reactive locale
    - Modify `src/frontend/src/main.tsx`
    - Create `LocalizedApp` wrapper component that reads `language` from `usePreferencesStore`
    - Pass `language` as `locale` prop to `TranslationProvider`
    - Ensure changing language re-renders the entire translation tree reactively
    - _Requirements: Req 2 (criterion 2)_

  - [ ] 2.2 Update TranslationProvider default locale
    - Modify `src/frontend/src/i18n/index.ts`
    - Change default locale from `'en'` to `'es'` (matching app default)
    - _Requirements: Req 2 (criterion 5)_

- [ ] 3. Add i18n keys for sidebar and preferences
  - [ ] 3.1 Update Spanish translations
    - Modify `src/frontend/src/i18n/es.json`
    - Add `sidebar` section with keys: `title`, `collapse`, `expand`
    - Add `sidebar.preferences` section: `title`
    - Add `sidebar.language` section: `label`, `options.es` ("Español"), `options.en` ("English")
    - Add `sidebar.model` section: `label`, `options.default` ("Automático (recomendado)"), `options.defaultDesc`, `options.gemini` ("Gemini 2.5 Flash"), `options.geminiDesc` ("Principal — análisis profundo"), `options.groq` ("Groq Llama 3.3 70B"), `options.groqDesc` ("Rápido — análisis base")
    - Add `sidebar.fallback` section: `label` ("Auto-fallback"), `description`, `enabled`, `disabled`
    - _Requirements: Req 1 (criterion 5), Req 2 (criterion 1), Req 3 (criterion 1, 5), Req 4 (criterion 1)_

  - [ ] 3.2 Update English translations
    - Modify `src/frontend/src/i18n/en.json`
    - Add same structure as Spanish with English values
    - _Requirements: Req 1 (criterion 5), Req 2 (criterion 1), Req 3 (criterion 1, 5), Req 4 (criterion 1)_

- [ ] 4. Create Sidebar component
  - [ ] 4.1 Create Sidebar UI
    - Create `src/frontend/src/components/layout/Sidebar.tsx`
    - Collapsible panel: 260px expanded, 48px collapsed
    - Toggle button with chevron icon (lucide-react)
    - Collapsed state: show only icon indicators with tooltips
    - Expanded state: show full preference controls
    - Preferences section with heading
    - Language selector: shadcn `Select` with options from i18n keys
    - Model selector: shadcn `Select` with options + brief descriptions below each
    - Auto-fallback: shadcn `Switch` with label and description text
    - All labels use `useTranslation()` for i18n support
    - Wire to `usePreferencesStore` actions for read/write
    - _Requirements: Req 1 (criteria 1-3, 5), Req 2 (criterion 1), Req 3 (criteria 1, 5), Req 4 (criterion 1)_

  - [ ] 4.2 Implement responsive behavior
    - Desktop (≥768px): sidebar pushes main content (flex layout)
    - Mobile (<768px): sidebar overlays content with backdrop
    - Backdrop click or toggle closes sidebar on mobile
    - Store collapsed/expanded state in component local state (not persisted)
    - Default to collapsed on mobile, expanded on desktop
    - _Requirements: Req 1 (criterion 4)_

  - [ ] 4.3 Implement accessibility
    - Toggle button: `aria-expanded`, `aria-label`
    - Select components: associated labels, keyboard navigable
    - Switch: associated label, `role="switch"`, `aria-checked`
    - Sidebar landmark: `role="complementary"` or `<aside>`
    - Focus trap when sidebar overlays on mobile
    - _Requirements: Req 1 (criterion 5)_

  - [ ] 4.4 Write component tests for Sidebar
    - Create `src/frontend/tests/components/layout/Sidebar.test.tsx`
    - Test renders collapsed by default (mobile viewport)
    - Test toggle expands/collapses
    - Test language selector dispatches setLanguage
    - Test model selector dispatches setModel
    - Test fallback switch dispatches setAutoFallback
    - Test accessibility attributes present
    - _Requirements: Req 1 (criteria 1-5)_

- [ ] 5. Update AppShell layout to include Sidebar
  - [ ] 5.1 Modify AppShell layout
    - Modify `src/frontend/src/components/layout/AppShell.tsx`
    - Change from vertical-only flex to horizontal: `<Sidebar />` + main column
    - Main column contains Header + main content (existing structure)
    - Main content area uses `flex-1` to fill remaining width
    - Ensure existing responsive behavior of content area is preserved
    - _Requirements: Req 1 (criteria 1, 4)_

- [ ] 6. Inject preference headers into API client
  - [ ] 6.1 Modify API client
    - Modify `src/frontend/src/api/client.ts`
    - Create `getPreferenceHeaders(): Record<string, string>` helper
    - Reads from `usePreferencesStore.getState()` (works outside React components)
    - Returns: `{ 'Accept-Language': language, 'X-Model-Preference': model, 'X-Auto-Fallback': String(autoFallback) }`
    - Inject these headers into all existing fetch calls (modify the shared fetch pattern)
    - If model is 'default', still send header with value 'default' (backend interprets)
    - _Requirements: Req 5 (criterion 1)_

  - [ ] 6.2 Write unit test for header injection
    - Create `src/frontend/tests/api/preferenceHeaders.test.ts`
    - Test headers reflect current store state
    - Test defaults when store is in initial state
    - _Requirements: Req 5 (criterion 1)_

- [ ] 7. Create backend request preferences dependency
  - [ ] 7.1 Create preferences module
    - Create `src/backend/app/middleware/__init__.py`
    - Create `src/backend/app/middleware/preferences.py`
    - Define `RequestPreferences` dataclass: `language: str`, `model_override: str | None`, `auto_fallback: bool`
    - Define `get_request_preferences(request: Request) -> RequestPreferences` as FastAPI `Depends` function
    - Parse `Accept-Language`: take first 2 chars, validate against ('es', 'en'), default 'es'
    - Parse `X-Model-Preference`: if 'default' or empty → None; otherwise use as-is
    - Parse `X-Auto-Fallback`: 'false' → False, anything else → True
    - _Requirements: Req 5 (criteria 2-5)_

  - [ ] 7.2 Write unit tests for preferences middleware
    - Create `tests/unit/middleware/test_preferences.py`
    - Test with all headers present → correct values
    - Test with missing headers → defaults (es, None, True)
    - Test with invalid language → falls back to 'es'
    - Test with X-Model-Preference: 'default' → model_override is None
    - Test with X-Auto-Fallback: 'false' → auto_fallback is False
    - _Requirements: Req 5 (criteria 2-5)_

- [ ] 8. Update LLMClient to accept model override and fallback control
  - [ ] 8.1 Extend LLMClient.call() signature
    - Modify `src/backend/app/analysis/llm_client.py`
    - Add `model_override: str | None = None` parameter
    - Add `auto_fallback: bool = True` parameter
    - If `model_override` is not None and not 'default': use it as `target_model` instead of tier default
    - If `auto_fallback` is False: on transient error, raise `LLMTransientError` immediately (skip fallback)
    - If `auto_fallback` is True: existing fallback behavior unchanged
    - All existing callers continue to work (new params are optional with backward-compatible defaults)
    - _Requirements: Req 3 (criterion 3), Req 4 (criteria 2-3), Req 5 (criteria 3-4)_

  - [ ] 8.2 Write unit tests for new LLMClient parameters
    - Modify `tests/unit/analysis/test_llm_client.py` (or create new test file)
    - Test model_override routes to specified model
    - Test model_override=None uses tier default (existing behavior)
    - Test auto_fallback=False raises on transient error without retry
    - Test auto_fallback=True retries (existing behavior preserved)
    - _Requirements: Req 3 (criterion 3), Req 4 (criteria 2-3)_

- [ ] 9. Update base analysis prompts with language parameter
  - [ ] 9.1 Modify prompt template
    - Modify `src/backend/app/analysis/base_analysis/prompts.py`
    - Add `{response_language}` placeholder as first line: "Respond in {response_language}."
    - Keep all existing placeholders intact
    - _Requirements: Req 6 (criterion 1)_

  - [ ] 9.2 Modify LLMAnalyzer to accept language
    - Modify `src/backend/app/analysis/base_analysis/llm_analyzer.py`
    - Add `language: str = "es"` parameter to `analyze()` method
    - Map: 'es' → "Spanish", 'en' → "English"
    - Pass as `response_language` to prompt template format
    - _Requirements: Req 6 (criterion 1)_

  - [ ] 9.3 Propagate language through BaseAnalysisService
    - Modify `src/backend/app/analysis/base_analysis/service.py`
    - Add `language: str = "es"` parameter to `analyze()` and `retry_llm()`
    - Pass to `self._llm_analyzer.analyze(..., language=language)`
    - _Requirements: Req 6 (criterion 1)_

  - [ ] 9.4 Inject preferences into card and documents API endpoints
    - Modify `src/backend/app/api/v1/card.py`: add `prefs: RequestPreferences = Depends(get_request_preferences)` to retry-llm endpoint, pass `prefs.language` and `prefs.model_override` to service
    - Modify `src/backend/app/api/v1/documents.py`: pass preferences to `_run_base_analysis` background task
    - _Requirements: Req 5 (criteria 2-4), Req 6 (criterion 1)_

- [ ] 10. Update quality analysis prompts with language parameter
  - [ ] 10.1 Update ambiguity detector
    - Modify `src/backend/app/analysis/quality/ambiguity_detector.py`
    - Add `language: str = "es"` parameter to analysis method
    - Add "Respond in {language}" to prompt template (explanations in ui_language)
    - _Requirements: Req 6 (criterion 2)_

  - [ ] 10.2 Update completeness evaluator
    - Modify `src/backend/app/analysis/quality/completeness_evaluator.py`
    - Add `language: str = "es"` parameter to analysis method
    - Add "Respond in {language}" to prompt template
    - _Requirements: Req 6 (criterion 2)_

  - [ ] 10.3 Update contradiction detector
    - Modify `src/backend/app/analysis/quality/contradiction_detector.py`
    - Add `language: str = "es"` parameter to analysis method
    - Add "Respond in {language}" to prompt template
    - _Requirements: Req 6 (criterion 2)_

  - [ ] 10.4 Update suggestion generator
    - Modify `src/backend/app/analysis/quality/suggestion_generator.py`
    - Add `document_language: str = "es"` parameter (NOT ui_language — suggestions must be in document's language per language rules)
    - Add "Respond in {document_language}" to prompt template
    - _Requirements: Req 6 (criterion 2)_

  - [ ] 10.5 Propagate language through quality service and API
    - Modify `src/backend/app/analysis/quality/service.py`: propagate `language` and `document_language` to all sub-detectors
    - Modify `src/backend/app/api/v1/quality.py`: inject `RequestPreferences`, pass `prefs.language` to service
    - _Requirements: Req 5 (criteria 2-4), Req 6 (criterion 2)_

- [ ] 11. Update query/Q&A prompts with language parameter
  - [ ] 11.1 Update query service
    - Modify `src/backend/app/analysis/query/service.py`
    - Add `language: str = "es"` parameter to query method
    - Add "Respond in {language}" instruction to the query prompt
    - _Requirements: Req 6 (criterion 3)_

  - [ ] 11.2 Inject preferences into query API endpoint
    - Modify `src/backend/app/api/v1/query.py`
    - Add `prefs: RequestPreferences = Depends(get_request_preferences)` dependency
    - Pass `prefs.language` and `prefs.model_override` to query service
    - _Requirements: Req 5 (criteria 2-4), Req 6 (criterion 3)_

- [ ] 12. Integration verification
  - [ ] 12.1 Frontend build verification
    - Run `npx vite build` — must complete without errors
    - Verify no TypeScript errors in source files (test files excluded)

  - [ ] 12.2 Backend startup verification
    - Run `python -m uvicorn app.run:app` — must start without import errors
    - Verify all modified endpoints accept the new headers

  - [ ] 12.3 Manual integration checklist
    - Start app → sidebar visible with collapsed icon state
    - Expand sidebar → language, model, and fallback selectors visible
    - Change language → all UI labels switch immediately (no reload)
    - Upload document → card summary appears in selected language
    - Change model → verify in backend logs that next analysis uses selected model
    - Toggle auto-fallback off → verify behavior on model failure (if testable)
    - Reload page → preferences restored from localStorage
    - Mobile viewport → sidebar overlays correctly, backdrop closes it

## Notes

- Tasks 1, 3, and 7 are independent and can be developed in parallel
- Task 2 depends on Task 1 (needs the store to exist)
- Tasks 4 and 5 depend on Tasks 1 and 3 (need store + i18n keys)
- Task 6 depends on Task 1 (needs store for header values)
- Tasks 8-11 depend on Task 7 (need RequestPreferences to exist)
- Task 12 depends on all previous tasks
- All backend changes are backward-compatible: missing headers use defaults
- No database migrations needed for this feature

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "3.2", "7.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.2", "6.1", "7.2", "8.1"] },
    { "id": 2, "tasks": ["4.1", "4.2", "4.3", "6.2", "8.2"] },
    { "id": 3, "tasks": ["4.4", "5.1"] },
    { "id": 4, "tasks": ["9.1", "9.2", "9.3", "9.4"] },
    { "id": 5, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5"] },
    { "id": 6, "tasks": ["11.1", "11.2"] },
    { "id": 7, "tasks": ["12.1", "12.2", "12.3"] }
  ]
}
```
