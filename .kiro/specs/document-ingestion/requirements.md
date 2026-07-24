# Requirements — Document Ingestion

## Overview

This feature implements the document ingestion layer: the entry point where users upload a document and the system validates, parses, and transforms it into a structured intermediate representation that the analysis engine can consume. The ingestion layer is architecturally decoupled from the analysis pipeline (ADR-003).

## Relevant Documentation

- #[[file:docs/product/04-product-mvp-specification.md]]
- #[[file:docs/decisions/ADR-003-document-ingestion.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]

---

## Requirement 1: Document Upload API

### User Story
As a user, I want to upload a document so that the system can analyze its content.

### Acceptance Criteria
1. Given a valid Markdown (.md) file under 1 MB, when the user uploads it, then the system accepts the file and returns a document identifier.
2. Given a valid text (.txt) file under 1 MB, when the user uploads it, then the system accepts the file and returns a document identifier.
3. Given a valid PDF (.pdf) file under 10 MB, when the user uploads it, then the system accepts the file and returns a document identifier.
4. Given a file with an unsupported extension (e.g., .docx, .xlsx), when the user uploads it, then the system rejects it with a clear error message indicating supported formats.
5. Given a Markdown or text file exceeding 1 MB, when the user uploads it, then the system rejects it with an error indicating the size limit.
6. Given a PDF file exceeding 10 MB, when the user uploads it, then the system rejects it with an error indicating the size limit.
7. Given a Markdown or text file with non-UTF-8 encoding, when the user uploads it, then the system rejects it with an error indicating encoding requirements.

---

## Requirement 2: Text Extraction and Normalization

### User Story
As a system, I need to extract and normalize text from uploaded documents so that the analysis engine receives a consistent intermediate representation regardless of the source format.

### Acceptance Criteria
1. Given an uploaded Markdown file, when the system processes it, then it extracts the full text preserving heading structure as section boundaries.
2. Given an uploaded text file, when the system processes it, then it extracts the full text content as a single section (or split by detectable headings if present).
3. Given an uploaded PDF file with extractable text, when the system processes it, then it extracts the text content preserving page boundaries.
4. Given a PDF with embedded images, when the system processes it, then images are ignored and only text content is extracted.
5. Given a PDF with simple tables, when the system processes it, then the table content is extracted as plain text.
6. Given a PDF with complex tables (multi-level headers, merged cells), when the system processes it, then those tables are skipped with an annotation in the intermediate representation.
7. Given a scanned PDF (image-only without selectable text), when the system processes it, then the system rejects it with a clear error indicating that scanned PDFs are not supported.

---

## Requirement 3: Intermediate Representation Generation

### User Story
As the analysis engine, I need a structured intermediate representation of any ingested document so that I can operate on it without knowledge of the original file format.

### Acceptance Criteria
1. Given a successfully extracted document, when the intermediate representation is generated, then it contains a unique document_id.
2. Given a successfully extracted document, when the intermediate representation is generated, then it contains document-level metadata (original filename, format, size, language detected, upload timestamp).
3. Given a successfully extracted document, when the intermediate representation is generated, then it contains an ordered list of content chunks, each with a chunk_id, text content, and structural context (page number for PDF, section heading for Markdown).
4. Given a Markdown document with headings, when the intermediate representation is generated, then each section corresponds to a chunk with its heading as structural context.
5. Given a PDF document, when the intermediate representation is generated, then each page corresponds to one or more chunks with the page number as structural context.
6. Given the intermediate representation, when the analysis engine accesses it, then it has no dependency on the original file format or parsing libraries.

---

## Requirement 4: Language Detection

### User Story
As a user, I want the system to detect the language of my document so that the analysis can be performed in the appropriate language (Spanish or English).

### Acceptance Criteria
1. Given a document written in Spanish, when the system processes it, then it identifies the language as Spanish in the intermediate representation metadata.
2. Given a document written in English, when the system processes it, then it identifies the language as English in the intermediate representation metadata.
3. Given a document in an unsupported language, when the system processes it, then it proceeds with a warning but does not block ingestion (best-effort analysis).

---

## Requirement 5: Temporary Storage and Privacy Controls

### User Story
As a user, I want my document content to be handled securely and not retained beyond what is necessary for the analysis session.

### Acceptance Criteria
1. Given an uploaded document, when the system stores it for processing, then the original file content is stored only temporarily (in Supabase Storage or server filesystem) for the duration of the analysis session.
2. Given a completed or expired session, when the retention period ends, then the original document content is deleted.
3. Given an uploaded document, when the intermediate representation is generated, then only the extracted text (not the original binary) is passed to downstream services.
4. Given the system design, when reviewing data flow, then no user metadata, account information, or usage history is attached to the stored document.

---

## Requirement 6: Upload Feedback and Status

### User Story
As a user, I want to see the progress of my document upload and processing so that I know when the system is ready for analysis.

### Acceptance Criteria
1. Given a document being uploaded, when the upload starts, then the user sees a progress indicator.
2. Given a document being processed (text extraction), when the extraction is in progress, then the user sees a status indicating processing.
3. Given a successfully processed document, when the intermediate representation is ready, then the user is notified that the document is ready for analysis.
4. Given a document that fails validation or extraction, when the error occurs, then the user receives a specific, actionable error message explaining what went wrong and how to fix it.

---

## Requirement 7: Format-Independent Processing

### User Story
As a user, I want the system to produce the same quality of analysis regardless of whether I upload a Markdown, text, or PDF file covering the same content, so that the document format does not affect the results I receive.

### Acceptance Criteria
1. Given the same content saved as Markdown and as a text file, when both are uploaded and processed, then the resulting intermediate representations contain equivalent textual content and structural context.
2. Given a new document format is added to the system in the future, when a user uploads a file in that format, then existing formats continue to work without degradation.
3. Given a successfully ingested document, when the analysis engine processes it, then the analysis engine has no knowledge of the original file format — it operates exclusively on the intermediate representation.
4. Given any supported format, when the system generates the intermediate representation, then the output structure (document_id, metadata, ordered chunks with chunk_id and structural context) is identical regardless of the source format.
