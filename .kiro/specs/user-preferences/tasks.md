# Tasks

User Preferences — Implementation Steps

## Task 1: Create preferences Zustand store with localStorage persistence

**Requirements:** Req 2 (criterion 3), Req 3 (criterion 2), Req 4 (criterion 4)

Create `src/frontend/src/store/preferencesStore.ts`:
- State: `language: 'es' | 'en'`, `model: string`, `autoFallback: boolean`
- Actions: `setLanguage`, `setModel`, `setAutoFallback`
- Initialize from `localStorage.getItem('user_preferences')` parsed as JSON
- On every setter, persist full state to `localStorage.setItem('user_preferences', JSON.stringify(state))`
- Defaults: `{ language: 'es', model: 'default', autoFallback: true }`

- [ ] Create `src/frontend/src/store/preferencesStore.ts`
- [ ] Verify store reads from and writes to localStorage correctly

---

## Task 2: Wire language from preferences store to TranslationProvider

**Requirements:** Req 2 (criterion 2)

Update `src/frontend/src/main.tsx`:
- Create a `LocalizedApp` wrapper component that reads `language` from `usePreferencesStore`
- Pass `language` as `locale` prop to `TranslationProvider`
- This makes language switching reactive across the entire app

- [ ] Update `src/frontend/src/main.tsx` to read locale from preferences store
- [ ] Verify changing store language re-renders all translated text

---

## Task 3: Create Sidebar component

**Requirements:** Req 1 (criteria 1-5), Req 2 (criterion 1), Req 3 (criterion 1, 5), Req 4 (criterion 1)

Create `src/frontend/src/components/layout/Sidebar.tsx`:
- Collapsible left panel (260px expanded, 48px collapsed)
- Toggle button with menu/chevron icon
- Preferences section with:
  - Language selector: shadcn `Select` with options "Español" / "English"
  - Model selector: shadcn `Select` with options "Automático (recomendado)" / "Gemini 2.5 Flash (principal)" / "Groq Llama 3.3 70B (rápido)"
  - Auto-fallback: shadcn `Switch` with label and brief description
- Brief description below model selector explaining speed vs quality
- All labels use `useTranslation()` for i18n
- Responsive: desktop pushes content, mobile overlays with backdrop
- Accessible: keyboard navigation, proper aria labels

- [ ] Create `src/frontend/src/components/layout/Sidebar.tsx`
- [ ] Integrate with `usePreferencesStore` for read/write

---

## Task 4: Update AppShell layout to include Sidebar

**Requirements:** Req 1 (criteria 1, 4)

Modify `src/frontend/src/components/layout/AppShell.tsx`:
- Change layout from vertical-only to horizontal (sidebar + main column)
- Import and render `Sidebar` as first child in the flex row
- Main content area takes remaining space with `flex-1`
- Ensure mobile responsiveness (sidebar doesn't break small screens)

- [ ] Update `src/frontend/src/components/layout/AppShell.tsx`
- [ ] Verify layout works on desktop and mobile widths

---

## Task 5: Add i18n keys for sidebar and preferences

**Requirements:** Req 1 (criterion 5), Req 2 (criterion 1), Req 3 (criterion 1, 5), Req 4 (criterion 1)

Update `src/frontend/src/i18n/es.json` and `src/frontend/src/i18n/en.json`:
- Add `sidebar.preferences` section with keys for:
  - Section title
  - Language label and options
  - Model label and options with descriptions
  - Auto-fallback label and description
  - Collapse/expand tooltips

- [ ] Update `src/frontend/src/i18n/es.json` with sidebar keys
- [ ] Update `src/frontend/src/i18n/en.json` with sidebar keys

---

## Task 6: Inject preference headers into API client

**Requirements:** Req 5 (criterion 1)

Modify `src/frontend/src/api/client.ts`:
- Create helper `getPreferenceHeaders()` that reads from `usePreferencesStore.getState()`
- Returns `{ 'Accept-Language': language, 'X-Model-Preference': model, 'X-Auto-Fallback': autoFallback }`
- Inject these headers into the existing fetch wrapper or modify all fetch calls to include them
- Ensure headers are included on all API calls that could trigger LLM work (upload, analyze, retry-llm, quality, query)

- [ ] Update `src/frontend/src/api/client.ts` with preference headers
- [ ] Verify headers are sent on API requests (browser DevTools)

---

## Task 7: Create backend request preferences middleware

**Requirements:** Req 5 (criteria 2-5)

Create `src/backend/app/middleware/preferences.py`:
- Define `RequestPreferences` dataclass: `language`, `model_override`, `auto_fallback`
- Define `get_request_preferences(request: Request) -> RequestPreferences` FastAPI dependency
- Parse `Accept-Language` header (default: `es`, take first 2 chars)
- Parse `X-Model-Preference` header (default: `None` meaning task-default)
- Parse `X-Auto-Fallback` header (default: `true`)

- [ ] Create `src/backend/app/middleware/preferences.py`
- [ ] Add as dependency in relevant API endpoints

---

## Task 8: Update LLMClient to accept model override and fallback control

**Requirements:** Req 3 (criterion 3), Req 4 (criteria 2-3), Req 5 (criteria 3-4)

Modify `src/backend/app/analysis/llm_client.py`:
- Add `model_override: str | None = None` parameter to `call()`
- Add `auto_fallback: bool = True` parameter to `call()`
- If `model_override` is provided and is not `"default"`, use it instead of tier default
- If `auto_fallback` is False, on transient error raise immediately instead of trying fallback
- Maintain backward compatibility (existing calls without new params work unchanged)

- [ ] Update `LLMClient.call()` signature and logic
- [ ] Verify existing tests still pass (no breaking changes)

---

## Task 9: Update base analysis prompt with language parameter

**Requirements:** Req 6 (criterion 1)

Modify `src/backend/app/analysis/base_analysis/prompts.py`:
- Add `{response_language}` placeholder to PROMPT_TEMPLATE: "Respond in {response_language}."
- Keep all existing placeholders intact

Modify `src/backend/app/analysis/base_analysis/llm_analyzer.py`:
- Accept `language: str = "es"` parameter in `analyze()`
- Map language code to full name: `es` → `"Spanish"`, `en` → `"English"`
- Pass to prompt template as `response_language`

Modify callers (`BaseAnalysisService.analyze`, `BaseAnalysisService.retry_llm`):
- Accept and propagate `language` parameter
- Callers in API endpoints get language from `RequestPreferences`

- [ ] Update `src/backend/app/analysis/base_analysis/prompts.py`
- [ ] Update `src/backend/app/analysis/base_analysis/llm_analyzer.py`
- [ ] Update `src/backend/app/analysis/base_analysis/service.py` to propagate language
- [ ] Update `src/backend/app/api/v1/card.py` to inject preferences and pass language
- [ ] Update `src/backend/app/api/v1/documents.py` to inject preferences and pass language

---

## Task 10: Update quality analysis prompts with language parameter

**Requirements:** Req 6 (criterion 2)

Modify quality analysis prompt templates and services:
- `src/backend/app/analysis/quality/ambiguity_detector.py` — explanations in `ui_language`
- `src/backend/app/analysis/quality/completeness_evaluator.py` — explanations in `ui_language`
- `src/backend/app/analysis/quality/contradiction_detector.py` — explanations in `ui_language`
- `src/backend/app/analysis/quality/suggestion_generator.py` — suggestions in `document_language`

For each:
- Add `language` parameter to the analysis method
- Include "Respond in {language}" instruction in the prompt
- Suggestion generator uses `document_language` instead of `ui_language`

- [ ] Update ambiguity_detector with language parameter
- [ ] Update completeness_evaluator with language parameter
- [ ] Update contradiction_detector with language parameter
- [ ] Update suggestion_generator with document_language parameter
- [ ] Update quality service to propagate language from request preferences
- [ ] Update quality API endpoint to inject preferences

---

## Task 11: Update query/Q&A prompt with language parameter

**Requirements:** Req 6 (criterion 3)

Modify `src/backend/app/analysis/query/service.py`:
- Accept `language` parameter in query method
- Include "Respond in {language}" in the query prompt
- Pass language from API endpoint via RequestPreferences

- [ ] Update query service with language parameter
- [ ] Update query API endpoint to inject preferences

---

## Task 12: Integration verification

**Requirements:** All

Manual verification checklist:
- [ ] Start app, sidebar visible with preferences
- [ ] Change language → all UI labels switch immediately
- [ ] Upload document → card summary appears in selected language
- [ ] Change model → next analysis uses selected model (verify in backend logs)
- [ ] Disable auto-fallback → model failure shows error (if testable)
- [ ] Preferences persist across page reload
- [ ] Mobile layout: sidebar overlays correctly
- [ ] Build passes: `npx vite build`
