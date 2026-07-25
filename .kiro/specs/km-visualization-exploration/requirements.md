# Requirements Document

Knowledge Model Visualization & Exploration

## Introduction

This feature implements the user-facing visualization and exploration layer for the Knowledge Model. It consumes the structured Knowledge Model produced by the Analysis Engine (Feature 3) and presents it as an interactive, navigable interface where users can explore typed elements, inspect relationships, view source evidence, and assess verification status.

This is a frontend-focused feature. The backend already exposes the Knowledge Model via `GET /api/v1/documents/{id}/knowledge-model` (implemented in Feature 3). This feature builds the React components, state management, and interaction patterns that make the Knowledge Model accessible and explorable by the user.

The visualization layer is the primary means by which the user evaluates the Trust by Evidence model (ADR-004): every element displays its source_ref, verification status is visually indicated, and the user can trace any claim back to the original document.

## Relevant Documentation

- #[[file:docs/product/04-product-mvp-specification.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/architecture/001-technology-stack.md]]
- #[[file:docs/architecture/mvp-roadmap.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/requirements.md]]
- #[[file:.kiro/specs/app-shell-upload-ui/requirements.md]]

## Feature Boundaries

**In scope:**
- Knowledge Model element list/grid view grouped by type (propósito, conceptos, actores, reglas, procesos, restricciones).
- Element detail panel displaying name, type, description/content, and evidence (source_ref).
- Source_ref evidence display with verified/non-verified visual indicator.
- Relationship visualization using React Flow (graph view) or structured list (fallback).
- Navigation between related elements (clicking a related element navigates to its detail).
- Integration with the existing application shell (Feature 2 layout, header, main content area).
- Loading, empty, and error states for Knowledge Model data.
- Responsive layout adapting to different screen widths.
- Zustand store for Knowledge Model state management.
- Accessibility: keyboard navigation, ARIA labels, screen reader support.

**Out of scope (belongs to subsequent features):**
- Quality analysis results display (inconsistencies, faltantes, sugerencias) — Feature 5.
- Natural language query interface — Feature 6.
- User feedback buttons on elements (mark as incorrect/irrelevant) — Feature 7.
- Document upload or ingestion — Feature 1/2.
- Analysis initiation or document type confirmation — Feature 3.
- Editing the Knowledge Model.
- Multi-document comparison or cross-document navigation.
- Confidence scores per element (not in MVP per ADR-004).

## Glossary

| Term | Definition |
|------|------------|
| Knowledge Model | A structured representation of the knowledge contained in a document, composed of typed elements with optional relationships — produced by the Analysis Engine (Feature 3). |
| Knowledge Element | A single unit of structured knowledge extracted from the document (e.g., a concept, actor, rule), with a unique id, type, name, description, and source_ref. |
| Taxonomy | The fixed set of element types: propósito, conceptos, actores, reglas, procesos, restricciones. |
| source_ref | A flexible evidence reference that traces a knowledge element back to the original document (includes document_id, page, section, chunk_id, evidence text span). |
| Evidence | The verbatim text span from the original document that supports a knowledge element, contained within source_ref. |
| Verification Status | A boolean flag (verified/not-verified) indicating whether the element's evidence text was confirmed to exist in the source document by the verification pipeline. |
| Relationship | A directed or bidirectional connection between two Knowledge Elements using the fixed vocabulary: constrains, participates_in, depends_on, contradicts. |
| Element Detail Panel | The UI component that displays full information about a selected Knowledge Element, including its content, evidence, verification status, and relationships. |
| Relationship Graph | An interactive graph visualization (React Flow) showing Knowledge Elements as nodes and their relationships as edges. |
| Application Shell | The top-level UI layout (header, navigation, main content area) established by Feature 2, which hosts this feature's views. |
| Zustand Store | The client-side state management store holding the fetched Knowledge Model, selected element, UI state (loading, error, filters). |

---

## Requirements

### Requirement 1: Knowledge Model Data Fetching and State Management

**User Story:** As a user, I want the Knowledge Model to be loaded automatically when I navigate to the visualization view so that I can immediately begin exploring the document's structured knowledge.

#### Acceptance Criteria

1. Given a document with a completed analysis (status = completed), when the user navigates to the Knowledge Model visualization view, then the system fetches the Knowledge Model from `GET /api/v1/documents/{document_id}/knowledge-model` and stores it in the Zustand store.
2. Given the Knowledge Model is being fetched, when the request is in progress, then the UI displays a loading state with a skeleton or spinner indicating that data is being loaded.
3. Given the fetch request completes successfully, when the Knowledge Model contains elements, then the UI transitions from loading to displaying the element list/grid view.
4. Given the fetch request completes successfully, when the Knowledge Model contains zero elements, then the UI displays an empty state message indicating that no knowledge elements were extracted from the document.
5. Given the fetch request fails (network error, server error, or timeout), when the error occurs, then the UI displays an error state with a user-friendly message and a retry action.
6. Given the Knowledge Model has been fetched and stored, when the user navigates away and returns to the visualization view, then the cached data is displayed without re-fetching unless the user explicitly requests a refresh.
7. Given the backend is unreachable due to cold start or network issues, when the fetch times out, then the UI handles the delay gracefully with an extended timeout (at least 30 seconds) consistent with the application shell's cold-start handling (Feature 2).

**Traceability:**
- MVP Roadmap Feature 4: "Backend: endpoint GET /{id}/knowledge-model ya existe desde Feature 3."
- MVP Spec RF-10: "El sistema mostrará el Knowledge Model de forma estructurada."
- App Shell Requirements (Feature 2, Req 8): Backend integration patterns, cold-start handling.
- Tech Stack: Zustand for state management.

---

### Requirement 2: Element List/Grid View Grouped by Type

**User Story:** As a user, I want to see all Knowledge Model elements organized by their type so that I can quickly scan the document's structure and find elements of interest.

#### Acceptance Criteria

1. Given the Knowledge Model has been loaded, when the visualization view renders, then it displays elements grouped by type using the fixed taxonomy order: propósito, conceptos, actores, reglas, procesos, restricciones.
2. Given a type group, when it contains elements, then the group displays a header with the type name and the count of elements in that group.
3. Given a type group, when it contains no elements, then the group is still displayed with its type name header visible and a count of zero, plus a subtle indication that no elements of that type were extracted.
4. Given each element in the list, when it is displayed, then it shows at minimum: the element name and a truncated preview of the description (first 120 characters or first sentence, whichever is shorter).
5. Given each element in the list, when it has a verification status, then a visual indicator (icon or badge) distinguishes verified elements from non-verified elements.
6. Given the element list, when the user clicks or activates an element, then the full details of that element are displayed (via the Detail Panel, overlay, or other appropriate UI pattern).
7. Given the element list, when the user presses keyboard arrow keys while focus is within the list, then focus moves between elements in a logical order (within-group first, then between groups).

**Traceability:**
- MVP Spec CA-05: "El usuario puede visualizar los elementos del Knowledge Model."
- MVP Spec RF-10: "El sistema mostrará el Knowledge Model de forma estructurada."
- ADR-002: Taxonomy of 6 element types.
- MVP Roadmap Feature 4: "lista/grid de elementos agrupados por tipo."
- PRD C3: Exploración del conocimiento.

---

### Requirement 3: Element Detail Panel

**User Story:** As a user, I want to see the full details of a Knowledge Element including its content and evidence so that I can understand what knowledge was extracted and verify its origin in the document.

#### Acceptance Criteria

1. Given the user selects an element from the list/grid, when the Element Detail Panel opens, then it displays: the element name, type (with a type label or badge), and full description/content.
2. Given the Element Detail Panel is displayed, when the selected element has a source_ref, then the panel displays the evidence section showing: the evidence text span (verbatim quote from the source document), and contextual metadata (section heading for Markdown, page number for PDF, chunk reference).
3. Given the Element Detail Panel is displayed, when the system fails to load or render the evidence section due to a technical error, then the evidence area displays an inline error message informing the user that evidence could not be loaded, rather than failing silently or hiding the section.
4. Given the Element Detail Panel is displayed, when the element is verified (verified = true), then a visual indicator clearly communicates that the evidence was confirmed to exist in the source document.
5. Given the Element Detail Panel is displayed, when the element is not verified (verified = false), then a visual warning indicator clearly communicates that the evidence could not be confirmed, with a brief explanation that the element's source reference was not found in the original document.
6. Given the Element Detail Panel is displayed, when the selected element has relationships to other elements, then the panel displays a "Related Elements" section listing each related element with its name, type, and the relationship type (constrains, participates_in, depends_on, contradicts).
7. Given the "Related Elements" section, when the user clicks on a related element entry, then the Detail Panel navigates to display that element's full details (the selected element changes).
8. Given the Element Detail Panel is open, when the user presses Escape or clicks a close/back control, then the panel closes or returns to the previous state without losing scroll position in the element list.

**Traceability:**
- MVP Spec RF-03.1: source_ref with document_id, page, section, chunk_id, evidence.
- MVP Spec RF-03.2: Non-verified elements marked as such.
- ADR-004: Trust by Evidence — source_ref visible to user for verification.
- MVP Roadmap Feature 4: "panel de detalle con contenido y evidencia."
- PRD C6: Trust by Evidence (source_ref visualization).

---

### Requirement 4: Evidence Display and Verification Status

**User Story:** As a user, I want to clearly see the evidence supporting each knowledge element and whether it has been verified so that I can trust the analysis results and identify elements that may need manual review.

#### Acceptance Criteria

1. Given the evidence section of the Detail Panel, when the evidence text span is displayed, then it is rendered in a visually distinct manner (e.g., blockquote styling, monospace, or highlighted background) to differentiate it from the element's description.
2. Given a verified element, when its verification status is displayed (in both the list view and detail panel), then a consistent icon or badge (e.g., a checkmark) indicates verified status with an accessible label for screen readers.
3. Given a non-verified element, when its verification status is displayed (in both the list view and detail panel), then a consistent warning icon or badge (e.g., a caution triangle) indicates non-verified status with an accessible label for screen readers.
4. Given the verification status indicator fails to render due to a technical error, when the element is displayed, then the element remains visible and functional without the status indicator, degrading gracefully rather than blocking access to the element content.
5. Given the element list/grid, when it is rendered, then the user can visually scan verification status across all elements without opening each one (the status indicator is visible at the list level).
6. Given a non-verified element, when the user views it in the detail panel, then a brief explanatory tooltip or inline text communicates that the evidence text was not found in the original document, indicating potential inaccuracy.
7. Given the Knowledge Model metadata includes a verification rate (percentage), when the visualization view loads, then it displays a summary indicating the overall verification rate of the Knowledge Model (e.g., "85% of elements verified").

**Traceability:**
- ADR-004: "Si una referencia no puede ser verificada, el elemento se marca como no-verificado."
- ADR-004: Verification rate as part of analysis session metadata.
- MVP Spec RF-03.2: Unverified elements marked.
- MVP Spec CA-06: "el sistema marca el elemento como no-verificado."
- PRD C6: Trust by Evidence — user can verify origin of each result.
- US-003: Visualizar los elementos del Knowledge Model.

---

### Requirement 5: Relationship Visualization

**User Story:** As a user, I want to see how Knowledge Elements are related to each other so that I can understand the connections and dependencies within my document's knowledge structure.

#### Acceptance Criteria

1. Given the Knowledge Model contains relationships between elements, when the user accesses the relationship view, then the system displays an interactive graph visualization (React Flow) showing elements as nodes and relationships as directed edges.
2. Given the graph visualization, when elements are rendered as nodes, then each node displays the element name and a visual indicator of its type (color, icon, or shape per type).
3. Given the graph visualization, when relationships are rendered as edges, then each edge displays or encodes the relationship type (constrains, participates_in, depends_on, contradicts) via labels, colors, or line styles.
4. Given a "contradicts" relationship, when it is rendered, then it is displayed as a bidirectional edge (both directions) with a visually distinct style (e.g., red or dashed) to highlight the conflict.
5. Given the graph visualization, when the user clicks on a node, then the Element Detail Panel opens or updates to show that element's details.
6. Given the graph visualization, when the user interacts with the canvas, then standard React Flow interactions are available: pan, zoom, and node dragging for layout adjustment.
7. Given the Knowledge Model contains no relationships, when the user navigates to the relationship view, then the system displays a message indicating that no relationships were identified in this document, with an explanation that relationships are optional.
8. Given the Knowledge Model contains a large number of elements (more than 20 nodes), when the graph renders, then nodes are positioned using an automatic layout algorithm that minimizes edge crossings and overlaps, providing a readable initial layout.

**Traceability:**
- ADR-002: Relationships optional, 4 fixed types with directionality.
- MVP Spec RF-04: Relationship vocabulary and semantic directions.
- MVP Roadmap Feature 4: "visualización de relaciones (React Flow o lista)."
- Tech Stack: React Flow for relationship visualization.
- PRD C3: Exploración del conocimiento.

---

### Requirement 6: Navigation Between Related Elements

**User Story:** As a user, I want to navigate from one element to its related elements so that I can follow the knowledge connections and explore the document's structure naturally.

#### Acceptance Criteria

1. Given the Element Detail Panel displays related elements, when the user clicks on a related element entry, then the detail panel updates to show the clicked element's full details, effectively navigating to it.
2. Given the graph visualization, when the user clicks on an edge connecting two nodes, then a tooltip or panel shows the relationship type and a brief description (if available), with links to both connected elements.
3. Given the user has navigated to a related element via the detail panel, when they want to go back, then a back button or breadcrumb trail allows returning to the previously viewed element.
4. Given the element list/grid view, when the user selects an element that has relationships, then the list highlights or indicates which other visible elements are related to the selected one.
5. Given any element reference displayed anywhere in the UI (detail panel, graph node, relationship list), when the user activates it (click or keyboard Enter), then navigation occurs to display that element's full details.

**Traceability:**
- MVP Roadmap Feature 4: "navegación entre elementos relacionados."
- MVP Spec RF-04: "Navegación y exploración: permitir al usuario seguir conexiones entre elementos."
- PRD C3: Exploración del conocimiento.
- ADR-002: Relationships enable navigation.

---

### Requirement 7: Responsive Layout and Application Shell Integration

**User Story:** As a user, I want the Knowledge Model visualization to work well within the application layout and adapt to different screen sizes so that I can explore knowledge on any device.

#### Acceptance Criteria

1. Given the Knowledge Model visualization view, when it renders within the application shell, then it occupies the main content area established by Feature 2's layout structure (header + main content area).
2. Given a screen width of 1024px or larger, when the visualization view is displayed, then the element list/grid and the detail panel are shown side by side (master-detail layout).
3. Given a screen width between 768px and 1023px, when the visualization view is displayed, then the layout automatically adapts by stacking the detail panel below the element list or using a sliding panel overlay.
4. Given a screen width below 768px, when the visualization view is displayed with no element selected, then the element list fills the screen width; and when the user selects an element, then the UI navigates to a full-screen detail view with a back button to return to the list.
5. Given the graph visualization (React Flow), when displayed on screens below 768px, then the graph remains functional with touch-friendly zoom and pan controls, and nodes are large enough to be tapped.
6. Given the visualization view, when navigation occurs (between list view, detail panel, and graph view), then the application shell's header and navigation remain stable (no layout shifts or re-renders of the shell).

**Traceability:**
- MVP Roadmap Feature 4: "Vista principal del Knowledge Model."
- App Shell Requirements (Feature 2, Req 1, AC 3): "the layout adapts responsively without horizontal scrolling."
- Tech Stack: Tailwind CSS for responsive design, shadcn/ui for components.

---

### Requirement 8: Accessibility

**User Story:** As a user relying on assistive technology, I want the Knowledge Model visualization to be navigable via keyboard and compatible with screen readers so that I can explore document knowledge regardless of my abilities.

#### Acceptance Criteria

1. Given the element list/grid, when the user navigates using the keyboard, then all elements are reachable via Tab and arrow keys, and the currently focused element has a visible focus indicator.
2. Given the Element Detail Panel, when it is rendered, then all interactive elements (close button, related element links, evidence sections) are reachable via keyboard and have associated ARIA labels.
3. Given the graph visualization (React Flow), when rendered, then an alternative accessible representation is available (e.g., a structured list of relationships) for users who cannot interact with the visual graph, accessible via a toggle or link.
4. Given verification status indicators (verified/non-verified icons), when rendered, then each has an `aria-label` or `aria-describedby` attribute conveying the status meaning to screen readers (e.g., "Verified: evidence confirmed in source document").
5. Given type group headers in the element list, when rendered, then they use appropriate heading levels or ARIA roles to establish document structure for screen reader navigation.
6. Given the visualization view as a whole, when audited for color contrast, then all text and interactive elements meet WCAG 2.1 AA minimum contrast ratios (4.5:1 for normal text, 3:1 for large text and UI components).
7. Given the relationship graph, when node colors or edge styles encode information (type, status), then the information is also conveyed through a non-color channel (labels, patterns, shapes) to support users with color vision deficiency.

**Traceability:**
- MVP Roadmap Feature 4: Accessibility as a deliverable.
- Tech Stack: shadcn/ui (built with accessibility in mind, uses Radix primitives).
- WCAG 2.1 AA compliance baseline.
