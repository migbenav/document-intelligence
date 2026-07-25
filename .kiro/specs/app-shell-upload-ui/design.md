# Design — Application Shell & Document Upload UI

## Overview

This document describes the technical design for the Application Shell & Document Upload UI feature. It covers the frontend architecture, component structure, state management, API integration layer, internationalization approach, and key technical decisions required to implement the approved requirements.

This is the first frontend feature. It establishes the React + TypeScript + Vite project, installs the UI toolkit (Tailwind + shadcn/ui), configures state management (Zustand), and implements the upload workflow end-to-end against the existing backend API.

## Relevant Documentation

- #[[file:.kiro/specs/app-shell-upload-ui/requirements.md]]
- #[[file:.kiro/specs/document-ingestion/design.md]]
- #[[file:docs/architecture/001-technology-stack.md]]
- #[[file:docs/architecture/003-vertical-development-strategy.md]]

---

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Vercel)                        │
│  React + TypeScript + Vite + Tailwind + shadcn/ui + Zustand  │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  App Shell  │  │  Upload Flow │  │  API Client      │    │
│  │  (Layout)   │  │  (Pages)     │  │  (HTTP Layer)    │    │
│  └─────────────┘  └──────────────┘  └────────┬─────────┘    │
└───────────────────────────────────────────────┼──────────────┘
                                                │ HTTPS (CORS)
                                                ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend (Render)                            │
│  FastAPI — already implemented (Feature 1)                   │
│                                                              │
│  POST /api/v1/documents/upload  → 202 | 400 | 422           │
│  GET  /api/v1/documents/{id}/status → 200 | 404             │
└─────────────────────────────────────────────────────────────┘
```

### Frontend Internal Architecture

The frontend follows a layered architecture:

1. **Pages** — Top-level route components that compose UI from smaller components.
2. **Components** — Reusable UI building blocks (upload area, consent dialog, status display).
3. **Store** — Zustand store managing upload workflow state (file, status, errors).
4. **API Client** — Thin HTTP layer wrapping fetch/axios calls to the backend.
5. **i18n** — Translation files providing all user-facing strings.

```
Pages ──▶ Components ──▶ Store ──▶ API Client ──▶ Backend
                           │
                           └──▶ i18n (translation keys)
```

---

## Components and Interfaces

### Component Tree

```
<App>
  <AppShell>                          // Layout: header + main
    <Header />                        // App name, branding
    <main>
      <UploadPage>                    // Default landing view
        <UploadZone />                // Drag-drop area + file picker
        <FileInfo />                  // Selected file details (name, size, format)
        <ConsentDialog />             // Modal: privacy disclosure + accept/cancel
        <UploadProgress />            // Progress indicator during upload
        <ProcessingStatus />          // Polling indicator + result display
        <ErrorDisplay />              // Error messages with recovery actions
      </UploadPage>
    </main>
  </AppShell>
</App>
```

### Component Responsibilities

| Component | Responsibility | Requirements |
|-----------|---------------|--------------|
| `AppShell` | Top-level layout with header and responsive main content area | Req 1 |
| `Header` | Application name, future navigation placeholder | Req 1 |
| `UploadPage` | Orchestrates the upload workflow states | Req 1, 3, 4, 5, 6 |
| `UploadZone` | Drag-and-drop area, file picker trigger, client-side validation | Req 3 |
| `FileInfo` | Displays selected file metadata (name, format, size) | Req 3 |
| `ConsentDialog` | Modal with privacy information, accept/cancel buttons | Req 2 |
| `UploadProgress` | Progress bar/spinner during file upload | Req 4 |
| `ProcessingStatus` | Displays polling state, success/failure result | Req 5 |
| `ErrorDisplay` | Renders error messages with retry/start-over actions | Req 6 |

---

## Data Models

### Zustand Store

A single Zustand store manages the upload workflow. The store is the single source of truth for the current workflow step, selected file, upload progress, and processing status.

```typescript
type UploadStep =
  | 'idle'            // No file selected
  | 'file-selected'   // File selected, awaiting consent
  | 'consent-pending' // Consent dialog open
  | 'uploading'       // Upload in progress
  | 'processing'      // Backend processing (polling)
  | 'ready'           // Document ready for analysis
  | 'error';          // Error state (upload or processing failed)

interface SelectedFile {
  file: File;
  name: string;
  size: number;
  format: 'markdown' | 'plain_text' | 'pdf';
}

interface UploadResult {
  documentId: string;
  filename: string;
  format: string;
  language: string | null;
  chunkCount: number | null;
  warnings: string[];
}

interface UploadError {
  type: 'validation' | 'network' | 'server' | 'processing' | 'connectivity';
  message: string;
  canRetry: boolean;
}

interface UploadStore {
  // State
  step: UploadStep;
  selectedFile: SelectedFile | null;
  uploadProgress: number;        // 0-100 percentage
  result: UploadResult | null;
  error: UploadError | null;
  documentId: string | null;

  // Actions
  selectFile: (file: File) => void;        // Validates + sets file
  openConsent: () => void;                 // Transitions to consent-pending
  acceptConsent: () => void;               // Triggers upload
  declineConsent: () => void;              // Returns to file-selected
  startUpload: () => Promise<void>;        // Calls API, manages progress
  startPolling: () => void;                // Begins status polling
  stopPolling: () => void;                 // Cleanup polling interval
  reset: () => void;                       // Returns to idle, clears all state
}
```

### State Transitions

```
idle ──[file selected]──▶ file-selected
                              │
                    [upload button clicked]
                              │
                              ▼
                      consent-pending
                         │         │
              [accept]   │         │  [decline/dismiss]
                         ▼         ▼
                     uploading    file-selected
                         │
              [202 received]   [error]
                    │              │
                    ▼              ▼
               processing       error ──[start over]──▶ idle
                    │
        [ready, chunks>0]   [failed or chunks=0]
              │                    │
              ▼                    ▼
            ready               error ──[start over]──▶ idle
```

---

## API Integration Layer

### HTTP Client Configuration

```typescript
// src/frontend/src/api/client.ts

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const UPLOAD_TIMEOUT_MS = 30_000;  // 30s for cold start tolerance
const POLL_INTERVAL_MS = 2_000;    // 2s between status polls
const MAX_POLL_FAILURES = 3;       // Stop polling after 3 consecutive failures
```

### API Functions

```typescript
// Upload a document file
async function uploadDocument(file: File): Promise<UploadResponse>
// Poll document processing status
async function getDocumentStatus(documentId: string): Promise<StatusResponse>
```

### Response Types (matching backend models)

```typescript
interface UploadResponse {
  document_id: string;
  status: 'processing' | 'ready' | 'failed';
  filename: string;
  format: string;
  language: string | null;
  chunk_count: number | null;
  warnings: string[];
  error_message: string | null;
}

interface StatusResponse {
  document_id: string;
  status: 'processing' | 'ready' | 'failed';
  filename: string;
  format: string;
  language: string | null;
  chunk_count: number | null;
  warnings: string[];
  error_message: string | null;
}

interface ApiErrorResponse {
  error: string;         // error code
  message: string;       // user-facing message
  supported_formats?: string[];
  max_size_bytes?: number;
  required_encoding?: string;
}
```

### Polling Logic

```typescript
// Polling is managed via setInterval + cleanup
// - Starts when step transitions to 'processing'
// - Stops on: terminal status (ready/failed), component unmount, or max failures
// - Uses an AbortController per request for cleanup on unmount
// - Consecutive failure counter resets on any successful response
```

---

## Client-Side Validation

Validation runs immediately on file selection, before consent or upload:

```typescript
const SUPPORTED_EXTENSIONS = ['.md', '.txt', '.pdf'] as const;
const SIZE_LIMIT_TEXT = 1_048_576;   // 1 MB (inclusive)
const SIZE_LIMIT_PDF = 10_485_760;   // 10 MB (inclusive)

function validateFile(file: File): ValidationResult {
  // 1. Check extension
  // 2. Check size against format-specific limit
  // Files at exactly the limit are accepted (strictly greater = rejected)
  // Returns: { valid: true, format } or { valid: false, errorKey, metadata }
}
```

The validation mirrors the backend Validator but runs client-side for instant feedback. The backend remains the authoritative validator — server-side errors from the 400 response are still displayed if they occur.

---

## Internationalization (i18n)

### Approach

Use a lightweight JSON-based translation system. No heavy library needed for the MVP — a simple React context with a translation lookup function is sufficient.

```
src/frontend/src/i18n/
├── index.ts          // useTranslation hook + TranslationProvider
├── en.json           // English translations (default)
└── es.json           // Spanish translations
```

### Translation Structure

```json
{
  "app": {
    "name": "Document Intelligence"
  },
  "upload": {
    "title": "Upload a document",
    "dropzone": "Drag and drop your file here, or click to browse",
    "formats": "Supported formats: .md, .txt, .pdf",
    "sizeLimits": "Max size: 1 MB (text), 10 MB (PDF)",
    "button": "Upload and Analyze"
  },
  "consent": {
    "title": "External Processing Notice",
    "body": "Your document will be sent to an external AI service for analysis...",
    "details": {
      "sent": "Only the document text and system prompts are sent.",
      "noPersonalData": "No personal data or usage history is transmitted.",
      "retention": "Document content is not retained beyond the analysis session."
    },
    "accept": "I understand, proceed",
    "decline": "Cancel"
  },
  "status": {
    "uploading": "Uploading document...",
    "processing": "Extracting text content...",
    "ready": "Document ready for analysis",
    "failed": "Processing failed"
  },
  "errors": {
    "unsupportedFormat": "This file format is not supported. Please upload a .md, .txt, or .pdf file.",
    "fileTooLarge": "File exceeds the size limit of {limit}.",
    "networkError": "Connection failed. Please check your network and try again.",
    "serverError": "Processing failed, please try again.",
    "connectivity": "Unable to reach the server. Please check your connection.",
    "noContent": "No extractable content was found in this document."
  },
  "actions": {
    "retry": "Try again",
    "startOver": "Start over",
    "selectFile": "Select a file"
  }
}
```

Backend error messages are displayed as-is (not translated) since the backend owns their content.

---

## CORS Configuration

The backend already has CORS middleware configured in `main.py` with `allow_origins=["*"]` for development. For production deployment:

- The `cors_origins` parameter should be set via environment variable to restrict to the Vercel frontend URL.
- The frontend needs no special CORS handling — the browser handles it transparently once the backend is configured.

### Backend Change Required

Add environment-based CORS origin configuration to the backend startup script:

```python
# In the production entrypoint (e.g., run.py or startup config)
import os
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app = create_app(supabase_client=client, cors_origins=cors_origins)
```

This is a minor configuration change, not a structural modification to the ingestion feature.

---

## File Structure

```
src/frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── .env.example                     # VITE_API_BASE_URL=http://localhost:8000
├── src/
│   ├── main.tsx                     # React entry point
│   ├── App.tsx                      # Root component with providers
│   ├── api/
│   │   ├── client.ts               # HTTP client configuration (base URL, timeouts)
│   │   └── documents.ts            # uploadDocument(), getDocumentStatus()
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx         # Header + main content wrapper
│   │   │   └── Header.tsx           # Application name header
│   │   ├── upload/
│   │   │   ├── UploadPage.tsx       # Page orchestrating the upload flow
│   │   │   ├── UploadZone.tsx       # Drag-drop + file picker area
│   │   │   ├── FileInfo.tsx         # Selected file metadata display
│   │   │   ├── ConsentDialog.tsx    # Privacy consent modal
│   │   │   ├── UploadProgress.tsx   # Upload progress indicator
│   │   │   ├── ProcessingStatus.tsx # Polling state + result display
│   │   │   └── ErrorDisplay.tsx     # Error messages with actions
│   │   └── ui/                      # shadcn/ui components (generated)
│   │       ├── button.tsx
│   │       ├── dialog.tsx
│   │       ├── progress.tsx
│   │       ├── alert.tsx
│   │       └── card.tsx
│   ├── store/
│   │   └── uploadStore.ts           # Zustand store for upload workflow
│   ├── i18n/
│   │   ├── index.ts                 # useTranslation hook + provider
│   │   ├── en.json                  # English strings
│   │   └── es.json                  # Spanish strings
│   ├── lib/
│   │   ├── validation.ts            # Client-side file validation logic
│   │   └── utils.ts                 # Tailwind cn() helper, formatBytes(), etc.
│   └── types/
│       └── api.ts                   # TypeScript interfaces for API responses
└── tests/
    ├── components/
    │   ├── UploadZone.test.tsx
    │   ├── ConsentDialog.test.tsx
    │   └── ProcessingStatus.test.tsx
    ├── store/
    │   └── uploadStore.test.ts
    └── api/
        └── documents.test.ts
```

---

## Key Technical Decisions

### Decision 1: Fetch API vs Axios

**Choice:** Native Fetch API with a thin wrapper.

**Reasoning:** The upload workflow needs progress tracking (via `XMLHttpRequest` `upload.onprogress` or ReadableStream), a custom timeout (30s for cold starts), and abort support (via `AbortController`). Fetch + `XMLHttpRequest` for upload progress provides these capabilities without adding a dependency. For a project this size, axios adds little value over a well-structured fetch wrapper.

**Fallback:** If upload progress tracking proves complex with fetch alone, use `XMLHttpRequest` specifically for the upload call while using fetch for polling.

### Decision 2: i18n Approach

**Choice:** Lightweight custom hook with JSON translation files.

**Reasoning:** The MVP has approximately 30-40 translatable strings. A full i18n library (react-intl, i18next) adds significant bundle size and complexity for minimal benefit. A simple `useTranslation()` hook that reads from a JSON dictionary is sufficient. If the string count grows significantly in later features, migrating to i18next is straightforward since the pattern (key-based lookup) is the same.

### Decision 3: Polling vs WebSocket/SSE

**Choice:** HTTP polling (setInterval + fetch).

**Reasoning:** The backend already has a `GET /status` endpoint designed for polling. The processing time is typically short (a few seconds). Polling at 2-second intervals is simple, reliable, and doesn't require backend changes. WebSocket/SSE adds complexity (connection management, reconnection) for negligible UX improvement given the short processing duration.

### Decision 4: Zustand Store Granularity

**Choice:** Single store for the entire upload workflow.

**Reasoning:** The upload workflow is a single linear flow with clear state transitions. Splitting into multiple stores would add indirection without benefit. One store makes state transitions explicit and testable. If future features need their own state (e.g., Knowledge Model viewer), they get their own stores — this keeps concerns separated by feature.

### Decision 5: shadcn/ui Component Selection

**Choice:** Use shadcn/ui `Dialog`, `Button`, `Progress`, `Alert`, and `Card` components.

**Reasoning:** These cover all UI needs for this feature: Dialog for consent, Button for actions, Progress for upload indicator, Alert for warnings/errors, Card for the upload zone. shadcn/ui components are copied into the project (no runtime dependency), fully customizable, and accessible by default (built on Radix UI primitives).

### Decision 6: Cold Start Handling

**Choice:** Extended timeout (30s) on the first request + visual feedback if response takes > 3 seconds.

**Reasoning:** Render free tier takes ~30s to wake. Rather than showing an error, the UI shows an informational message ("Starting up, this may take a moment...") after 3 seconds of waiting. The actual timeout is set to 30s. This avoids false errors while keeping the user informed.

---

## Correctness Properties

These invariants must hold for the frontend upload workflow to be considered correct:

### Property 1: Consent Gate

No file data is transmitted to the backend unless the user has explicitly clicked the acceptance button in the consent dialog. Dismissing, closing, or declining the dialog must never result in any network request carrying file content.

**Validates: Requirements 2.3, 2.4**

### Property 2: Validation Before Upload

A file that fails client-side validation (unsupported extension or exceeds size limit) never triggers a consent dialog or upload request. The user sees an error immediately upon file selection.

**Validates: Requirements 3.3, 3.4, 3.5**

### Property 3: Single Upload Atomicity

At any point in time, at most one upload operation is in progress. The UI disables the upload control during upload and polling, preventing duplicate submissions.

**Validates: Requirements 4.2**

### Property 4: Polling Cleanup

When the component unmounts, navigates away, or reaches a terminal state (ready, failed, error), all polling intervals are cleared and in-flight requests are aborted via AbortController. No orphaned network requests persist.

**Validates: Requirements 5.6**

### Property 5: State Consistency

The `step` field in the store is always consistent with the presence/absence of related state:
- `step === 'idle'` → `selectedFile === null`, `documentId === null`, `result === null`, `error === null`
- `step === 'file-selected'` → `selectedFile !== null`
- `step === 'uploading'` → `selectedFile !== null`, `uploadProgress >= 0`
- `step === 'processing'` → `documentId !== null`
- `step === 'ready'` → `result !== null`, `result.chunkCount > 0`
- `step === 'error'` → `error !== null`

**Validates: Requirements 4.3, 5.3, 5.7, 6.4**

### Property 6: No Technical Exposure

During any error state, no HTTP status codes, stack traces, internal error codes, or raw JSON are displayed to the user. Only user-facing messages (from i18n keys or backend `message` fields) are rendered.

**Validates: Requirements 6.1, 6.2**

### Property 7: Reset Completeness

When `reset()` is called (start over), all state returns to initial values: `step = 'idle'`, `selectedFile = null`, `documentId = null`, `result = null`, `error = null`, `uploadProgress = 0`. No stale state from a previous attempt leaks into the next workflow.

**Validates: Requirements 6.4**

### Property 8: String Externalization

No user-visible string literal appears directly in JSX component markup. All rendered text originates from either i18n translation keys or backend API response fields.

**Validates: Requirements 7.1**

---

## Interaction Flow

```
1. User lands on UploadPage (step: idle)
       │
2. User selects/drops file
       │── validation fails? → show error (step: error) → [select new file] → back to 1
       │
       ▼
3. File accepted (step: file-selected)
       │
4. User clicks "Upload and Analyze"
       │
       ▼
5. Consent dialog opens (step: consent-pending)
       │
       ├── [decline/dismiss] → back to step 3 (file-selected)
       │
       └── [accept]
              │
              ▼
6. Upload begins (step: uploading)
       │── progress indicator shown
       │── upload control disabled
       │
       ├── [network error] → error state (canRetry: true)
       ├── [400 error] → error state (display backend message)
       │
       └── [202 received]
              │
              ▼
7. Polling begins (step: processing)
       │── "Extracting text content..." shown
       │── polls GET /status every 2s
       │
       ├── [status: processing] → continue polling
       ├── [status: failed] → error state (display error_message)
       ├── [status: ready, chunks=0] → error state (no content)
       ├── [3 consecutive network failures] → connectivity error
       │
       └── [status: ready, chunks>0]
              │
              ▼
8. Success state (step: ready)
       │── shows filename, language, chunk count
       │── shows warnings if any
       │── [future: "Proceed to Analysis" button for Feature 3]
```

---

## Error Handling

| Error Source | Error Type | UI Behavior | Recovery |
|-------------|-----------|-------------|----------|
| Client validation | `validation` | Inline error below upload zone | Select new file |
| Upload network failure | `network` | Error card with message | Retry button |
| Backend 400 (validation) | `validation` | Display backend `message` field | Start over |
| Backend 422 (extraction) | `processing` | Display backend `message` field | Start over |
| Backend 5xx | `server` | Generic "Processing failed" | Retry or start over |
| Polling network failure (3x) | `connectivity` | "Unable to reach server" | Start over |
| Status: failed | `processing` | Display `error_message` from status | Start over |
| Status: ready, chunks=0 | `processing` | "No extractable content found" | Start over |

All errors reset to `idle` when "Start over" is clicked. The `retry` action re-attempts the last failed operation (upload or initial connection).

---

## Responsive Design

| Breakpoint | Layout Behavior |
|-----------|----------------|
| ≥ 1024px (desktop) | Centered content card, max-width 640px |
| 768px–1023px (tablet) | Centered content card, max-width 560px |
| < 768px (mobile) | Full-width content with horizontal padding |

The upload zone scales proportionally. The consent dialog uses the shadcn/ui `Dialog` component which is responsive by default (full-screen sheet on mobile via Radix).

---

## Security Considerations

- **No secrets in frontend:** The API base URL is the only environment variable. No API keys or credentials are stored in the frontend.
- **File validation:** Client-side validation is a UX convenience only. The backend enforces all constraints authoritatively.
- **CORS:** Configured server-side to allow only the known frontend origin in production.
- **No user data collected:** The frontend does not track, store, or transmit any user identity or usage data.
- **Consent before transmission:** No file data leaves the browser until the user explicitly accepts the consent dialog.

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| Components | UI rendering and interactions | Vitest + React Testing Library; test upload zone interactions, consent dialog behavior, error display |
| Store | State transitions | Vitest; test each action produces correct state, edge cases (double-click, rapid file changes) |
| API Client | Request construction and response parsing | Vitest with mocked fetch; verify correct URLs, headers, timeout handling, error classification |
| Validation | File validation logic | Vitest; boundary cases (exact limits, extensions, empty files) |
| Integration | Full upload flow | Vitest with MSW (Mock Service Worker); simulate complete upload → poll → ready flow |

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| react + react-dom | UI framework | Project standard (D-03) |
| typescript | Type safety | Project standard (D-03) |
| vite | Build tool | Project standard (D-03) |
| tailwindcss + postcss + autoprefixer | Utility CSS | Project standard (D-03) |
| @radix-ui/* (via shadcn/ui) | Accessible primitives | Project standard (D-03); Dialog, Progress, Alert components |
| zustand | State management | Project standard (D-03) |
| class-variance-authority + clsx + tailwind-merge | shadcn/ui utilities | Required by shadcn/ui components |
| vitest + @testing-library/react + jsdom | Testing | Project standard (D-03) |
| msw | API mocking for tests | Standard testing utility for frontend API integration tests |

No additional dependencies beyond the project's established stack are introduced.

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Application Shell | `AppShell`, `Header`, Vite project setup, responsive Tailwind layout |
| Req 2: Privacy Consent | `ConsentDialog`, store `consent-pending` state, dismiss-as-decline behavior |
| Req 3: File Selection & Validation | `UploadZone`, `FileInfo`, `lib/validation.ts`, client-side checks |
| Req 4: Upload Progress | `UploadProgress`, store `uploading` state, XHR progress events, disabled controls |
| Req 5: Status Monitoring | `ProcessingStatus`, polling logic in store, AbortController cleanup, chunk_count=0 handling |
| Req 6: Error Handling | `ErrorDisplay`, `UploadError` type, error classification, retry/start-over actions |
| Req 7: Internationalization | `i18n/` directory, `useTranslation` hook, JSON translation files, no hardcoded strings |
| Req 8: Backend Integration | `api/client.ts`, `api/documents.ts`, env-based URL, 30s timeout, CORS config |
