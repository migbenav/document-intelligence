# Implementation Plan: Application Shell & Document Upload UI

## Overview

This plan implements the frontend application shell and document upload UI. Tasks are ordered by dependency: project scaffolding first, then foundational layers (API client, store, i18n), then UI components, and finally integration verification. Each task produces a working increment that can be visually verified.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": [1],
      "description": "Frontend project scaffolding (Vite + React + TypeScript + Tailwind + shadcn/ui)"
    },
    {
      "wave": 2,
      "tasks": [2, 3, 4],
      "description": "Foundation layers: API client, i18n infrastructure, Zustand store"
    },
    {
      "wave": 3,
      "tasks": [5, 6],
      "description": "Application shell layout and file validation logic"
    },
    {
      "wave": 4,
      "tasks": [7, 8],
      "description": "Upload zone component and consent dialog"
    },
    {
      "wave": 5,
      "tasks": [9, 10],
      "description": "Upload progress and processing status components"
    },
    {
      "wave": 6,
      "tasks": [11],
      "description": "Error display and recovery flows"
    },
    {
      "wave": 7,
      "tasks": [12],
      "description": "Upload page orchestration and full flow integration"
    },
    {
      "wave": 8,
      "tasks": [13],
      "description": "Backend CORS configuration and end-to-end verification"
    }
  ]
}
```

## Tasks

- [x] 1. Frontend project scaffolding
  Initialize the Vite + React + TypeScript project in `src/frontend/`. Install and configure: Tailwind CSS (with `tailwind.config.ts`, `postcss.config.js`), shadcn/ui (init with default style, install Button, Dialog, Progress, Alert, Card components into `src/components/ui/`), Zustand, and Vitest + React Testing Library + jsdom. Create `vite.config.ts` with path aliases. Create `.env.example` with `VITE_API_BASE_URL=http://localhost:8000`. Create `src/main.tsx` entry point and `src/App.tsx` root component. Verify the app renders with `npm run dev`.
  **Requirements: 1.4**

- [x] 2. API client layer
  Create `src/frontend/src/api/client.ts` with configuration constants (`API_BASE_URL` from env, `UPLOAD_TIMEOUT_MS = 30000`, `POLL_INTERVAL_MS = 2000`, `MAX_POLL_FAILURES = 3`). Create `src/frontend/src/api/documents.ts` with two async functions: `uploadDocument(file: File)` using XMLHttpRequest for progress tracking (returns `UploadResponse` or throws typed error), and `getDocumentStatus(documentId: string)` using fetch with AbortController support. Create `src/frontend/src/types/api.ts` with TypeScript interfaces: `UploadResponse`, `StatusResponse`, `ApiErrorResponse`. Include a slow-connection detection mechanism that triggers a "starting up" indicator after 3 seconds of waiting. Write tests in `tests/api/documents.test.ts` with mocked fetch.
  **Requirements: 8.2, 8.3, 8.4**

- [x] 3. Internationalization infrastructure
  Create `src/frontend/src/i18n/index.ts` with a `TranslationProvider` React context and `useTranslation()` hook that performs nested key lookup with interpolation support (e.g., `{limit}` placeholders). Create `src/frontend/src/i18n/en.json` with all English strings (app, upload, consent, status, errors, actions sections as defined in design). Create `src/frontend/src/i18n/es.json` with Spanish translations. Wrap `<App>` in `<TranslationProvider>`. Write unit tests verifying key lookup, missing key fallback, and interpolation.
  **Requirements: 7.1, 7.2, 7.3**

- [x] 4. Zustand upload store
  Create `src/frontend/src/store/uploadStore.ts` implementing the `UploadStore` interface from design: state fields (`step`, `selectedFile`, `uploadProgress`, `result`, `error`, `documentId`) and actions (`selectFile`, `openConsent`, `acceptConsent`, `declineConsent`, `startUpload`, `startPolling`, `stopPolling`, `reset`). Implement state transition logic: idle → file-selected → consent-pending → uploading → processing → ready/error. Ensure `reset()` clears all state completely. Ensure `stopPolling()` clears interval and aborts in-flight request. Write comprehensive unit tests in `tests/store/uploadStore.test.ts` covering all transitions, edge cases (double-click, rapid file changes), and correctness properties (consent gate, reset completeness).
  **Requirements: 4.2, 5.6, 6.4**

- [x] 5. Application shell layout
  Create `src/frontend/src/components/layout/AppShell.tsx` (flex column, min-h-screen, header + main content area) and `src/frontend/src/components/layout/Header.tsx` (app name from i18n, responsive padding). Apply responsive breakpoints: centered max-w-2xl on desktop/tablet, full-width with padding on mobile (<768px). Export the shell as the default layout wrapping page content in `App.tsx`. Write component tests verifying responsive behavior and header content.
  **Requirements: 1.1, 1.2, 1.3**

- [x] 6. Client-side file validation
  Create `src/frontend/src/lib/validation.ts` with `validateFile(file: File): ValidationResult` function. Check file extension against `SUPPORTED_EXTENSIONS` (.md, .txt, .pdf). Check size against format-specific limits (>1,048,576 bytes for md/txt, >10,485,760 for pdf — boundary is inclusive/accepted). Return `{ valid: true, format }` or `{ valid: false, errorKey, metadata: { filename, size, limit } }`. Create `src/frontend/src/lib/utils.ts` with `cn()` helper (clsx + tailwind-merge) and `formatBytes(bytes)` utility. Write unit tests in `tests/lib/validation.test.ts` covering all boundary cases: exact limit accepted, one byte over rejected, each extension, unknown extensions.
  **Requirements: 3.3, 3.4, 3.5**

- [x] 7. Upload zone component
  Create `src/frontend/src/components/upload/UploadZone.tsx`: a styled drop area (using Card from shadcn/ui) with drag-and-drop support (`onDragOver`, `onDragLeave`, `onDrop` handlers) and a hidden file input triggered by click. On file selection, call `validateFile()` then store's `selectFile()`. Show visual feedback on drag-over (border highlight). When idle, display format instructions and size limits from i18n. Create `src/frontend/src/components/upload/FileInfo.tsx`: displays selected file name, format badge, and formatted size. Write component tests for drag-drop interaction, file picker, and validation error display.
  **Requirements: 3.1, 3.2, 3.6, 3.7**

- [x] 8. Consent dialog component
  Create `src/frontend/src/components/upload/ConsentDialog.tsx` using shadcn/ui Dialog. Content includes: title, three bullet points about data handling (from i18n consent keys), accept button (primary) and cancel button (secondary). Dialog is controlled by store step `consent-pending`. On accept: call store's `acceptConsent()`. On any dismissal (cancel click, X button, overlay click, Escape key): call store's `declineConsent()`. Ensure `onOpenChange(false)` maps to decline. Write tests verifying: accept triggers upload flow, all dismiss methods cancel, dialog content matches i18n keys.
  **Requirements: 2.1, 2.2, 2.3, 2.4, 2.5**

- [x] 9. Upload progress component
  Create `src/frontend/src/components/upload/UploadProgress.tsx`: displays a Progress bar (shadcn/ui) with percentage during upload, and a spinner/indeterminate state with "Uploading..." text from i18n. Visible when store step is `uploading`. If the upload takes longer than 3 seconds, show an additional informational message ("Starting up, this may take a moment..."). Write component tests for progress display and slow-connection message appearance.
  **Requirements: 4.1, 4.3, 8.4**

- [x] 10. Processing status component
  Create `src/frontend/src/components/upload/ProcessingStatus.tsx`: shows a spinner with "Extracting text content..." text during polling (step=processing). On success (step=ready): displays a success card with filename, detected language, and chunk count. On warnings: renders them as non-blocking Alert components (info variant). Integrates with store's polling lifecycle — calls `startPolling()` on mount when step is processing, `stopPolling()` on unmount via useEffect cleanup. Write tests verifying: polling starts/stops correctly, success state renders metadata, warnings render.
  **Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7**

- [x] 11. Error display component
  Create `src/frontend/src/components/upload/ErrorDisplay.tsx`: renders an Alert (destructive variant) with the error message from store. Shows a "Try again" button if `error.canRetry === true`, and always shows a "Start over" button. "Start over" calls `store.reset()`. "Try again" re-invokes the last failed operation. Ensures no technical details are exposed — only the `error.message` string (which comes from i18n or backend message field). Write tests for both recovery actions, message display, and absence of technical content.
  **Requirements: 6.1, 6.2, 6.3, 6.4, 6.5**

- [x] 12. Upload page orchestration
  Create `src/frontend/src/components/upload/UploadPage.tsx` that orchestrates all upload components based on the current store step: renders UploadZone when idle/file-selected/error-with-validation, ConsentDialog when consent-pending, UploadProgress when uploading, ProcessingStatus when processing/ready, ErrorDisplay when error. Connect the "Upload and Analyze" button (visible in file-selected step) to `store.openConsent()`. Ensure the page renders the correct component for each step and transitions are smooth. Update `App.tsx` to render UploadPage inside AppShell. Write integration tests using MSW to mock the backend: complete flow from file selection → consent → upload → poll → ready.
  **Requirements: 1.2, 4.1, 4.2**

- [x] 13. Backend CORS update and end-to-end verification
  Update `src/backend/app/main.py` (or create a production entrypoint) to read `CORS_ORIGINS` from environment variable and pass it to `create_app()`. Add `CORS_ORIGINS` to `.env.example` documentation. Verify end-to-end: start backend locally (`uvicorn`), start frontend (`npm run dev`), upload a test document through the UI, confirm the full flow works (file selection → consent → upload → processing → ready). Document any issues found and fix them. Verify responsive layout on narrow viewport.
  **Requirements: 8.1, 8.2**

## Notes

- All tasks include component/unit tests alongside implementation.
- Task 1 must complete before any other task can start (project doesn't exist yet).
- Tasks 2, 3, 4 can be parallelized after Task 1 since they have no interdependencies.
- Tasks 7 and 8 depend on the store (Task 4) and validation (Task 6) being complete.
- Task 12 is the integration point where all components come together — it depends on Tasks 7-11.
- Task 13 requires both frontend (Tasks 1-12) and backend to be running for manual verification.
- The shadcn/ui components in `src/components/ui/` are generated by the shadcn CLI during Task 1 scaffolding — they are not hand-written.
- MSW (Mock Service Worker) is installed during Task 12 for integration testing only.
