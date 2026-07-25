# Requirements Document

Document Quality Analysis

## Introduction

This feature implements the document quality analysis engine: a pipeline that consumes the completed Knowledge Model (produced by Feature 3) and evaluates the document's quality across three dimensions — internal inconsistencies (contradictions and ambiguities), missing information (relative to the document type schema), and improvement suggestions. This is the primary differentiator of the MVP (ADR-001): the system not only extracts knowledge but reasons about its quality and internal consistency.

The quality analysis operates on the Knowledge Model and the original IR, using LLM-based analysis augmented by structural checks (e.g., leveraging existing `contradicts` relationships). All findings include `source_ref` evidence linking back to the original document, maintaining the Trust by Evidence model (ADR-004).

## Relevant Documentation

- #[[file:docs/product/04-product-mvp-specification.md]]
- #[[file:docs/decisions/ADR-001-mvp-scope.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-006-document-type-schemas.md]]
- #[[file:docs/architecture/mvp-roadmap.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/requirements.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/design.md]]

## Feature Boundaries

**In scope:**
- Contradiction detection using Knowledge Model relationships (`contradicts`) and LLM-based deeper analysis.
- Ambiguity detection identifying vague, unclear, or ambiguous statements in the document.
- Completeness evaluation based on document type schema (PRD, Technical Spec, Policy/Process). Disabled for Generic type.
- Suggestion generation providing actionable improvement recommendations.
- Quality Analysis API endpoint to trigger and retrieve results.
- Quality analysis session management (state tracking, result persistence).
- Evidence traceability: all findings include `source_ref` linking to the original document.
- Pydantic models for findings (Inconsistency, MissingElement, Suggestion).
- Versioned prompts for each quality analysis type.
- Integration with the existing Knowledge Model as input.
- Reproducibility principles (controlled parameters, prompt versioning, metadata tracking).

**Out of scope (belongs to other features or future iterations):**
- Knowledge Model extraction (already completed in Feature 3).
- Knowledge Model visualization (Feature 4).
- Natural language queries (Feature 6).
- User feedback on findings (Feature 7).
- Quality analysis for multi-document relationships.
- Custom quality rules defined by the user.
- Automated fix/rewrite suggestions that modify the document.
- Frontend quality panel UI (this feature provides the API; frontend is a separate task).
- Confidence scores per finding (deferred per ADR-004).

## Glossary

| Term | Definition |
|------|------------|
| Quality_Analysis | The process of evaluating a document's quality based on its Knowledge Model, producing findings across three categories: inconsistencies, missing elements, and suggestions. |
| Inconsistency | A finding where the document contains internal contradictions or ambiguities — statements that conflict with each other or are unclear. |
| Contradiction | A type of inconsistency where two or more elements in the Knowledge Model assert conflicting information about the same subject. |
| Ambiguity | A type of inconsistency where a statement in the document is vague, unclear, or can be interpreted in multiple valid ways. |
| Missing_Element | A finding indicating that the document lacks an element expected by its document type schema (e.g., a PRD without defined acceptance criteria). |
| Suggestion | An actionable improvement recommendation derived from the findings or general document quality patterns. |
| Document_Type_Schema | The set of expected elements for a specific document type (PRD, Technical Spec, Policy/Process). Defines what "completeness" means for that type. |
| Quality_Analysis_Session | A record tracking the state and results of a quality analysis run, associated with an existing analysis session. |
| Finding | A generic term for any quality issue detected (inconsistency, missing element, or suggestion). |
| source_ref | A flexible evidence reference that traces a finding back to the original document (includes document_id, chunk_id, page, section, evidence text span). |
| Knowledge_Model | The structured representation of the document's knowledge (typed elements with relationships), produced by Feature 3 and consumed as input by this feature. |
| Quality_Analysis_Service | The backend service that orchestrates the quality analysis pipeline. |
| Severity | A classification of finding importance: high (critical issue), medium (notable issue), low (minor improvement opportunity). |

---

## Requirements

### Requirement 1: Contradiction Detection

**User Story:** As a user, I want the system to detect internal contradictions in my document so that I can identify statements that conflict with each other before they cause problems.

#### Acceptance Criteria

1. WHEN a completed Knowledge Model exists for a document, THE Quality_Analysis_Service SHALL identify contradictions by examining elements connected via `contradicts` relationships in the Knowledge Model and by performing LLM-based semantic analysis to detect additional contradictions not captured by explicit relationships.
2. WHEN a contradiction is detected, THE Quality_Analysis_Service SHALL produce an Inconsistency finding that includes: the two or more conflicting elements (by element ID), a description of the contradiction (maximum 500 characters), a severity level, and a source_ref for each involved element linking to the original document text. Severity SHALL be assigned as: high — elements assert mutually exclusive facts about the same subject (e.g., conflicting numeric values, incompatible states); medium — elements imply incompatible intent or constraints that could lead to misinterpretation; low — elements contain minor wording tensions that are unlikely to cause operational problems.
3. WHEN the Knowledge Model already contains explicit `contradicts` relationships between elements, THE Quality_Analysis_Service SHALL include these as confirmed contradictions without requiring additional LLM validation. Each confirmed contradiction SHALL still include a description explaining the conflict and a severity level assigned according to the severity criteria defined in criterion 2.
4. WHEN the LLM identifies a potential contradiction between elements that do not have an explicit `contradicts` relationship, THE Quality_Analysis_Service SHALL include the finding with a description explaining the nature of the conflict.
5. IF no contradictions are detected in the document, THEN THE Quality_Analysis_Service SHALL return an empty contradictions list rather than fabricating findings.
6. IF the LLM service is unavailable or returns an error during contradiction analysis, THEN THE Quality_Analysis_Service SHALL mark the quality analysis status as "failed" with a descriptive error message, preserve any contradictions already collected from explicit `contradicts` relationships as partial results regardless of when in the pipeline the failure occurs (if contradictions from explicit relationships exist, they are assumed to have been successfully collected), and not return incomplete LLM-based findings.

**Traceability:**
- ADR-001: "Detección de inconsistencias internas como diferenciador del MVP."
- ADR-002: Relationship type `contradicts` for detection.
- RF-05: System must detect internal inconsistencies (contradictions and ambiguities).
- CA-02: System identifies contradictions/ambiguities and presents them with traceable evidence.
- ADR-004: source_ref in findings for Trust by Evidence.

---

### Requirement 2: Ambiguity Detection

**User Story:** As a user, I want the system to identify ambiguous or vague statements in my document so that I can clarify them before they lead to misinterpretation.

#### Acceptance Criteria

1. WHEN a completed Knowledge Model and IR exist for a document, THE Quality_Analysis_Service SHALL analyze the document text to identify statements that can be interpreted in multiple valid ways, using the Knowledge Model elements and relations as context for detecting semantic ambiguity.
2. WHEN an ambiguity is detected, THE Quality_Analysis_Service SHALL produce an Inconsistency finding (subtype: ambiguity) that includes: the ambiguous element or text, a description explaining why the statement is ambiguous and listing at least 2 plausible interpretations, a severity level (high: blocks comprehension of a core element; medium: creates uncertainty in a secondary element; low: stylistic imprecision with minimal misinterpretation risk), and a source_ref linking to the specific location in the original document.
3. THE Quality_Analysis_Service SHALL detect, at minimum, the following ambiguity categories: undefined terms used without context, quantifiers without specific values (e.g., "quickly", "adequate", "many"), pronouns with unclear antecedents, and conditional statements with unspecified conditions. Additional ambiguity categories beyond these four MAY be detected.
4. IF no ambiguities are detected in the document, THEN THE Quality_Analysis_Service SHALL return an empty ambiguities list rather than fabricating findings.
5. IF the Quality_Analysis_Service fails to complete ambiguity analysis due to an LLM service error or timeout, THEN THE Quality_Analysis_Service SHALL report the failure with an error indication specifying the failure reason, without returning partial or fabricated ambiguity results.

**Traceability:**
- RF-05: System must detect internal inconsistencies (contradictions and ambiguities).
- CA-02: System identifies contradictions/ambiguities with traceable evidence.
- ADR-001: Inconsistency detection as MVP differentiator.

---

### Requirement 3: Completeness Evaluation

**User Story:** As a user, I want the system to identify information missing from my document based on its type so that I can complete it with the necessary elements.

#### Acceptance Criteria

1. WHEN the confirmed document type is PRD, Technical Spec, or Policy/Process, THE Quality_Analysis_Service SHALL compare the Knowledge Model elements against the expected elements defined in the document type schema and classify each expected element as: present (element exists with substantive content), partial (element exists but covers fewer than half of the sub-aspects implied by its schema definition), or missing (element is entirely absent from the Knowledge Model).
2. WHEN an element is classified as missing, THE Quality_Analysis_Service SHALL produce a Missing_Element finding that includes: the expected element name (from the schema), a description of what is expected, a severity level (high for elements that define the document's core purpose or scope, medium for elements that support understanding but are not structural, low for supplementary elements), and the document type schema that defines the expectation.
3. WHILE the confirmed document type is Generic, THE Quality_Analysis_Service SHALL skip completeness evaluation entirely and return an empty missing elements list — no "information missing" findings are reported for generic documents.
4. THE Quality_Analysis_Service SHALL use the following document type schemas for completeness evaluation:
   - PRD: propósito, usuarios/actores, requisitos funcionales, restricciones, criterios de éxito.
   - Technical Spec: propósito, alcance, componentes/conceptos, interfaces, restricciones, decisiones.
   - Policy/Process: propósito, alcance, actores/roles, reglas, procesos, excepciones.
5. WHEN an element is classified as partial, THE Quality_Analysis_Service SHALL produce a Partial_Coverage finding that includes: the expected element name, a description of what additional content is expected, a severity level (low or medium based on the same severity criteria defined in criterion 2), and the document type schema that defines the expectation.
6. IF the Knowledge Model contains zero extracted elements due to an extraction failure or an empty document, THEN THE Quality_Analysis_Service SHALL skip completeness evaluation and return an error indication stating that completeness cannot be assessed without a valid Knowledge Model.
7. WHILE the confirmed document type is Generic and an extraction failure prevents analysis of the document, THE Quality_Analysis_Service SHALL still report errors from the extraction failure rather than silently returning empty results — completeness evaluation is skipped, but error reporting for failures is permitted.

**Traceability:**
- ADR-006: Schemas per type for completeness evaluation; Generic without completeness evaluation.
- RF-06: System must identify missing information per document type schema.
- CA-03: System identifies missing information for typed documents.
- CA-03.1: No "information missing" reported for Generic type.
- US-005: User wants to know what information is missing.

---

### Requirement 4: Suggestion Generation

**User Story:** As a user, I want to receive actionable improvement suggestions so that I can enhance my document based on the analysis findings.

#### Acceptance Criteria

1. WHEN quality analysis is completed (contradictions, ambiguities, and completeness findings are available), THE Quality_Analysis_Service SHALL generate improvement suggestions based on the identified findings.
2. WHEN a suggestion is generated, THE Quality_Analysis_Service SHALL include: a clear description of the recommended improvement (maximum 300 characters), the category of the suggestion (structure, clarity, completeness, consistency), a priority level (high: addresses a high-severity finding; medium: addresses a medium-severity finding or structural gap; low: addresses a low-severity finding or stylistic improvement), and optionally a reference to the related finding(s) that motivated the suggestion.
3. THE Quality_Analysis_Service SHALL generate suggestions that are specific and actionable — each suggestion describes what to do, not just what is wrong. A suggestion SHALL contain a concrete recommended action (e.g., "Add a section defining the maximum response time for each endpoint") rather than a restatement of the problem (e.g., "Performance requirements are vague").
4. WHEN findings exist, THE Quality_Analysis_Service SHALL generate at least one suggestion per high-severity finding. General structural improvement suggestions MAY also be generated when quality patterns (e.g., organization, section ordering) can be improved, regardless of whether findings exist.
5. IF the document has zero findings and the LLM identifies no structural improvement opportunities, THEN THE Quality_Analysis_Service SHALL return an empty suggestions list rather than fabricating generic advice.
6. THE Quality_Analysis_Service SHALL generate a maximum of 20 suggestions per quality analysis run to maintain actionability and avoid overwhelming the user.

**Traceability:**
- RF-07: System must generate improvement suggestions based on Knowledge Model and quality analysis.
- US-006: User wants improvement suggestions.
- ADR-001: Suggestions as part of quality analysis capabilities.

---

### Requirement 5: Quality Analysis API

**User Story:** As a frontend client, I need an API endpoint to trigger quality analysis and retrieve the results so that I can build the quality analysis UI.

#### Acceptance Criteria

1. WHEN `GET /api/v1/documents/{document_id}/quality-analysis` is called and quality analysis is completed, THE API SHALL return 200 with the quality analysis results structured as: a list of inconsistencies (each with type [contradiction | ambiguity], description, severity [high | medium | low], affected element identifiers, and source_ref tracing to the original document), a list of missing elements (each with element type expected, description, and the document type schema used as reference), a list of suggestions (each with category, description, and related element identifiers), and analysis metadata as specified in criterion 7.
2. WHEN `GET /api/v1/documents/{document_id}/quality-analysis` is called and no quality analysis has been performed yet, THE API SHALL trigger the quality analysis pipeline and return 202 with a response body containing the document_id and a status field set to the initial analysis phase.
3. WHEN `GET /api/v1/documents/{document_id}/quality-analysis` is called and quality analysis is currently running, THE API SHALL return 202 with the current status as one of the defined phases: "analyzing_contradictions", "analyzing_ambiguities", "analyzing_completeness", or "generating_suggestions".
4. WHEN `GET /api/v1/documents/{document_id}/quality-analysis` is called and the associated Knowledge Model extraction has not reached "completed" status, THE API SHALL return 409 with an error body containing error code "km_not_completed" and a message indicating that quality analysis requires a completed Knowledge Model.
5. WHEN `GET /api/v1/documents/{document_id}/quality-analysis` is called and the document_id does not correspond to any existing document, THE API SHALL return 404 with an error body containing error code "not_found" and a message identifying the missing document.
6. IF the quality analysis pipeline fails during execution due to an LLM error or an internal processing error, THEN THE API SHALL set the analysis status to "failed", and subsequent GET requests SHALL return 500 with an error body containing error code "analysis_failed", a message indicating the failure category, and the phase at which the failure occurred.
7. WHEN quality analysis results are returned with status 200, THE API SHALL include metadata containing: the prompt version identifiers used for each analysis phase, the LLM model identifier, the analysis start and completion timestamps in ISO 8601 format, finding counts per category (contradictions, ambiguities, missing elements, suggestions), and the document type the analysis was evaluated against.
8. WHEN `GET /api/v1/documents/{document_id}/quality-analysis` is called and quality analysis has already completed, THE API SHALL return the previously computed results (idempotent retrieval) without re-triggering the analysis pipeline.

**Traceability:**
- MVP Roadmap Feature 5: "API: GET /{id}/quality-analysis."
- Document Ingestion & Analysis Engine API patterns (202 for async, 404/409 for state conflicts).
- ADR-004: source_ref and evidence traceability in all analysis outputs.
- ADR-006: Document type schemas for completeness evaluation; Generic type excludes completeness analysis.

---

### Requirement 6: Quality Analysis Session Management

**User Story:** As a system, I need to track the state of each quality analysis so that results are persisted and retrievable.

#### Acceptance Criteria

1. WHEN quality analysis is initiated for a document, THE Quality_Analysis_Service SHALL first verify that a completed Knowledge Model exists (analysis session status = "completed") before creating or updating the quality analysis record. IF the prerequisite is not met, THE Quality_Analysis_Service SHALL return an error without creating or updating the quality analysis record. IF the prerequisite is met, THE Quality_Analysis_Service SHALL create a quality analysis record associated with the document, with status "analyzing". IF a quality analysis record already exists for that document, THEN THE Quality_Analysis_Service SHALL reset its status to "analyzing" and clear previous results before proceeding.
2. WHEN the quality analysis status changes, THE Quality_Analysis_Service SHALL transition through the following states: analyzing → completed; or analyzing → failed. No other transitions are valid.
3. WHEN quality analysis completes successfully, THE Quality_Analysis_Service SHALL persist the results (inconsistencies, missing elements, suggestions) alongside the quality analysis record, with metadata consisting of: prompt version identifier, model version identifier, and analysis start and end timestamps.
4. IF quality analysis fails at any step, THEN THE Quality_Analysis_Service SHALL mark the quality analysis status as "failed" with an error message (maximum 1000 characters) indicating the step that failed and the nature of the failure. Any partial results persisted during processing SHALL be removed so that no incomplete quality analysis is retrievable.
5. THE Quality_Analysis_Service SHALL store quality analysis results as JSONB in the database, either as an extension of the existing analysis_sessions table or in a dedicated quality_analysis table.
6. WHEN quality analysis is re-triggered for a document that already has completed or failed results, THE Quality_Analysis_Service SHALL overwrite the previous results with the new analysis, maintaining a single quality analysis record per document.
7. IF the quality analysis remains in "analyzing" status for 120 seconds or more without progressing to "completed" or "failed", THEN THE Quality_Analysis_Service SHALL mark the record as "failed" with an error message indicating a timeout occurred.

**Traceability:**
- MVP Roadmap Feature 5: "Persistencia: resultados almacenados en analysis_sessions o tabla dedicada."
- Feature 3 pattern: analysis_sessions table, state machine, JSONB persistence.

---

### Requirement 7: Evidence Traceability

**User Story:** As a user, I want every quality finding to include evidence linking to the original document so that I can verify the finding and locate the relevant text.

#### Acceptance Criteria

1. THE Quality_Analysis_Service SHALL include at least one source_ref in every Inconsistency finding, pointing to the specific text in the original document where the contradiction or ambiguity occurs.
2. WHEN a contradiction involves multiple elements, THE Quality_Analysis_Service SHALL include one source_ref for each involved element (minimum 2) so the user can compare the conflicting statements.
3. THE source_ref in quality findings SHALL follow the same structure defined for Knowledge Model elements: document_id, chunk_id, page (when available), section (when available), and evidence text span limited to a maximum of 500 characters.
4. WHEN a Missing_Element finding is generated, THE Quality_Analysis_Service SHALL include the document type schema reference (which schema expects this element) but is not required to include a source_ref to the document text (since the element is absent by definition).
5. THE Quality_Analysis_Service SHALL verify that evidence text spans in source_refs exist in the original document using the same deterministic text-matching approach as the Knowledge Model verification (Feature 3, Requirement 7). Each source_ref SHALL include a boolean attribute `evidence_verified` set to true when matched and false when unverifiable. Findings with unverifiable evidence are retained in results with `evidence_verified = false`.
6. WHEN a Suggestion finding is generated, THE Quality_Analysis_Service SHALL include at least one source_ref pointing to the document context that triggered the suggestion (e.g., the section where improvement applies), following the same structure and verification rules as Inconsistency findings.
7. IF all source_refs in a finding have `evidence_verified = false`, THEN THE Quality_Analysis_Service SHALL retain the finding but mark it with a finding-level attribute `all_evidence_unverified = true` to indicate reduced traceability confidence.

**Traceability:**
- ADR-004: source_ref in findings for Trust by Evidence.
- CA-02: Inconsistencies presented "con evidencia trazable."
- RF-03.1: source_ref structure (document_id, page, section, chunk_id, evidence).
- RF-03.2: Verification of evidence against original document.

---

### Requirement 8: Integration with Knowledge Model

**User Story:** As a system, I need quality analysis to consume the completed Knowledge Model as its primary input so that findings are grounded in the structured knowledge already extracted.

#### Acceptance Criteria

1. WHEN quality analysis is initiated, THE Quality_Analysis_Service SHALL require a completed Knowledge Model (analysis session status = "completed") as a prerequisite. If the analysis session status is any value other than "completed", quality analysis SHALL NOT proceed and SHALL return an error indicating the prerequisite is not met.
2. THE Quality_Analysis_Service SHALL use the Knowledge Model elements (types, content, relationships) as the primary context for contradiction and ambiguity detection, supplemented by the original IR text chunks referenced by those elements' source_ref fields.
3. THE Quality_Analysis_Service SHALL use the confirmed document type from the analysis session to determine which completeness schema to apply. Completeness evaluation is only applied to explicitly supported document types (PRD, Technical Spec, Policy/Process) as defined in Requirement 3, criterion 4. If the confirmed type is "generic" or any other unsupported type, completeness evaluation is skipped entirely per Requirement 3.
4. WHEN the Knowledge Model contains elements marked as `verified = false`, THE Quality_Analysis_Service SHALL include those elements in the analysis. If such an unverified element is part of a finding, the finding SHALL include an attribute `involves_unverified_elements = true`.
5. THE Quality_Analysis_Service SHALL use the Knowledge Model's `contradicts` relationships as a starting point for contradiction detection, then extend analysis via LLM to find contradictions not captured by explicit relationships.
6. WHILE the confirmed document type is Generic, THE Quality_Analysis_Service SHALL still execute prerequisite checks, contradiction detection, and ambiguity detection — only completeness evaluation is skipped. All document types, including generic, receive full analysis for contradictions, ambiguities, and suggestions.

**Traceability:**
- MVP Roadmap Feature 5: Depends on Feature 3 (Knowledge Model + confirmed document type).
- ADR-002: Knowledge Model as the structured representation consumed by quality analysis.
- Design (Feature 3): quality_analysis as downstream consumer of Knowledge Model.

---

### Requirement 9: Reproducibility and Minimization

**User Story:** As a user, I want quality analysis to produce consistent results and I want to be confident that only the minimum necessary information is sent to the AI service.

#### Acceptance Criteria

1. WHEN quality analysis is run twice on the same Knowledge Model with the same model configuration and the same prompt version, THE Quality_Analysis_Service SHALL produce structurally consistent results — the same principal findings (equivalent inconsistencies, missing elements, and suggestions) are identified. Structural consistency means that at least 80% of findings from the first run are matched by equivalent findings in the second run, as determined by finding type and referenced Knowledge Model elements. Serialized output is not required to be byte-for-byte identical.
2. WHEN the Quality_Analysis_Service sends data to the LLM, THE Quality_Analysis_Service SHALL send only: Knowledge Model elements and relationships relevant to the analysis type being performed, the IR text chunks associated with those Knowledge Model elements, and the system prompt. No user identity, session history, account metadata, or information unrelated to the document content is included in the payload.
3. WHEN quality analysis completes, THE Quality_Analysis_Service SHALL record in metadata: the prompt version(s) used for each analysis type, the model identifier used, the generation parameters (temperature), and the analysis timestamp.
4. THE Quality_Analysis_Service SHALL use controlled generation parameters (temperature ≤ 0.1 by default) to maximize reproducibility of findings.
5. THE Quality_Analysis_Service SHALL use versioned prompt templates for each analysis type (contradiction detection, ambiguity detection, completeness evaluation, suggestion generation), following the same prompt versioning pattern established in Feature 3.
6. IF the generation temperature parameter is explicitly overridden to a value greater than 0.1, THEN THE Quality_Analysis_Service SHALL record the override value in the analysis metadata alongside the default value. This applies only when the temperature is intentionally overridden by configuration, not when the effective temperature happens to exceed 0.1 for other reasons.

**Traceability:**
- ADR-004: Bounded reproducibility — structural consistency.
- ADR-005: Minimization principle — only text + prompts sent.
- RF-13: Only minimum necessary information sent to AI.
- Feature 3 Requirement 10: Same reproducibility and minimization principles.

---

### Requirement 10: Quality Analysis Prompts

**User Story:** As a developer, I need dedicated prompt templates for each quality analysis type so that the analysis behavior is auditable, reproducible, and improvable.

#### Acceptance Criteria

1. THE Quality_Analysis_Service SHALL use separate versioned prompt templates for: contradiction detection, ambiguity detection, completeness evaluation, and suggestion generation.
2. WHEN a prompt template instructs the LLM, THE prompt SHALL require structured JSON output conforming to the corresponding Pydantic response models (one model per analysis type), such that the output can be validated by calling the model's constructor without raising a ValidationError.
3. IF the LLM returns output that fails Pydantic validation for the expected response model, THEN THE Quality_Analysis_Service SHALL treat the analysis step as failed and report a parsing error indicating which analysis type produced invalid output.
4. WHEN the completeness evaluation prompt is constructed for a document with confirmed type "prd", "technical_spec", or "policy_process", THE prompt SHALL include the document type schema (expected elements for that type as defined in ADR-006) so the LLM can compare the Knowledge Model against expectations. IF the document type schema cannot be included in the prompt due to a configuration error or missing schema definition, THEN THE Quality_Analysis_Service SHALL fail the completeness evaluation step entirely rather than proceeding without the schema.
5. IF the confirmed document type is "generic", THEN THE Quality_Analysis_Service SHALL skip the completeness evaluation step entirely, since no expected-elements schema exists for comparison.
6. WHEN a document's confirmed type changes from "generic" to a supported type (PRD, Technical Spec, or Policy/Process) through user correction, THE Quality_Analysis_Service SHALL make completeness evaluation available and run it for the updated type upon the next quality analysis execution.
7. WHEN any quality analysis prompt includes document content, THE prompt SHALL include only Knowledge Model elements, relationships, and the IR text chunks referenced by those elements' source_ref fields — no user metadata, account information, or usage history is included.
8. THE prompt templates SHALL be stored as Python modules in the prompts directory with explicit version constants, following the pattern established in Feature 3 (e.g., `contradiction_detection_v1.py`, `ambiguity_detection_v1.py`, `completeness_evaluation_v1.py`, `suggestion_generation_v1.py`).
9. WHEN a new prompt version is created, THE previous version files SHALL remain in the prompts directory unchanged, preserving their module and VERSION constant for comparison and rollback.

**Traceability:**
- Feature 3 Requirement 2: Prompt Template System pattern.
- ADR-004: Prompts versionados e inmutables por release.
- ADR-005: Only text + prompts sent; minimization principle.
- ADR-006: Document type schemas and Generic type behavior.
