# Design — User Preferences (Preferencias de Usuario)

## Overview

This document describes the technical design for the User Preferences feature. It covers the architecture, component structure, API contracts, data flow, and key technical decisions for implementing a left sidebar with language selection, LLM model configuration, and auto-fallback control.

The preferences panel gives users immediate control over two cross-cutting concerns: the language used for all AI-generated output and UI labels, and the LLM model used for all analyses. Preferences are stored client-side (localStorage) and propagated to the backend via HTTP headers on every request, making the backend stateless with respect to user settings.

## Relevant Documentation

- #[[file:.kiro/specs/user-preferences/requirements.md]]
- #[[file:.kiro/steering/language-rules.md]]
- #[[file:.kiro/steering/tech.md]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/frontend/src/i18n/index.ts]]
- #[[file:src/frontend/src/store/uploadStore.ts]]
- #[[file:src/frontend/src/components/layout/AppShell.tsx]]

---

## Architecture

### System Context

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Browser                                       │
│                                                                            │
│  ┌────────────┐   ┌──────────────────────────────────────────────────┐   │
│  │  Sidebar   │   │              Main Content Area                    │   │
│  │            │   │                                                    │   │
│  │  [Lang]    │   │  UploadPage / DocumentCard / Quality / Query      │   │
│  │  [Model]   │   │                                                    │   │
│  │  [Fallbk]  │   │                                                    │   │
│  │            │   │                                                    │   │
│  └─────┬──────┘   └──────────────────────────────────────────────────┘   │
│        │                                                                   │
│        ▼                                                                   │
│  Zustand: usePreferencesStore ──▶ localStorage('user_preferences')         │
│        │                                                                   │
│        ├──▶ TranslationProvider (locale prop updates reactively)           │
│        └──▶ API Client (injects headers on every request)                 │
└──────────────────────────────────────────────────────────────────────────┘
                         │
                         │  HTTP Headers:
                         │    Accept-Language: es | en
                         │    X-Model-Preference: model-id | default
                         │    X-Auto-Fallback: true | false
                         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        Backend (FastAPI)                                    │
│                                                                            │
│  FastAPI Dependency: get_request_preferences(request) → RequestPreferences │
│        │                                                                   │
│        ├──▶ LLMClient.call(prompt, model_override=..., auto_fallback=...) │
│        │                                                                   │
│        └──▶ Prompt templates: "Respond in {response_language}."           │
└──────────────────────────────────────────────────────────────────────────┘
```

### Internal Module Decomposition

The feature spans frontend and backend with the following new or modified modules:

1. **usePreferencesStore** (Zustand) — State management with localStorage persistence. Single source of truth for language, model, and fallback preferences.
2. **Sidebar** (React component) — Collapsible left panel rendering preference selectors using shadcn/ui components.
3. **API Client headers** — Middleware layer in the fetch wrapper that injects preference headers.
4. **RequestPreferences** (FastAPI dependency) — Extracts preferences from HTTP headers, provides them to endpoint handlers.
5. **LLMClient extensions** — New parameters for model override and fallback control.
6. **Prompt templates** — All existing prompts gain a `{response_language}` placeholder.

---

## Components and Interfaces

### Component Overview

| Component | Responsibility | Exposes | Consumes |
|-----------|---------------|---------|----------|
| `store/preferencesStore.ts` | Preferences state + localStorage sync | `usePreferencesStore` hook | localStorage |
| `components/layout/Sidebar.tsx` | Preferences UI panel | React component | `usePreferencesStore`, `useTranslation` |
| `components/layout/AppShell.tsx` | App layout with sidebar | React component | `Sidebar` |
| `api/client.ts` | HTTP wrapper with preference headers | `apiFetch()` or header injection | `usePreferencesStore` |
| `middleware/preferences.py` | Extract preferences from request | `get_request_preferences()` dependency | FastAPI Request |
| `analysis/llm_client.py` | LLM calls with override support | `LLMClient.call()` | LiteLLM, RequestPreferences |
| `analysis/*/prompts.py` | Language-aware prompt templates | `PROMPT_TEMPLATE` | Language parameter |

### Key Interfaces

```typescript
// --- Frontend: Preferences Store ---

interface PreferencesState {
  language: 'es' | 'en';
  model: string;           // 'default' | 'gemini/gemini-2.5-flash' | 'groq/llama-3.3-70b-versatile'
  autoFallback: boolean;
}

interface PreferencesActions {
  setLanguage: (lang: 'es' | 'en') => void;
  setModel: (model: string) => void;
  setAutoFallback: (enabled: boolean) => void;
}

// Defaults:
// { language: 'es', model: 'default', autoFallback: true }
```

```python
# --- Backend: Request Preferences ---

@dataclass
class RequestPreferences:
    """User preferences extracted from HTTP request headers."""
    language: str            # 'es' | 'en' — from Accept-Language
    model_override: str | None  # None means use task-default assignment
    auto_fallback: bool      # from X-Auto-Fallback header


def get_request_preferences(request: Request) -> RequestPreferences:
    """FastAPI dependency that extracts user preferences from headers.

    Defaults: language='es', model_override=None, auto_fallback=True
    """
    ...
```

```python
# --- Backend: Updated LLMClient.call() signature ---

async def call(
    self,
    prompt: str,
    *,
    model_tier: Literal["primary", "light"] = "primary",
    temperature: float = 0.1,
    model_override: str | None = None,    # NEW: override tier default
    auto_fallback: bool = True,           # NEW: disable fallback if False
) -> LLMResponse:
    """Make an LLM call with optional model override and fallback control.

    - model_override: if provided and != 'default', use this model instead of tier default.
    - auto_fallback: if False, raise immediately on transient error (no fallback attempt).
    """
    ...
```

---

## Data Models

### Preferences (Client-Side Only)

```typescript
// Stored in localStorage under key 'user_preferences'
interface StoredPreferences {
  language: 'es' | 'en';
  model: string;
  autoFallback: boolean;
}
```

No database table or migration is needed. Preferences are ephemeral and per-browser.

### Available Models Configuration

```typescript
// Static configuration — not user-configurable in MVP
const AVAILABLE_MODELS = [
  {
    id: 'default',
    nameKey: 'sidebar.model.options.default',  // "Automático (recomendado)"
    descriptionKey: 'sidebar.model.options.defaultDesc',
    role: null,
  },
  {
    id: 'gemini/gemini-2.5-flash',
    nameKey: 'sidebar.model.options.gemini',  // "Gemini 2.5 Flash"
    descriptionKey: 'sidebar.model.options.geminiDesc',
    role: 'primary',
  },
  {
    id: 'groq/llama-3.3-70b-versatile',
    nameKey: 'sidebar.model.options.groq',  // "Groq Llama 3.3 70B"
    descriptionKey: 'sidebar.model.options.groqDesc',
    role: 'light',
  },
] as const;
```

---

## API Design

### Preference Headers (Frontend → Backend)

Every API request that may trigger LLM work includes these headers:

| Header | Values | Default | Purpose |
|--------|--------|---------|---------|
| `Accept-Language` | `es`, `en` | `es` | Controls LLM output language for summaries/explanations |
| `X-Model-Preference` | model identifier or `default` | `default` | Override the task-default model |
| `X-Auto-Fallback` | `true`, `false` | `true` | Enable/disable automatic retry with alternate model |

No new API endpoints are created. Existing endpoints are modified to accept and use these headers.

### Affected Endpoints

| Endpoint | How preferences are used |
|----------|--------------------------|
| `POST /api/v1/documents/upload` | Language → prompt for base analysis; Model → LLM call |
| `POST /api/v1/documents/{id}/card/retry-llm` | Language → prompt; Model → LLM call |
| `POST /api/v1/documents/{id}/analyze` | Language → prompts; Model → LLM calls |
| `POST /api/v1/documents/{id}/quality-analysis` | Language → prompts; Model → LLM calls |
| `POST /api/v1/documents/{id}/query` | Language → prompt; Model → LLM call |

---

## Key Technical Decisions

### Decision 1: localStorage over Server-Side Storage

**Choice:** Store preferences exclusively in the browser's localStorage, not in a database.

**Reasoning:** The MVP has no user accounts. Server-side storage would require authentication infrastructure that doesn't exist yet. localStorage is immediate, works offline, and survives page reloads. The tradeoff is that preferences don't sync across devices — acceptable for MVP.

### Decision 2: HTTP Headers over Query Parameters

**Choice:** Propagate preferences via HTTP headers (`Accept-Language`, custom `X-` headers) rather than query parameters or request body fields.

**Reasoning:** Headers are transparent to the API contract — they don't change endpoint signatures or request schemas. `Accept-Language` is a standard HTTP header. Custom `X-` headers are a well-understood pattern for request metadata. This avoids modifying every request body schema.

### Decision 3: Sidebar Layout (Push, Not Overlay on Desktop)

**Choice:** On desktop (≥768px), the sidebar pushes the main content to the right when expanded. On mobile (<768px), it overlays with a backdrop.

**Reasoning:** Push layout avoids content being hidden behind the sidebar. The main content area already uses `max-w` constraints, so the reduced width won't break the layout. On mobile, the sidebar is used infrequently enough that an overlay is acceptable and saves permanent screen real estate.

### Decision 4: model='default' Means Task-Default Assignment

**Choice:** When the user selects "Automático (recomendado)", the model preference is `"default"`, which tells the backend to use the standard task-based assignment (Groq for base analysis, Gemini for deep analyses).

**Reasoning:** This preserves the optimized model routing from the tech steering (light model for fast tasks, primary model for deep analysis). Users who don't want to think about models get the best default behavior. Users who explicitly choose a model override the task-based routing.

### Decision 5: Prompt Language Instruction Placement

**Choice:** Add the language instruction as the first line of the LLM prompt: `"Respond in {response_language}."` before the rest of the prompt content.

**Reasoning:** Placing the language instruction first gives it high priority in the model's attention. The rest of the prompt (in English) remains unchanged for maximum model performance. Testing shows models follow first-line language instructions reliably.

### Decision 6: Backward-Compatible LLMClient

**Choice:** Add `model_override` and `auto_fallback` as optional keyword parameters with defaults matching current behavior (`None` and `True`).

**Reasoning:** Existing callers (tests, other features) continue to work without changes. New callers pass the preferences when available. This is a non-breaking extension.

---

## Correctness Properties

### Property 1: Preference Persistence

*For any* language, model, or fallback change made by the user, the preference SHALL be immediately written to localStorage and SHALL survive page reloads. Reading the store after reload SHALL return the last persisted values.

**Validates: Requirements 2.3, 3.2, 4.4**

### Property 2: Immediate UI Language Switch

*For any* language change, all visible UI labels and text rendered via `useTranslation()` SHALL update reactively without requiring a page reload.

**Validates: Requirements 2.2**

### Property 3: Header Propagation Completeness

*For any* API request that may trigger an LLM call, the request SHALL include all three preference headers. Missing headers on the backend SHALL fall back to defaults without error.

**Validates: Requirements 5.1, 5.5**

### Property 4: Model Override Determinism

*For any* request where `X-Model-Preference` is not `"default"`, the backend SHALL route the LLM call to exactly that model (via LiteLLM), regardless of the task tier assignment.

**Validates: Requirements 3.3**

### Property 5: Fallback Control

*For any* request where `X-Auto-Fallback` is `"false"`, a transient failure from the selected model SHALL result in an immediate error response without attempting the alternate model.

**Validates: Requirements 4.2, 4.3**

### Property 6: Language in LLM Output

*For any* analysis triggered after a language preference change, the LLM output (summary, explanations, classifications) SHALL be in the newly selected language. Existing stored results SHALL NOT be affected.

**Validates: Requirements 2.4, 2.6, 6.1**

---

## Interaction Flow

```
=== USER CHANGES LANGUAGE ===

1. User expands sidebar, selects "English" in language dropdown
       │
       ▼
2. usePreferencesStore.setLanguage('en')
       ├── State updates: language = 'en'
       ├── localStorage.setItem('user_preferences', {..., language: 'en'})
       │
       ▼
3. LocalizedApp re-renders TranslationProvider with locale='en'
       │
       ▼
4. All components using useTranslation() re-render with English labels
       │
       ▼
5. Next API request includes: Accept-Language: en
       │
       ▼
6. Backend prompt includes: "Respond in English."
       │
       ▼
7. LLM response is in English → saved to DB → shown to user


=== USER CHANGES MODEL ===

1. User selects "Gemini 2.5 Flash" in model dropdown
       │
       ▼
2. usePreferencesStore.setModel('gemini/gemini-2.5-flash')
       ├── State updates: model = 'gemini/gemini-2.5-flash'
       ├── localStorage persisted
       │
       ▼
3. Next API request includes: X-Model-Preference: gemini/gemini-2.5-flash
       │
       ▼
4. Backend: get_request_preferences() reads model_override = 'gemini/gemini-2.5-flash'
       │
       ▼
5. LLMClient.call(prompt, model_override='gemini/gemini-2.5-flash')
       │
       ▼
6. LiteLLM routes to Gemini instead of task-default


=== AUTO-FALLBACK DISABLED + MODEL FAILURE ===

1. User disables auto-fallback toggle
2. User triggers analysis → model fails (rate limit)
       │
       ▼
3. Backend: auto_fallback=False → LLMClient raises LLMTransientError immediately
       │
       ▼
4. API returns error response
       │
       ▼
5. Frontend shows error with options: "Reintentar" / "Cambiar modelo"
```

---

## Error Handling

| Error Source | Condition | Behavior | Recovery |
|-------------|-----------|----------|----------|
| localStorage unavailable | Private browsing, quota | Preferences use in-memory defaults | No persistence across reloads |
| Invalid stored preferences | Corrupted JSON | Fall back to defaults, overwrite | Self-healing |
| Missing preference headers (backend) | Frontend bug or direct API call | Use defaults (es, task-default, true) | Graceful degradation |
| Model override not recognized | Typo or deprecated model | LiteLLM raises error → fallback (if enabled) or error | User changes model |
| Both models fail with fallback enabled | Service outage | Partial card (base analysis) or error (other features) | Retry later |
| Selected model fails, fallback disabled | Rate limit, timeout | Immediate error to user | User retries or changes model |

---

## Security Considerations

- **No sensitive data in preferences:** Language and model choices are not personally identifiable information.
- **Headers cannot escalate privileges:** Custom headers only affect model routing and language — they cannot access additional data or bypass auth.
- **Model identifiers are validated:** The backend should validate `X-Model-Preference` against a whitelist of known model identifiers to prevent injection of arbitrary model strings into LiteLLM calls.
- **localStorage is per-origin:** Preferences are scoped to the app's domain and cannot be read by other sites.

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| `usePreferencesStore` | State management, localStorage read/write, defaults | Unit tests with mocked localStorage |
| `Sidebar` | Renders selectors, dispatches actions, responsive behavior | Component tests with Testing Library |
| API header injection | Correct headers on requests | Unit test for header helper function |
| `get_request_preferences` | Header parsing, defaults for missing headers | Unit tests with mock Request objects |
| `LLMClient` extensions | model_override routing, auto_fallback behavior | Unit tests with mocked LiteLLM |
| Prompt templates | Language placeholder interpolation | Unit tests verifying prompt content |
| Integration | Language change → card in new language | Manual test (LLM call required) |

---

## File Structure

```
src/frontend/
├── src/
│   ├── store/
│   │   └── preferencesStore.ts         # NEW: Zustand + localStorage
│   ├── components/
│   │   └── layout/
│   │       ├── Sidebar.tsx             # NEW: Collapsible preferences panel
│   │       └── AppShell.tsx            # MODIFIED: Include sidebar in layout
│   ├── api/
│   │   └── client.ts                  # MODIFIED: Inject preference headers
│   ├── i18n/
│   │   ├── es.json                    # MODIFIED: Add sidebar.* keys
│   │   └── en.json                    # MODIFIED: Add sidebar.* keys
│   └── main.tsx                       # MODIFIED: Wire locale from store

src/backend/
├── app/
│   ├── middleware/
│   │   └── preferences.py             # NEW: RequestPreferences extraction
│   ├── analysis/
│   │   ├── llm_client.py              # MODIFIED: model_override + auto_fallback params
│   │   ├── base_analysis/
│   │   │   ├── prompts.py             # MODIFIED: Add {response_language} placeholder
│   │   │   ├── llm_analyzer.py        # MODIFIED: Accept language param
│   │   │   └── service.py             # MODIFIED: Propagate language
│   │   ├── quality/
│   │   │   ├── ambiguity_detector.py  # MODIFIED: Add language to prompts
│   │   │   ├── completeness_evaluator.py  # MODIFIED: Add language to prompts
│   │   │   ├── contradiction_detector.py  # MODIFIED: Add language to prompts
│   │   │   └── suggestion_generator.py   # MODIFIED: Add document_language to prompts
│   │   └── query/
│   │       └── service.py             # MODIFIED: Add language to prompts
│   └── api/v1/
│       ├── card.py                    # MODIFIED: Inject RequestPreferences
│       ├── documents.py               # MODIFIED: Inject RequestPreferences
│       ├── quality.py                 # MODIFIED: Inject RequestPreferences
│       └── query.py                   # MODIFIED: Inject RequestPreferences
```

---

## Database Changes

**None.** No migrations, no new tables, no schema modifications. Preferences are client-side only.

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Sidebar Layout | `Sidebar.tsx`, `AppShell.tsx` modification, responsive behavior (push vs overlay), shadcn/ui components |
| Req 2: Language Selector | `usePreferencesStore.setLanguage()`, `Sidebar.tsx` Select, `main.tsx` TranslationProvider wiring, localStorage persistence |
| Req 3: LLM Model Selector | `usePreferencesStore.setModel()`, `Sidebar.tsx` Select with model descriptions, `X-Model-Preference` header, `LLMClient.call(model_override=...)` |
| Req 4: Auto-Fallback | `usePreferencesStore.setAutoFallback()`, `Sidebar.tsx` Switch, `X-Auto-Fallback` header, `LLMClient.call(auto_fallback=...)` |
| Req 5: Backend Propagation | `client.ts` header injection, `middleware/preferences.py`, `get_request_preferences()` FastAPI dependency, default values |
| Req 6: Prompt Updates | `{response_language}` in all prompt templates, language mapping (es→Spanish, en→English), callers propagate from RequestPreferences |
