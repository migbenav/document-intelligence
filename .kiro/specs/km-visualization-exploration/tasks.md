# Implementation Plan: Knowledge Model Visualization & Exploration

## Overview

This plan implements the frontend visualization and exploration layer for the Knowledge Model. It covers TypeScript types, API client, Zustand store, i18n extensions, element list/detail components, React Flow graph visualization, accessibility features, responsive layout, and page orchestration. Tasks are ordered by dependency — foundational types and infrastructure first, then core UI components, then graph view, then integration and testing.

The backend endpoint `GET /api/v1/documents/{document_id}/knowledge-model` already exists (Feature 3). This feature builds the React components, state management, and interaction patterns that consume it.

## Tasks

- [ ] 1. Foundation: Types, API client, and store
  - [ ] 1.1 Create TypeScript types and API client function
    - Create `src/frontend/src/types/knowledgeModel.ts` with interfaces: `KnowledgeModelResponse`, `KnowledgeElementResponse`, `SourceRefResponse`, `RelationResponse`, `ExtractionMetadataResponse`
    - Create `src/frontend/src/api/knowledgeModel.ts` with `getKnowledgeModel(documentId: string): Promise<KnowledgeModelResponse>` using the existing HTTP client pattern from `api/client.ts`
    - Configure 30s timeout for cold-start tolerance
    - Handle HTTP status codes: 200 (success), 404 (not found), 409 (not ready), network errors
    - _Requirements: 1.1, 1.5, 1.7_

  - [ ] 1.2 Implement Zustand knowledgeModelStore
    - Create `src/frontend/src/store/knowledgeModelStore.ts` with state: `status` (idle|loading|loaded|error|empty), `knowledgeModel`, `selectedElementId`, `viewMode` (list|graph), `navigationHistory`, `error`, `documentId`
    - Implement actions: `fetchKnowledgeModel(documentId)` with cache logic (skip fetch if same documentId and loaded), `selectElement(id)` (clears history), `navigateToElement(id)` (pushes current to history stack), `goBack()` (pops from history), `setViewMode(mode)`, `reset()`
    - Cap navigation history at 50 entries
    - State transitions: idle→loading→loaded/empty/error, error→loading (retry)
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 6.1, 6.3_

  - [ ] 1.3 Extend i18n translation files
    - Extend `src/frontend/src/i18n/en.json` with the `km` namespace keys (title, verificationRate, viewMode, typeGroups, element, relationships, graph, states, navigation, count)
    - Extend `src/frontend/src/i18n/es.json` with equivalent Spanish translations
    - Follow the JSON structure defined in the design document's Internationalization section
    - _Requirements: 8.4 (aria-labels from i18n), all requirements (user-facing strings)_

- [ ] 2. Element list view components
  - [ ] 2.1 Implement ElementCard component
    - Create `src/frontend/src/components/knowledge-model/ElementCard.tsx`
    - Display: element name, truncated description (first 120 chars or first sentence), verification status icon (checkmark for verified, warning triangle for not-verified)
    - Verification icons include `aria-label` from i18n keys (`km.element.verified` / `km.element.notVerified`)
    - Click/Enter triggers element selection via store
    - Use `role="option"` for accessibility within the listbox container
    - _Requirements: 2.4, 2.5, 2.6, 4.2, 4.3, 4.5, 8.1_

  - [ ] 2.2 Implement TypeGroup component
    - Create `src/frontend/src/components/knowledge-model/TypeGroup.tsx`
    - Render a collapsible section with type name header (from i18n `km.typeGroups.*`) and element count badge
    - Show empty state when count is zero (subtle "No elements" indicator)
    - Use semantic heading elements (`<h3>`) for screen reader navigation
    - Render child `ElementCard` components for each element in the group
    - _Requirements: 2.2, 2.3, 8.5_

  - [ ] 2.3 Implement ElementListView component
    - Create `src/frontend/src/components/knowledge-model/ElementListView.tsx`
    - Group elements by type using fixed taxonomy order: propósito, conceptos, actores, reglas, procesos, restricciones
    - Implement keyboard navigation: arrow keys move focus within/between groups, Tab for focus traversal
    - Use `role="listbox"` on container with proper ARIA attributes
    - _Requirements: 2.1, 2.6, 2.7, 8.1_

- [ ] 3. Element detail panel and evidence
  - [ ] 3.1 Implement EvidenceSection component
    - Create `src/frontend/src/components/knowledge-model/EvidenceSection.tsx`
    - Render evidence text span in visually distinct blockquote styling
    - Display contextual metadata: section heading (Markdown) or page number (PDF)
    - Show verification status with icon + explanatory text (verified = "evidence confirmed in source document", not-verified = "evidence not found in source document")
    - Handle evidence render errors gracefully: show inline error message, don't block parent
    - _Requirements: 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.6_

  - [ ] 3.2 Implement RelatedElements component
    - Create `src/frontend/src/components/knowledge-model/RelatedElements.tsx`
    - List each related element with: name, type badge, relationship type label (from i18n `km.relationships.*`)
    - Click on a related element calls `navigateToElement(id)` in the store (pushes to history)
    - Show "No relationships identified" message when empty
    - All items keyboard-accessible (focusable, Enter to navigate)
    - _Requirements: 3.6, 3.7, 6.1, 6.5_

  - [ ] 3.3 Implement ElementDetailPanel component
    - Create `src/frontend/src/components/knowledge-model/ElementDetailPanel.tsx`
    - Display: element name, type badge, full description/content
    - Compose `EvidenceSection` and `RelatedElements` as child sections
    - Back button calls `goBack()` from store; Escape key closes panel or navigates back
    - Focus management: move focus to panel heading on open, return focus to trigger on close
    - Responsive: side panel on desktop (≥1024px), sliding overlay on tablet (768-1023px), full-screen on mobile (<768px) with back button
    - `aria-modal` attribute on mobile full-screen view
    - _Requirements: 3.1, 3.4, 3.5, 3.8, 6.3, 7.2, 7.3, 7.4, 8.2_

- [ ] 4. Checkpoint - Verify list view and detail panel
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Header, states, and page layout
  - [ ] 5.1 Implement KMHeader component
    - Create `src/frontend/src/components/knowledge-model/KMHeader.tsx`
    - Display verification rate from `extraction_metadata.verification_rate` (e.g., "85% of elements verified")
    - View mode toggle buttons (list/graph) calling `setViewMode()` in store
    - Use i18n keys for labels
    - _Requirements: 4.7_

  - [ ] 5.2 Implement LoadingState, EmptyState, and ErrorState components
    - Create `src/frontend/src/components/knowledge-model/LoadingState.tsx` — skeleton/spinner with i18n loading message
    - Create `src/frontend/src/components/knowledge-model/EmptyState.tsx` — explanatory message when zero elements extracted
    - Create `src/frontend/src/components/knowledge-model/ErrorState.tsx` — error message (network/notFound/notReady/generic from i18n) with retry button calling `fetchKnowledgeModel()` again
    - _Requirements: 1.2, 1.4, 1.5_

  - [ ] 5.3 Implement KnowledgeModelPage orchestrator
    - Create `src/frontend/src/components/knowledge-model/KnowledgeModelPage.tsx`
    - On mount: call `fetchKnowledgeModel(documentId)` if not cached
    - Render based on store status: loading→LoadingState, empty→EmptyState, error→ErrorState, loaded→KMHeader + content views
    - Manage layout composition: ElementListView + ElementDetailPanel (when viewMode=list), RelationshipGraphView + ElementDetailPanel (when viewMode=graph)
    - Responsive master-detail layout: side-by-side ≥1024px, stacked/overlay 768-1023px, full-screen navigation <768px
    - _Requirements: 1.1, 1.3, 7.1, 7.2, 7.3, 7.4, 7.6_

  - [ ] 5.4 Integrate KnowledgeModelPage into AppShell
    - Modify `src/frontend/src/components/layout/AppShell.tsx` to conditionally render `KnowledgeModelPage` when document analysis status is "completed"
    - Ensure shell header and navigation remain stable during page transitions (no layout shifts)
    - _Requirements: 7.1, 7.6_

- [ ] 6. Relationship graph visualization
  - [ ] 6.1 Install dependencies and create graph layout utility
    - Install `reactflow` and `@dagrejs/dagre` packages
    - Create `src/frontend/src/lib/graphLayout.ts` with dagre layout function: accepts nodes and edges, returns positioned nodes using directed graph algorithm (minimizes edge crossings)
    - Configure layout direction (top-to-bottom), node spacing, and rank separation
    - _Requirements: 5.8_

  - [ ] 6.2 Implement ElementNode custom React Flow node
    - Create `src/frontend/src/components/knowledge-model/ElementNode.tsx`
    - Display: element name + type indicator (unique color AND unique shape/icon per type for color-blind accessibility)
    - Highlight state when selected
    - _Requirements: 5.2, 8.7_

  - [ ] 6.3 Implement RelationshipEdge custom React Flow edge
    - Create `src/frontend/src/components/knowledge-model/RelationshipEdge.tsx`
    - Display relationship type as label on edge
    - Style per type: "contradicts" uses dashed line + distinct color + bidirectional markers
    - Non-color encoding: labels always visible, dashed pattern for contradicts
    - _Requirements: 5.3, 5.4, 8.7_

  - [ ] 6.4 Implement RelationshipGraphView component
    - Create `src/frontend/src/components/knowledge-model/RelationshipGraphView.tsx`
    - Convert KM elements to React Flow nodes and relationships to edges
    - Apply dagre auto-layout on initial render
    - Enable standard React Flow interactions: pan, zoom, node dragging
    - Handle node click → `selectElement(id)` in store
    - Handle empty relationships: display explanatory message (from i18n `km.graph.noRelationships`)
    - Touch-friendly controls for mobile (pinch zoom, two-finger pan)
    - _Requirements: 5.1, 5.5, 5.6, 5.7, 5.8, 7.5_

  - [ ] 6.5 Implement AccessibleRelationshipList component
    - Create `src/frontend/src/components/knowledge-model/AccessibleRelationshipList.tsx`
    - Render relationships as structured list: "Element A → [relationship type] → Element B"
    - Toggle link/button in graph view area: "View as accessible list"
    - All items keyboard-navigable, clicking element names triggers navigation
    - _Requirements: 8.3, 8.7_

- [ ] 7. Checkpoint - Verify graph view and full integration
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Testing
  - [ ]* 8.1 Write store unit tests
    - Create `src/frontend/tests/store/knowledgeModelStore.test.ts`
    - Test state transitions: idle→loading→loaded, idle→loading→error, idle→loading→empty
    - Test cache logic: skip fetch when documentId matches and loaded, reset on different documentId
    - Test selectElement clears history, navigateToElement pushes to history, goBack pops from history
    - Test history cap at 50 entries
    - Test reset clears all state
    - _Requirements: 1.1, 1.6, 6.3_

  - [ ]* 8.2 Write component tests
    - Create `src/frontend/tests/components/knowledge-model/` directory with test files
    - Test ElementCard: renders name, truncated description, verification icon with correct aria-label
    - Test TypeGroup: renders header with count, handles empty groups
    - Test ElementDetailPanel: renders full content, evidence, related elements; handles back navigation
    - Test EvidenceSection: renders evidence text in blockquote, shows verification status, handles error gracefully
    - Test KMHeader: displays verification rate, toggles view mode
    - Test ErrorState: shows error message, retry button triggers fetch
    - _Requirements: 2.4, 2.5, 3.1, 3.2, 4.1, 4.7_

  - [ ]* 8.3 Write property-based tests with fast-check
    - Install `fast-check` as dev dependency
    - Create `src/frontend/tests/properties/knowledgeModel.property.test.ts`
    - **Property 1: Data Integrity** — For any generated KnowledgeModelResponse, the store's loaded state contains exactly the same elements (by id, type, name) as the input response
    - **Validates: Requirements 1.3, 2.1**
    - **Property 4: Cache Validity** — For any state where knowledgeModel is not null, documentId in store equals knowledgeModel.document_id
    - **Validates: Requirements 1.6**
    - **Property 7: Navigation History Integrity** — For any sequence of navigateToElement calls followed by goBack calls, selectedElementId returns to each previously selected element in LIFO order, and history never contains the currently selected element
    - **Validates: Requirements 3.8, 6.3**
    - Minimum 100 iterations per property test
    - _Requirements: 1.3, 1.6, 2.1, 3.8, 6.3_

  - [ ]* 8.4 Write accessibility tests
    - Create `src/frontend/tests/accessibility/knowledgeModel.a11y.test.ts`
    - Use jest-axe (axe-core) to verify no accessibility violations on rendered components
    - Verify aria-labels on verification status icons
    - Verify keyboard navigation (Tab, Arrow keys, Enter, Escape) works correctly
    - Verify focus management on detail panel open/close
    - Verify contrast ratios meet WCAG 2.1 AA
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The backend endpoint already exists — no backend work is needed
- Dependencies to install: `reactflow`, `@dagrejs/dagre`, `fast-check` (dev)
- All user-facing strings must come from i18n keys — no hardcoded strings in JSX
- Verification status uses both color AND shape (checkmark vs. warning triangle) for color-blind accessibility
- React Flow canvas is supplemented by AccessibleRelationshipList for screen reader users

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "5.2"] },
    { "id": 3, "tasks": ["2.2", "3.1", "3.2", "5.1"] },
    { "id": 4, "tasks": ["2.3", "3.3"] },
    { "id": 5, "tasks": ["5.3"] },
    { "id": 6, "tasks": ["5.4", "6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3"] },
    { "id": 8, "tasks": ["6.4", "6.5"] },
    { "id": 9, "tasks": ["8.1", "8.2", "8.3", "8.4"] }
  ]
}
```
