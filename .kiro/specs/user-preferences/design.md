# Design Document

User Preferences — Sidebar, Language & LLM Configuration

## Overview

This design adds a collapsible left sidebar to the application layout containing user preferences: language selector and LLM model configuration. The preferences are stored in localStorage, propagated to the backend via HTTP headers, and consumed by prompt templates to control output language and model routing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser                                  │
│                                                                  │
│  ┌──────────┐    ┌────────────────────────────────────────────┐ │
│  │ Sidebar  │    │           Main Content Area                │ │
│  │          │    │                                            │ │
│  │ [Lang]   │    │  UploadPage / DocumentCard / Analysis      │ │
│  │ [Model]  │    │                                            │ │
│  │ [Fallbk] │    │                                            │ │
│  │          │    │                                            │ │
│  └──────────┘    └────────────────────────────────────────────┘ │
│                                                                  │
│  Zustand Store: usePreferencesStore                              │
│    ├── language: 'es' | 'en'                                    │
│    ├── model: string                                            │
│    └── autoFallback: boolean                                    │
│                                                                  │
│  localStorage: user_preferences                                  │
└─────────────────────────────────────────────────────────────────┘
          │
          │ HTTP Headers on every API request:
          │   Accept-Language: es | en
          │   X-Model-Preference: gemini/gemini-2.5-flash | groq/llama-...
          │   X-Auto-Fallback: true | false
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Backend (FastAPI)                         │
│                                                                  │
│  Middleware: extract preferences from headers → RequestContext    │
│                                                                  │
│  LLMClient.call(prompt, *, model_tier, language, model_override) │
│    - Reads model from override or defaults to tier assignment     │
│    - Fallback logic uses autoFallback from context                │
│                                                                  │
│  Prompt templates: include "Respond in {language}" instruction    │
└─────────────────────────────────────────────────────────────────┘
```

## Component Design

### Frontend

#### 1. `usePreferencesStore` (Zustand store)

```typescript
// src/frontend/src/store/preferencesStore.ts

interface PreferencesState {
  language: 'es' | 'en';
  model: string;
  autoFallback: boolean;
  setLanguage: (lang: 'es' | 'en') => void;
  setModel: (model: string) => void;
  setAutoFallback: (enabled: boolean) => void;
}
```

- Initializes from `localStorage.getItem('user_preferences')` on creation.
- Every setter persists to localStorage immediately.
- Defaults: `{ language: 'es', model: 'default', autoFallback: true }`.
- `model: 'default'` means use the task-default assignment (Groq for base, Gemini for deep).

#### 2. `Sidebar` component

```
src/frontend/src/components/layout/Sidebar.tsx
```

Structure:
- Collapsible panel on the left (width: 260px expanded, 48px collapsed).
- Toggle button with icon (menu/chevron).
- Sections:
  - **Preferencias** heading
  - Language selector (shadcn Select component)
  - Model selector (shadcn Select component)
  - Auto-fallback toggle (shadcn Switch component)

Uses `usePreferencesStore` for read/write.

Responsive behavior:
- Desktop (>= 768px): sidebar is beside main content, pushes it.
- Mobile (< 768px): sidebar overlays content when expanded, with backdrop.

#### 3. Updated `AppShell` layout

```tsx
// Current:
<div className="flex min-h-screen flex-col">
  <Header />
  <main>{children}</main>
</div>

// New:
<div className="flex min-h-screen">
  <Sidebar />
  <div className="flex flex-1 flex-col">
    <Header />
    <main>{children}</main>
  </div>
</div>
```

#### 4. Updated `TranslationProvider`

The `main.tsx` currently passes no locale (defaults to `'en'`). Updated to read from the preferences store:

```tsx
// main.tsx wraps App with a component that reads the store:
function LocalizedApp() {
  const language = usePreferencesStore((s) => s.language);
  return (
    <TranslationProvider locale={language}>
      <App />
    </TranslationProvider>
  );
}
```

#### 5. API client header injection

The existing `src/frontend/src/api/client.ts` needs a wrapper or interceptor that adds preference headers to every `fetch` call:

```typescript
function getPreferenceHeaders(): Record<string, string> {
  const prefs = usePreferencesStore.getState();
  return {
    'Accept-Language': prefs.language,
    'X-Model-Preference': prefs.model,
    'X-Auto-Fallback': String(prefs.autoFallback),
  };
}
```

This is injected into the existing fetch calls via a shared `apiFetch` wrapper or by modifying the existing `fetch` calls in `client.ts`.

### Backend

#### 6. Request context middleware

```python
# src/backend/app/middleware/preferences.py

@dataclass
class RequestPreferences:
    language: str  # 'es' | 'en'
    model_override: str | None  # None means use task default
    auto_fallback: bool

def get_request_preferences(request: Request) -> RequestPreferences:
    """Extract user preferences from request headers."""
    return RequestPreferences(
        language=request.headers.get("accept-language", "es")[:2],
        model_override=request.headers.get("x-model-preference") or None,
        auto_fallback=request.headers.get("x-auto-fallback", "true").lower() == "true",
    )
```

This is a FastAPI dependency injected into endpoints that trigger LLM calls.

#### 7. LLMClient updates

Add optional parameters to `LLMClient.call()`:

```python
async def call(
    self,
    prompt: str,
    *,
    model_tier: Literal["primary", "light"] = "primary",
    temperature: float = 0.1,
    model_override: str | None = None,
    auto_fallback: bool = True,
) -> LLMResponse:
```

- `model_override`: if provided and not `"default"`, use this model instead of the tier default.
- `auto_fallback`: if False, don't attempt fallback on transient errors — raise immediately.

#### 8. Prompt template updates

All prompt templates gain a `language` parameter:

```python
# base_analysis/prompts.py
PROMPT_TEMPLATE = """\
You are a document analysis assistant. Analyze the following document excerpt.
Respond in {response_language}.
...
"""

# Called with:
prompt = PROMPT_TEMPLATE.format(
    title=title,
    organization_type=org_type,
    text_sample=sample,
    response_language="Spanish" if language == "es" else "English",
)
```

Same pattern for quality analysis prompts and query prompts.

## Data Flow

### Language change:
1. User clicks "English" in sidebar → `setLanguage('en')` → localStorage updated
2. React re-renders `TranslationProvider` with `locale='en'` → all UI labels switch
3. Next API call includes `Accept-Language: en`
4. Backend prompt includes "Respond in English" → LLM responds in English

### Model change:
1. User selects "Gemini 2.5 Flash" → `setModel('gemini/gemini-2.5-flash')` → localStorage
2. Next API call includes `X-Model-Preference: gemini/gemini-2.5-flash`
3. Backend `LLMClient.call()` uses override instead of tier default

### Fallback flow:
1. Auto-fallback enabled, selected model fails
2. LLMClient detects transient error → retries with fallback model
3. Response includes `model_id` of actual model used
4. Frontend can display "Generated by {model}" if desired

## Available Models

| Identifier | Display Name | Role | Speed |
|---|---|---|---|
| `gemini/gemini-2.5-flash` | Gemini 2.5 Flash | Principal (análisis profundo) | Medium |
| `groq/llama-3.3-70b-versatile` | Groq Llama 3.3 70B | Rápido (análisis base) | Fast |
| `default` | Automático (recomendado) | Uses task-appropriate model | — |

## File Changes Summary

| File | Change |
|------|--------|
| `src/frontend/src/store/preferencesStore.ts` | **New** — Zustand store with localStorage sync |
| `src/frontend/src/components/layout/Sidebar.tsx` | **New** — Collapsible sidebar with preferences UI |
| `src/frontend/src/components/layout/AppShell.tsx` | **Modified** — Add Sidebar to layout |
| `src/frontend/src/main.tsx` | **Modified** — Wire locale from store to TranslationProvider |
| `src/frontend/src/api/client.ts` | **Modified** — Add preference headers to requests |
| `src/frontend/src/i18n/es.json` | **Modified** — Add sidebar/preferences translation keys |
| `src/frontend/src/i18n/en.json` | **Modified** — Add sidebar/preferences translation keys |
| `src/backend/app/middleware/preferences.py` | **New** — Request preferences extraction |
| `src/backend/app/analysis/llm_client.py` | **Modified** — Add model_override and auto_fallback params |
| `src/backend/app/analysis/base_analysis/prompts.py` | **Modified** — Add language parameter |
| `src/backend/app/analysis/base_analysis/llm_analyzer.py` | **Modified** — Pass language to prompt |
| `src/backend/app/analysis/quality/*.py` | **Modified** — Pass language to prompts |
| `src/backend/app/analysis/query/service.py` | **Modified** — Pass language to prompt |
| `src/backend/app/api/v1/card.py` | **Modified** — Inject RequestPreferences dependency |
| `src/backend/app/api/v1/documents.py` | **Modified** — Inject RequestPreferences dependency |

## Database Changes

**None required.** Preferences are stored client-side in localStorage. The backend is stateless regarding preferences — they come in via headers per-request.

## Supabase Changes

**None required.**

## Testing Strategy

- Unit tests for `usePreferencesStore` (localStorage read/write, defaults).
- Component test for Sidebar (renders selectors, dispatches changes).
- Integration test: verify API calls include correct headers after preference change.
- Backend unit test: `get_request_preferences` parses headers correctly.
- Backend unit test: `LLMClient.call` respects `model_override` and `auto_fallback`.
- Manual test: change language → verify card summary language changes on next upload.
