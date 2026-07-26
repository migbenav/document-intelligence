# Requirements Document

User Preferences (Preferencias de Usuario)

## Introduction

This feature implements a user preferences panel accessible from a left sidebar, allowing users to configure the application's display language and the LLM model used for analyses. These preferences are cross-cutting: they affect how every analysis feature presents results (language) and which model processes the document (LLM selection).

The language preference determines the output language for summaries, explanations, and classifications (following the language rules in steering). The LLM selector lets the user choose between available models and configure auto-fallback behavior.

This feature covers PRD v2 capabilities C5 (Configuración LLM) and extends C2/C3/C4 with language-aware output.

## Relevant Documentation

- #[[file:docs/product/03-prd v2.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:.kiro/steering/language-rules.md]]
- #[[file:.kiro/steering/tech.md]]
- #[[file:src/backend/app/analysis/llm_client.py]]
- #[[file:src/frontend/src/i18n/es.json]]
- #[[file:src/frontend/src/i18n/en.json]]

## Feature Boundaries

**In scope:**
- Left sidebar panel with preferences UI (collapsible).
- Language selector (español, inglés) that controls UI labels and LLM output language.
- LLM model selector (Gemini 2.5 Flash, Groq Llama 3.3 70B) with role indication (primary/light).
- Auto-fallback toggle: enable/disable automatic retry with alternate model on failure.
- Persistence of preferences in localStorage (frontend) and propagation to backend on each request.
- Backend receives `ui_language` and `model_preference` via request headers or parameters.
- All existing prompts updated to include language instruction based on `ui_language`.
- i18n system already exists; this feature ensures the selector is exposed to the user.

**Out of scope:**
- User accounts or server-side preference storage (MVP uses localStorage only).
- Adding new languages beyond es/en.
- Custom model endpoints or API key management by the user.
- Per-analysis model override (all analyses use the same selected model in MVP).
- Model cost estimation or usage tracking.

## Glossary

| Term | Definition |
|------|------------|
| ui_language | The language selected by the user for the application interface and LLM-generated explanations/summaries. |
| document_language | The language detected during ingestion (from IR metadata). Used for suggestions and extracted text. |
| Auto-fallback | When enabled, if the selected LLM fails, the system automatically retries with the alternate model. |
| Primary model | Gemini 2.5 Flash — used for deep analyses (on-demand, queries). |
| Light model | Groq Llama 3.3 70B — used for fast tasks (base analysis). |
| Sidebar | A collapsible left panel in the app layout containing navigation and user preferences. |

---

## Requirements

### Requirement 1: Sidebar Layout

**User Story:** As a user, I want a left sidebar that provides quick access to application settings so that I can configure my preferences without leaving the main workflow.

#### Acceptance Criteria

1. WHEN the application loads, THE UI SHALL display a collapsible left sidebar with an icon-based toggle button to expand/collapse it.
2. WHEN the sidebar is expanded, IT SHALL show sections for: navigation (future: document list) and preferences (language, model).
3. WHEN the sidebar is collapsed, IT SHALL show only icons for each section, with tooltips on hover.
4. THE sidebar SHALL NOT interfere with the main content area (document upload, card display). On small screens (< 768px), the sidebar SHALL overlay the content when expanded.
5. THE sidebar SHALL use shadcn/ui components and follow existing Tailwind CSS patterns.

---

### Requirement 2: Language Selector

**User Story:** As a user, I want to choose the application language so that all labels, explanations, and AI-generated summaries are in my preferred language.

#### Acceptance Criteria

1. WHEN the user opens the preferences section in the sidebar, THE UI SHALL display a language selector with options: "Español" and "English".
2. WHEN the user selects a language, THE UI SHALL immediately update all visible labels and text to the selected language (using the existing i18n system).
3. WHEN the user selects a language, THE preference SHALL be persisted in localStorage under key `user_preferences.language` so it survives page reloads.
4. WHEN a new analysis is triggered after changing the language, THE LLM output (summary, classification labels, explanations) SHALL be in the newly selected language.
5. THE default language SHALL be `es` (Spanish) if no preference is stored.
6. WHEN the language changes, existing analysis results already stored in the database SHALL NOT be re-generated automatically. Only new analyses will use the new language.

---

### Requirement 3: LLM Model Selector

**User Story:** As a user, I want to choose which AI model processes my documents so that I can balance speed vs quality based on my needs.

#### Acceptance Criteria

1. WHEN the user opens the preferences section in the sidebar, THE UI SHALL display a model selector showing available models with their role: "Gemini 2.5 Flash (principal)" and "Groq Llama 3.3 70B (rápido)".
2. WHEN the user selects a model, THE preference SHALL be persisted in localStorage under key `user_preferences.model`.
3. WHEN an analysis is triggered, THE backend SHALL use the model specified in the request (received via `X-Model-Preference` header) instead of the hardcoded default.
4. IF the request does not include a model preference header, THE backend SHALL use the default model assignment (Groq for base analysis, Gemini for on-demand).
5. THE UI SHALL display a brief description of each model's characteristics (speed vs depth) to help the user decide.

---

### Requirement 4: Auto-Fallback Configuration

**User Story:** As a user, I want to configure whether the system should automatically try an alternate model if my chosen model fails, so that I can control reliability vs predictability.

#### Acceptance Criteria

1. WHEN the user opens the preferences section, THE UI SHALL display a toggle switch labeled "Auto-fallback" (or equivalent in the selected language) with a brief explanation.
2. WHEN auto-fallback is enabled and the selected model fails, THE system SHALL automatically retry the same request with the alternate model and inform the user which model produced the result.
3. WHEN auto-fallback is disabled and the selected model fails, THE system SHALL show an error with options to "Retry" or "Change model".
4. THE auto-fallback preference SHALL be persisted in localStorage under key `user_preferences.autoFallback`.
5. THE default value SHALL be `true` (auto-fallback enabled).

---

### Requirement 5: Backend Preference Propagation

**User Story:** As a developer, I need the backend to receive and use user preferences so that LLM calls respect the user's language and model choices.

#### Acceptance Criteria

1. WHEN the frontend makes any API request that may trigger an LLM call, IT SHALL include headers: `Accept-Language` (value: `es` or `en`) and `X-Model-Preference` (value: model identifier or empty for default) and `X-Auto-Fallback` (value: `true` or `false`).
2. WHEN the backend receives a request with `Accept-Language`, IT SHALL pass the language value to the prompt context so the LLM responds in the specified language (for summaries and explanations, per language rules).
3. WHEN the backend receives a request with `X-Model-Preference`, IT SHALL use that model via LiteLLM instead of the default for the task type.
4. WHEN the backend receives a request with `X-Auto-Fallback: true` and the primary model call fails, IT SHALL retry with the alternate model before returning an error.
5. IF any preference header is missing, THE backend SHALL use defaults: language=es, model=task-default, autoFallback=true.

---

### Requirement 6: Update Existing Prompts

**User Story:** As a user, I want analyses to respect my language preference immediately so that new results are always in my chosen language.

#### Acceptance Criteria

1. WHEN the base analysis prompt is executed, IT SHALL include the instruction: "Respond in {ui_language}" where `{ui_language}` is the full language name (e.g., "Spanish", "English").
2. WHEN the quality analysis prompts are executed (contradictions, ambiguity, completeness, suggestions), THEY SHALL include appropriate language instructions per the language rules: explanations in `ui_language`, suggestions in `document_language`.
3. WHEN the query/Q&A prompt is executed, IT SHALL respond in `ui_language`.
4. ALL prompt templates SHALL accept a `language` parameter without changing the prompt structure or variable naming.
