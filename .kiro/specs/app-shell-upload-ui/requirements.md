# Requirements Document

## Introduction

This feature establishes the frontend application shell and implements the document upload user interface. It provides the visual entry point where a user selects a document, gives consent for external AI processing, uploads the file, and monitors its progress through ingestion until it is ready for analysis.

The feature connects to the existing Document Ingestion backend (Feature 1) via the REST API already implemented (`POST /api/v1/documents/upload`, `GET /api/v1/documents/{id}/status`). It does not include the analysis engine, Knowledge Model visualization, or document type confirmation — those belong to subsequent features.

### Relevant Documentation

- #[[file:docs/product/04-product-mvp-specification.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-003-document-ingestion.md]]
- #[[file:docs/architecture/001-technology-stack.md]]
- #[[file:docs/architecture/003-vertical-development-strategy.md]]
- #[[file:.kiro/specs/document-ingestion/design.md]]

### Feature Boundaries

**In scope:**
- Frontend project scaffolding (React + TS + Vite + Tailwind + shadcn/ui + Zustand).
- Application shell layout (header, main content area).
- Document upload UI (file selection, drag-and-drop, client-side validation).
- Privacy consent dialog before upload.
- Upload progress feedback.
- Processing status monitoring (polling the existing status endpoint).
- Success and error states.
- Internationalization infrastructure (string externalization).
- HTTP client configuration and CORS setup.
- Environment-based API URL configuration.

**Out of scope (belongs to subsequent features):**
- Document type inference and confirmation UI (Feature 3 — Analysis Engine).
- Knowledge Model visualization (Feature 4).
- Quality analysis results display (Feature 5).
- Natural language query interface (Feature 6).
- Authentication or user accounts.
- Multiple document management or history.
- Offline support or service workers.
- Analytics or telemetry.

## Glossary

| Term | Definition |
|------|------------|
| Application Shell | The top-level UI layout (header, navigation, main content area) that hosts all feature views. |
| Consent Dialog | A modal dialog shown before upload that informs the user about external AI processing and requires explicit acceptance to proceed. |
| CORS | Cross-Origin Resource Sharing — a browser security mechanism that must be configured to allow the frontend (Vercel) to communicate with the backend (Render). |
| Cold Start | The delay (~30 seconds) when the backend server wakes up after being idle on Render's free tier. |
| Document Ingestion | The backend pipeline (Feature 1) that validates, extracts text, and produces an Intermediate Representation from uploaded documents. |
| Intermediate Representation (IR) | A format-agnostic structured representation of document content produced by the ingestion layer, consisting of ordered text chunks with metadata. |
| Knowledge Model | A structured representation of knowledge elements extracted from a document by the analysis engine (Feature 3 — not part of this feature). |
| Polling | The frontend technique of repeatedly calling the status endpoint at intervals to check processing progress until a terminal state is reached. |
| Supported Formats | Markdown (.md), plain text (.txt), and PDF (.pdf) — the file types accepted by the MVP per ADR-003. |
| i18n | Internationalization — the practice of externalizing user-facing strings so the application can support multiple languages without code changes. |

---

## Requirements

### Requirement 1: Application Shell and Navigation Structure

**User Story:** As a user, I want a clean and responsive application layout so that I can navigate the system and understand where I am at each step of the document analysis workflow.

#### Acceptance Criteria

1. When the application loads, then it displays a top-level layout with a header containing the application name and a main content area.
2. When the user accesses the application root URL, then they are presented with the document upload screen as the default landing view.
3. When the application is viewed on a screen narrower than 768px, then the layout adapts responsively without horizontal scrolling or content overflow.
4. When the frontend application is built, then it uses React, TypeScript, Vite, Tailwind CSS, and shadcn/ui as defined in the technology stack (D-03).
5. When the application starts, then it establishes a configured HTTP client capable of communicating with the backend API at a base URL defined by environment configuration.

**Traceability:**
- MVP Spec US-001 (user uploads a document — requires an interface to do so)
- Architecture 003: "Establece la infraestructura del frontend (React, Vite, Tailwind, shadcn/ui, Zustand) que todas las features posteriores necesitan."
- Tech Stack D-03: React + TypeScript + Vite, Tailwind CSS, shadcn/ui

---

### Requirement 2: Privacy Consent and Transparency

**User Story:** As a user, I want to be clearly informed that my document will be processed by an external AI service and give my explicit consent before any data is sent, so that I understand and control what happens with my document content.

#### Acceptance Criteria

1. Given the user has selected a file for upload, when the system is about to initiate the upload, then it displays a consent dialog informing the user that the document content will be processed by an external AI service.
2. Given the consent dialog is displayed, when the user reads it, then the dialog clearly states: (a) that the document text will be sent to an external AI provider for analysis, (b) that only the document text and system prompts are sent — no personal data or usage history, and (c) that the original document content is not retained beyond the analysis session.
3. Given the consent dialog is displayed, when the user explicitly accepts (clicks a confirmation button), then the system proceeds with the upload.
4. Given the consent dialog is displayed, when the user declines, dismisses, or closes the dialog by any means other than explicit acceptance (including clicking outside, pressing Escape, or clicking the close button), then the upload is cancelled and no data is sent to the backend.
5. Given the user has previously given consent during the current session, when they upload another document in the same session, then the consent dialog is shown again (consent is per-upload, not persisted across sessions).

**Traceability:**
- MVP Spec RF-11: "El sistema debe informar al usuario, antes de iniciar el análisis, que el contenido del documento será procesado por un servicio externo de IA."
- MVP Spec RF-12: "El usuario debe dar consentimiento explícito antes de que el sistema envíe el contenido del documento al servicio de IA."
- ADR-005: Transparency principle, Consent principle.
- PRD Flujo principal paso 2 and paso 3.

---

### Requirement 3: Document File Selection and Validation

**User Story:** As a user, I want to select a document from my device and receive immediate feedback if the file is not compatible, so that I do not waste time uploading files that will be rejected.

#### Acceptance Criteria

1. Given the upload screen is displayed, when the user interacts with the upload area, then they can select a file via a file picker dialog or by dragging and dropping a file onto the designated area.
2. Given the user selects a file, when the file has a supported extension (.md, .txt, .pdf), then the system accepts the selection and displays the filename, format, and size.
3. Given the user selects a file, when the file has an unsupported extension (e.g., .docx, .xlsx, .html), then the system immediately displays an error message listing the supported formats alongside the selected file's name and size, without initiating an upload.
4. Given the user selects a Markdown or text file, when the file exceeds 1 MB (strictly greater than 1,048,576 bytes), then the system immediately displays an error message indicating the size limit for that format alongside the file's name and detected size.
5. Given the user selects a PDF file, when the file exceeds 10 MB (strictly greater than 10,485,760 bytes), then the system immediately displays an error message indicating the size limit for PDF files alongside the file's name and detected size.
6. Given a validation error is displayed, when the user selects a new file, then the previous error is cleared and the new file is validated.
7. Given the upload area, when no file has been selected, then the area displays instructions indicating supported formats (.md, .txt, .pdf) and their respective size limits.

**Traceability:**
- MVP Spec RF-01: Supported formats and size restrictions.
- ADR-003: Formats (MD, TXT, PDF), sizes (1 MB text, 10 MB PDF).
- Document Ingestion Requirement 1 (server-side validation) — this requirement adds client-side pre-validation for immediate feedback.

---

### Requirement 4: Document Upload with Progress Feedback

**User Story:** As a user, I want to see the progress of my document upload so that I know the system is working and how long I need to wait.

#### Acceptance Criteria

1. Given a valid file is selected and consent is given, when the upload begins, then the UI displays a progress indicator showing that the file is being uploaded.
2. Given the file is being uploaded, when the upload is in progress, then the user cannot initiate another upload simultaneously (the upload control is disabled).
3. Given the upload completes successfully and the backend returns a 202 response with a document_id, when both conditions are confirmed, then the UI transitions to a processing state showing that text extraction is in progress.
4. Given the upload fails due to a network error, when the connection is interrupted, then the UI displays an actionable error message and offers the option to retry.
5. Given the upload fails due to a server-side validation error (400 response), when the backend returns a specific error (unsupported_format, file_too_large, invalid_encoding), then the UI displays the error message from the backend response directly to the user.

**Traceability:**
- Document Ingestion Requirement 6: "The user sees a progress indicator" and "the user receives a specific, actionable error message."
- Document Ingestion Design — API: POST /api/v1/documents/upload returns 202, error responses with specific error codes.
- Architecture 003: "el usuario puede subir un documento y ver su estado."

---

### Requirement 5: Document Processing Status Monitoring

**User Story:** As a user, I want to see the status of my document's processing after upload so that I know when it is ready for analysis or if something went wrong.

#### Acceptance Criteria

1. Given a document has been uploaded successfully (202 received), when the UI enters the processing state, then it polls `GET /api/v1/documents/{document_id}/status` at a regular interval (e.g., every 2 seconds) to check processing progress.
2. Given the backend returns status `processing`, when the UI receives the response, then it continues displaying a processing indicator with a message that text extraction is underway.
3. Given the backend returns status `ready` with a chunk_count greater than zero, when the UI receives the response, then it stops polling and displays a success state indicating the document is ready for analysis, showing the filename, detected language, and chunk count.
4. Given the backend returns status `failed` with an error_message, when the UI receives the response, then it stops polling and displays the error message with guidance on what the user can do (e.g., re-export the PDF, check encoding).
5. Given the status response includes warnings (e.g., "Complex table skipped on page 3"), when the document reaches status `ready`, then the warnings are displayed to the user as non-blocking informational messages.
6. Given polling is active, when the component unmounts or the user navigates away, then polling stops and no orphaned requests are made.
7. Given the backend returns status `ready` with a chunk_count of zero, when the UI receives the response, then it stops polling and displays an error state indicating that no extractable content was found in the document.

**Traceability:**
- Document Ingestion Requirement 6, AC 2-4: Status feedback during processing.
- Document Ingestion Design — API: GET /api/v1/documents/{document_id}/status returns status, warnings, error_message.
- Architecture 003: "Indicador de progreso, pantalla de estado."

---

### Requirement 6: Error Handling and Recovery

**User Story:** As a user, I want clear and helpful error messages when something goes wrong so that I can understand the problem and take corrective action without needing technical knowledge.

#### Acceptance Criteria

1. Given any error occurs during upload or processing, when the error is displayed, then the message is written in user-friendly language (no technical jargon, stack traces, or internal codes exposed).
2. Given a server-side error (5xx response or timeout), when the error is displayed, then the UI shows a generic message (e.g., 'Processing failed, please try again') with at least one recovery action (retry or start-over), and no technical details (status codes, stack traces, internal identifiers) are exposed anywhere in the UI.
3. Given a validation or extraction error from the backend, when the error response contains a `message` field, then the UI displays that message directly (backend messages are user-facing by design per Document Ingestion Design).
4. Given an error state is displayed, when the user chooses to start over, then the UI resets to the initial upload screen with no residual state from the failed attempt.
5. Given the backend is unreachable (network failure during polling), when multiple consecutive poll requests fail, then the UI displays a connectivity error after 3 failed attempts and stops polling.

**Traceability:**
- Document Ingestion Requirement 6, AC 4: "The user receives a specific, actionable error message explaining what went wrong and how to fix it."
- Document Ingestion Design — Error Handling: "Error messages from the API are user-facing and actionable. The frontend displays them directly without transformation."

---

### Requirement 7: Internationalization Readiness

**User Story:** As a developer, I need all user-facing strings to be externalized from the source code so that the application can support multiple languages in the future without code changes.

#### Acceptance Criteria

1. Given any user-facing text in the frontend (labels, messages, button text, error messages), when examining the source code, then no user-visible string is hardcoded directly in component markup — all strings are referenced through a localization mechanism (e.g., a translation file or i18n library).
2. Given the localization resources, when a new language needs to be supported, then adding a new translation file is sufficient to support it without modifying component logic.
3. Given error messages returned by the backend API, when displayed to the user, then they are passed through as-is (the backend owns the content of its messages; frontend i18n applies only to frontend-owned strings).

**Traceability:**
- Steering `coding.md`: "User-facing text must not be hardcoded. UI strings should be externalized to support future internationalization (i18n)."
- Steering `coding.md`: "The application UI must be designed to support multiple languages."

---

### Requirement 8: Backend Integration and CORS

**User Story:** As a user, I want the frontend to communicate reliably with the backend API so that my uploads are processed without cross-origin or connectivity issues.

#### Acceptance Criteria

1. Given the frontend is served from a different origin than the backend (e.g., Vercel vs Render), when the frontend makes API requests, then CORS is configured on the backend to accept requests from the frontend's origin.
2. Given the frontend environment, when the application is built for deployment, then the backend API base URL is configurable via an environment variable (not hardcoded).
3. Given the frontend makes an API call, when the request includes a file upload (multipart/form-data), then the HTTP client correctly sends the file with the appropriate Content-Type header.
4. Given any initial connection delay occurs (whether due to backend cold start, network latency, or other causes), when the user initiates their first request, then the UI handles the delay gracefully with an extended timeout (at least 30 seconds) or an informational message indicating the system is starting up, without showing an immediate error.

**Traceability:**
- Architecture 001 D-07: Render free tier "Sleep después de 15 min de inactividad (se despierta en ~30s al recibir request)."
- Architecture 003: "Integración: cliente HTTP configurado, CORS verificado, deploy funcional."
- Tech Stack: Deploy frontend on Vercel, backend on Render. 15 min de inactividad (se despierta en ~30s al recibir request)."
- Architecture 003: "Integración: cliente HTTP configurado, CORS verificado, deploy funcional."
- Tech Stack: Deploy frontend on Vercel, backend on Render.
