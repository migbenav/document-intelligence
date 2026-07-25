# Design — Knowledge Model Visualization & Exploration

## Overview

This document describes the technical design for the Knowledge Model Visualization & Exploration feature. It covers the frontend architecture, component structure, state management, API integration, graph visualization strategy, and key technical decisions required to implement the approved requirements.

This is a frontend-focused feature. The backend already exposes the Knowledge Model via `GET /api/v1/documents/{document_id}/knowledge-model` (implemented in Feature 3). This feature builds the React components, Zustand store, and interaction patterns that make the Knowledge Model explorable by the user.

The visualization layer is the primary means by which the user evaluates the Trust by Evidence model (ADR-004): every element displays its source_ref, verification status is visually indicated, and the user can trace any claim back to the original document.

## Relevant Documentation

- #[[file:.kiro/specs/km-visualization-exploration/requirements.md]]
- #[[file:.kiro/specs/knowledge-model-extraction/design.md]]
- #[[file:.kiro/specs/app-shell-upload-ui/design.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/architecture/001-technology-stack.md]]

---

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Frontend (Vercel)                                 │
│  React + TypeScript + Vite + Tailwind + shadcn/ui + Zustand + React Flow │
│                                                                          │
│  ┌─────────────┐  ┌──────────────────────┐  ┌──────────────────┐        │
│  │  App Shell  │  │  KM Visualization    │  │  API Client      │        │
│  │  (Feature 2)│  │  (This Feature)      │  │  (HTTP Layer)    │        │
│  └─────────────┘  └──────────────────────┘  └────────┬─────────┘        │
└───────────────────────────────────────────────────────┼──────────────────┘
                                                        │ HTTPS (CORS)
                                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Backend (Render)                                   │
│  FastAPI — already implemented (Feature 3)                               │
│                                                                          │
│  GET /api/v1/documents/{id}/knowledge-model → 200 | 404 | 409           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Frontend Internal Architecture

The feature follows the layered architecture established by the App Shell (Feature 2):

1. **Pages** — `KnowledgeModelPage` as the top-level route component.
2. **Components** — Visualization-specific components (element list, detail panel, graph view).
3. **Store** — Zustand `knowledgeModelStore` managing KM data, selection, navigation, and view state.
4. **API Client** — Extends the existing HTTP layer with `getKnowledgeModel()`.

```
KnowledgeModelPage ──▶ Components ──▶ knowledgeModelStore ──▶ API Client ──▶ Backend
                                              │
                                              └──▶ i18n (translation keys)
```

### Routing

The application currently uses conditional rendering based on document state rather than React Router. When a document reaches `completed` analysis status, the `AppShell` conditionally renders `KnowledgeModelPage` in place of the upload/processing views.

- No React Router dependency is introduced for the MVP. The `AppShell` determines which page to render based on the active document's state (no document → upload view, processing → status view, completed → Knowledge Model view).
- If React Router is introduced in a future iteration, `KnowledgeModelPage` maps naturally to a route like `/documents/{id}/knowledge-model`.
- For now, page transitions are managed through Zustand store state, keeping the navigation model simple and avoiding unnecessary routing complexity for a single-document workflow.

---

## Components and Interfaces

### Component Tree

```
<App>
  <AppShell>                              // Existing layout (Feature 2)
    <Header />                            // Existing header
    <main>
      <KnowledgeModelPage>                // Top-level page for this feature
        <KMHeader />                      // Verification rate summary + view toggle
        <ElementListView>                 // Grouped element list (default view)
          <TypeGroup>                     // Collapsible group per element type
            <ElementCard />              // Individual element preview card
          </TypeGroup>
        </ElementListView>
        <ElementDetailPanel>              // Detail panel (side or overlay)
          <EvidenceSection />            // source_ref + verification display
          <RelatedElements />            // Related elements with navigation
        </ElementDetailPanel>
        <RelationshipGraphView>           // React Flow canvas (graph view)
          <ElementNode />                // Custom node component
          <RelationshipEdge />           // Custom edge with type labeling
        </RelationshipGraphView>
        <EmptyState />                    // No elements extracted
        <LoadingState />                  // Skeleton/spinner during fetch
        <ErrorState />                    // Error message with retry action
      </KnowledgeModelPage>
    </main>
  </AppShell>
</App>
```

### Component Responsibilities

| Component | Responsibility | Requirements |
|-----------|---------------|--------------|
| `KnowledgeModelPage` | Orchestrates views based on store state (loading, empty, error, loaded); manages layout between list/graph and detail panel | Req 1, 7 |
| `KMHeader` | Displays verification rate summary, view mode toggle (list/graph) | Req 4.7 |
| `ElementListView` | Renders elements grouped by taxonomy type, handles keyboard navigation | Req 2 |
| `TypeGroup` | Collapsible section for a single type, shows type name + element count | Req 2.2, 2.3 |
| `ElementCard` | Element preview: name, truncated description, verification indicator | Req 2.4, 2.5 |
| `ElementDetailPanel` | Full element details: name, type, content, evidence, relationships | Req 3 |
| `EvidenceSection` | Renders evidence text span, contextual metadata, verification status with explanation | Req 3.2, 4.1, 4.2, 4.3 |
| `RelatedElements` | Lists related elements with type and relationship type, enables click-to-navigate | Req 3.6, 3.7, 6.1 |
| `RelationshipGraphView` | React Flow canvas with custom nodes/edges, auto-layout; handles empty-relationships state with explanatory message and list view toggle available | Req 5 |
| `ElementNode` | Custom React Flow node: element name + type icon/color | Req 5.2 |
| `RelationshipEdge` | Custom React Flow edge: labeled with relationship type, styled per type | Req 5.3, 5.4 |
| `EmptyState` | Message when KM has zero elements | Req 1.4 |
| `LoadingState` | Skeleton/spinner during fetch | Req 1.2 |
| `ErrorState` | Error message with retry action | Req 1.5 |

---

## Data Models

### Zustand Store

A dedicated Zustand store manages the Knowledge Model visualization state. Separated from the upload store (Feature 2) to maintain clear feature boundaries.

```typescript
type KMStatus = 'idle' | 'loading' | 'loaded' | 'error' | 'empty';
type ViewMode = 'list' | 'graph';

interface KnowledgeModelStore {
  // State
  status: KMStatus;
  knowledgeModel: KnowledgeModelResponse | null;
  selectedElementId: string | null;
  viewMode: ViewMode;
  navigationHistory: string[];        // Stack of previously selected element IDs
  error: string | null;
  documentId: string | null;          // ID of the document whose KM is cached

  // Actions
  fetchKnowledgeModel: (documentId: string) => Promise<void>;
  selectElement: (elementId: string) => void;
  navigateToElement: (elementId: string) => void;  // Push current to history + select new
  goBack: () => void;                              // Pop from history
  setViewMode: (mode: ViewMode) => void;
  reset: () => void;                               // Clear all state
}
```

**Action semantics:**

- `selectElement(id)` — Used for initial selection from the element list or graph (direct user interaction). Clears the `navigationHistory` since it represents a fresh selection context, not a drill-down from a previous element.
- `navigateToElement(id)` — Used when following a related element link from within the detail panel. Pushes the current `selectedElementId` onto the `navigationHistory` stack before updating selection, enabling back-navigation through the exploration path.
- `goBack()` — Pops the last element ID from `navigationHistory` and sets it as `selectedElementId`. If the history stack is empty, deselects (sets `selectedElementId` to null, closing the detail panel).

### State Transitions

```
idle ──[fetchKnowledgeModel called]──▶ loading
                                          │
                          ┌───────────────┼───────────────┐
                          │               │               │
                    [success, >0]   [success, 0]     [error]
                          │               │               │
                          ▼               ▼               ▼
                       loaded          empty           error
                          │                               │
                    [selectElement]                  [retry → fetch]
                          │                               │
                          ▼                               ▼
                    loaded (with                      loading
                    selectedElementId)

loaded ──[reset]──▶ idle
loaded ──[navigateToElement]──▶ loaded (push to history, update selection)
loaded ──[goBack]──▶ loaded (pop from history, update selection)
```

### Cache Invalidation

The store tracks `documentId` alongside the cached `knowledgeModel`. On `fetchKnowledgeModel(documentId)`:
- If `documentId` matches the stored one and status is `loaded`, skip fetch (return cached data).
- If `documentId` differs, reset and fetch fresh.
- The user can force refresh by calling `reset()` then `fetchKnowledgeModel()`.

---

## API Integration

### API Function

```typescript
// src/frontend/src/api/knowledgeModel.ts

async function getKnowledgeModel(documentId: string): Promise<KnowledgeModelResponse>
```

### Response Types (from Feature 3 backend)

```typescript
interface KnowledgeModelResponse {
  document_id: string;
  document_type: string;
  elements: KnowledgeElementResponse[];
  extraction_metadata: ExtractionMetadataResponse;
}

interface KnowledgeElementResponse {
  id: string;
  type: 'proposito' | 'concepto' | 'actor' | 'regla' | 'proceso' | 'restriccion';
  name: string;
  content: string;
  source_ref: SourceRefResponse;
  relations: RelationResponse[];
  verified: boolean;
}

interface SourceRefResponse {
  document_id: string;
  chunk_id: string;
  page: number | null;
  section: string | null;
  evidence: string;
}

interface RelationResponse {
  target_id: string;
  type: 'constrains' | 'participates_in' | 'depends_on' | 'contradicts';
  description: string | null;
}

interface ExtractionMetadataResponse {
  prompt_version: string;
  model_id: string;
  temperature: number;
  element_count: number;
  relationship_count: number;
  verification_rate: number;
  extracted_at: string;
}
```

### HTTP Configuration

```typescript
const FETCH_TIMEOUT_MS = 30_000;  // 30s for cold start tolerance (aligned with Feature 2)
```

### Error Handling at API Layer

| HTTP Status | Meaning | Store Behavior |
|-------------|---------|----------------|
| 200 | Success | Parse response → `loaded` or `empty` (based on element count) |
| 404 | Document not found | `error` with user-friendly message |
| 409 | Analysis not yet completed | `error` with message explaining analysis is still in progress |
| Network error / timeout | Unreachable | `error` with connectivity message + retry action |

---

## Key Technical Decisions

### Decision 1: React Flow for Graph Visualization

**Choice:** React Flow (reactflow) for the relationship graph.

**Reasoning:** React Flow is the project standard (documented in tech stack). It provides a mature, accessible canvas for node-graph visualization with built-in pan, zoom, and drag interactions. Custom nodes and edges are straightforward to implement. The library handles large graphs performantly with virtualization.

### Decision 2: Automatic Layout with dagre

**Choice:** dagre for automatic graph layout.

**Reasoning:** Knowledge Models can have 5-50+ elements. Manual positioning is impractical. Dagre provides a directed graph layout algorithm that minimizes edge crossings and produces readable hierarchical layouts. It's lightweight, well-tested, and the standard choice for React Flow auto-layout. ELK is more powerful but heavier — dagre is sufficient for the expected graph sizes in a single-document context.

### Decision 3: Separate Zustand Store

**Choice:** Dedicated `knowledgeModelStore` separate from the existing `uploadStore`.

**Reasoning:** Following the pattern established in Feature 2's design: "If future features need their own state (e.g., Knowledge Model viewer), they get their own stores." The KM visualization has distinct lifecycle (fetch once, navigate many times) and distinct state shape (elements, selection, history) that don't overlap with the upload workflow.

### Decision 4: Master-Detail Layout Pattern

**Choice:** Side-by-side master-detail on desktop, stacked/overlay on mobile.

**Reasoning:** The element list + detail panel is a natural master-detail pattern. On desktop (≥1024px), side-by-side gives the user context (list) while reading details. On mobile (<768px), full-screen navigation between list and detail avoids cramped layouts. The 768-1023px range uses a sliding panel overlay to balance information density with readability.

### Decision 5: Navigation History Stack

**Choice:** In-store navigation history as a string array (stack of element IDs).

**Reasoning:** When exploring relationships (element A → related element B → related element C), the user needs a "back" button to retrace their path. A simple stack of previously-viewed element IDs provides this without introducing a full routing solution. The stack is capped at 50 entries to prevent memory growth in long exploration sessions.

### Decision 6: Accessible Graph Alternative

**Choice:** Text-based relationship list as an accessible alternative to the visual graph.

**Reasoning:** React Flow's canvas is not fully accessible to screen readers. Per Req 8.3, an alternative structured list of relationships must be available. This is implemented as a toggle within the graph view area — users who cannot interact with the canvas can switch to a formatted list showing "Element A → [relationship type] → Element B" entries, navigable via keyboard.

### Decision 7: Color + Shape Encoding for Types

**Choice:** Each element type has a unique color AND a unique shape/icon.

**Reasoning:** Per Req 8.7, information encoded via color must also be available through a non-color channel. Using both color and shape/icon for element types ensures users with color vision deficiency can distinguish types. The same principle applies to verification status (checkmark vs. warning triangle, not just green vs. yellow).

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Data Integrity — Display matches API response

*For any* Knowledge Model response from the API, the UI renders exactly the same set of elements (by ID, type, name, content) and relationships as contained in the response — no elements are added, removed, or modified during display.

**Validates: Requirements 1.3, 2.1**

### Property 2: Navigation Consistency

*For any* element selected via the list view, detail panel related elements section, or graph node click, the detail panel always displays the full details (name, type, content, source_ref, relationships) of exactly the element whose ID matches the current `selectedElementId` in the store.

**Validates: Requirements 3.1, 3.7, 5.5, 6.1, 6.5**

### Property 3: View Synchronization — Selection is reflected across views

*For any* selected element, if the element list is visible, the selected element's card is visually highlighted; and if the graph view is visible, the corresponding node is visually focused/highlighted.

**Validates: Requirements 6.4**

### Property 4: Cache Validity

*For any* state where `knowledgeModel` is not null in the store, `documentId` in the store equals `knowledgeModel.document_id` — the cached data always corresponds to the document the user is currently viewing.

**Validates: Requirements 1.6**

### Property 5: Graceful Degradation — Evidence failures don't block element access

*For any* element where the evidence section encounters a rendering or data error, the element's name, type, content, and relationships remain visible and navigable — only the evidence area shows an inline error message.

**Validates: Requirements 3.3, 4.4**

### Property 6: Accessibility Parity

*For any* information conveyed visually in the UI (verification status, element type, relationship type), an equivalent non-visual representation exists (aria-label, text label, or accessible alternative view) that conveys the same meaning to screen reader users.

**Validates: Requirements 4.2, 4.3, 8.3, 8.4, 8.7**

### Property 7: Navigation History Integrity

*For any* sequence of `navigateToElement` calls followed by `goBack` calls, the `selectedElementId` returns to each previously selected element in reverse order (LIFO), and the history stack never contains the currently selected element.

**Validates: Requirements 3.8, 6.3**

---

## Interaction Flow

```
1. User navigates to Knowledge Model visualization (KnowledgeModelPage mounts)
       │
       ├── [KM already cached for this documentId] → display cached data (status: loaded)
       │
       └── [No cache or different documentId]
              │
              ▼
2. Fetch Knowledge Model (status: loading)
       │── Skeleton/spinner displayed
       │── 30s timeout for cold start
       │
       ├── [network error / timeout] → ErrorState with retry button
       ├── [404] → ErrorState: "Document not found"
       ├── [409] → ErrorState: "Analysis not yet completed"
       │
       └── [200 success]
              │
              ├── [0 elements] → EmptyState (status: empty)
              │
              └── [>0 elements] → ElementListView (status: loaded)
                     │
                     ▼
3. User browses element list (grouped by type)
       │── Keyboard: arrow keys navigate within/between groups
       │── Tab: moves focus to elements, groups
       │
       └── [click/Enter on element]
              │
              ▼
4. Element Detail Panel opens (selectedElementId set)
       │── Full content, evidence, verification status, relationships displayed
       │── On desktop: side panel. On mobile: full-screen overlay
       │
       ├── [click related element] → navigateToElement (push to history, update panel)
       ├── [back button / Escape] → goBack (pop history) or close panel
       │
       └── [view toggle → graph]
              │
              ▼
5. Relationship Graph View (React Flow)
       │── Auto-layout with dagre
       │── Nodes: element name + type icon/color
       │── Edges: labeled with relationship type
       │── contradicts: red/dashed, bidirectional
       │
       ├── [click node] → selectElement → detail panel shows that element
       ├── [click edge] → tooltip with relationship info
       ├── [pan/zoom/drag] → standard React Flow interactions
       │
       └── [toggle accessible view] → structured text list of relationships
```

---

## Error Handling

| Error Source | Error Type | UI Behavior | Recovery |
|-------------|-----------|-------------|----------|
| Network error on fetch | `network` | ErrorState with "Unable to reach server" | Retry button |
| Backend 404 | `not_found` | ErrorState with "Document not found" | Navigate to upload |
| Backend 409 | `not_ready` | ErrorState with "Analysis not yet completed" | Retry button (polling not implemented — manual retry) |
| Fetch timeout (30s) | `timeout` | ErrorState with connectivity message | Retry button |
| Evidence render error | `partial` | Inline error in EvidenceSection only; rest of panel functional | None needed (graceful degradation) |
| Verification indicator render error | `partial` | Element displayed without status indicator | None needed (graceful degradation) |
| React Flow render error | `graph_error` | Fallback to list view with message | Toggle back to list |
| Empty Knowledge Model | `empty` | EmptyState with explanation | Navigate to re-analyze or upload different doc |
| No relationships in KM | `no_relationships` | RelationshipGraphView shows explanatory message instead of canvas; toggle to list view remains available | None needed |

All errors display user-friendly messages from i18n keys. No HTTP status codes, stack traces, or raw JSON are exposed to the user.

---

## Internationalization

Translation keys for the Knowledge Model visualization feature, extending the existing i18n JSON structure established in Feature 2:

```json
{
  "km": {
    "title": "Knowledge Model",
    "verificationRate": "{rate}% of elements verified",
    "viewMode": {
      "list": "List view",
      "graph": "Graph view"
    },
    "typeGroups": {
      "proposito": "Purpose",
      "concepto": "Concepts",
      "actor": "Actors",
      "regla": "Rules",
      "proceso": "Processes",
      "restriccion": "Constraints"
    },
    "element": {
      "verified": "Verified: evidence confirmed in source document",
      "notVerified": "Not verified: evidence not found in source document",
      "evidence": "Source Evidence",
      "evidenceError": "Evidence could not be loaded",
      "relatedElements": "Related Elements",
      "noRelatedElements": "No relationships identified"
    },
    "relationships": {
      "constrains": "Constrains",
      "participates_in": "Participates in",
      "depends_on": "Depends on",
      "contradicts": "Contradicts"
    },
    "graph": {
      "noRelationships": "No relationships were identified in this document. Relationships are optional and are extracted when the system identifies them with sufficient confidence.",
      "accessibleView": "View as accessible list"
    },
    "states": {
      "loading": "Loading Knowledge Model...",
      "empty": "No knowledge elements were extracted from this document.",
      "error": {
        "network": "Unable to reach the server. Please check your connection.",
        "notFound": "Document not found.",
        "notReady": "Analysis is not yet completed. Please wait and try again.",
        "generic": "Failed to load the Knowledge Model."
      },
      "retry": "Try again"
    },
    "navigation": {
      "back": "Back",
      "close": "Close details"
    },
    "count": {
      "elements": "{count} elements",
      "noElements": "No elements"
    }
  }
}
```

---

## Responsive Design

| Breakpoint | Layout Behavior |
|-----------|----------------|
| ≥ 1024px (desktop) | Master-detail side-by-side: element list (left, ~40% width) + detail panel (right, ~60% width). Graph view takes full content area with detail panel as an overlay/sidebar. |
| 768px–1023px (tablet) | Element list full width. Detail panel as a sliding overlay from the right (50-60% width). Graph view full width with panel overlay. |
| < 768px (mobile) | Full-screen list view. Element selection navigates to full-screen detail view with back button. Graph view with touch-friendly controls, tap node for detail. |

### Layout Composition: Graph View + Detail Panel

The graph view and detail panel coexist differently at each breakpoint:

| Breakpoint | List Mode | Graph Mode |
|-----------|-----------|------------|
| ≥ 1024px (desktop) | Side-by-side: list (40%) + detail panel (60%) | Full-width graph canvas with a collapsible detail sidebar (right, 350px) that overlays the graph when an element is selected |
| 768–1023px (tablet) | Full-width list; detail panel slides in from right (60% width) as overlay | Full-width graph; detail panel slides in from right as overlay |
| < 768px (mobile) | Full-screen list → full-screen detail on select | Full-screen graph → tap node shows full-screen detail |

The React Flow canvas adapts to container size. Touch interactions (pinch zoom, two-finger pan) are enabled on mobile/tablet.

---

## Accessibility Implementation

| Concern | Implementation |
|---------|---------------|
| Keyboard navigation in element list | `role="listbox"` on list container, `role="option"` on items. Arrow keys move focus, Enter/Space selects. |
| Type group headers | `role="heading"` with appropriate aria-level, or semantic `<h3>`/`<h4>` elements |
| Verification status | `aria-label="Verified: evidence confirmed in source document"` or `aria-label="Not verified: evidence not found in source document"` on status icons |
| Detail panel focus management | Focus moves to panel heading when opened. Focus returns to triggering element when closed. `aria-modal` on mobile full-screen. |
| Graph accessible alternative | Toggle link: "View as accessible list". Renders relationships as a structured table/list with aria-labels. |
| Color-blind safe design | Types use unique shapes/icons in addition to color. Verification uses checkmark vs. warning triangle. Contradicts edges use dashed line pattern + label, not just red color. |
| Contrast | All text meets WCAG 2.1 AA (4.5:1 normal text, 3:1 large text/UI components). shadcn/ui defaults meet this. |

---

## File Structure

```
src/frontend/src/
├── api/
│   ├── client.ts                       # Existing HTTP client (Feature 2)
│   ├── documents.ts                    # Existing upload/status API functions
│   └── knowledgeModel.ts              # NEW: getKnowledgeModel()
├── components/
│   ├── layout/                         # Existing (Feature 2)
│   │   ├── AppShell.tsx
│   │   └── Header.tsx
│   ├── upload/                         # Existing (Feature 2)
│   │   └── ...
│   ├── knowledge-model/               # NEW: All KM visualization components
│   │   ├── KnowledgeModelPage.tsx     # Top-level page component
│   │   ├── KMHeader.tsx               # Verification summary + view toggle
│   │   ├── ElementListView.tsx        # Grouped element list
│   │   ├── TypeGroup.tsx              # Collapsible type section
│   │   ├── ElementCard.tsx            # Element preview card
│   │   ├── ElementDetailPanel.tsx     # Full element details
│   │   ├── EvidenceSection.tsx        # Evidence text + verification display
│   │   ├── RelatedElements.tsx        # Related elements list with navigation
│   │   ├── RelationshipGraphView.tsx  # React Flow canvas wrapper
│   │   ├── ElementNode.tsx            # Custom React Flow node
│   │   ├── RelationshipEdge.tsx       # Custom React Flow edge
│   │   ├── AccessibleRelationshipList.tsx  # Text alternative to graph
│   │   ├── EmptyState.tsx             # Empty KM message
│   │   ├── LoadingState.tsx           # Skeleton/spinner
│   │   └── ErrorState.tsx             # Error display with retry
│   └── ui/                             # Existing shadcn/ui components
│       └── ...
├── store/
│   ├── uploadStore.ts                  # Existing (Feature 2)
│   └── knowledgeModelStore.ts         # NEW: KM visualization state
├── i18n/
│   ├── index.ts                        # Existing
│   ├── en.json                         # Extended with KM visualization keys
│   └── es.json                         # Extended with KM visualization keys
├── lib/
│   ├── validation.ts                   # Existing (Feature 2)
│   ├── utils.ts                        # Existing (Feature 2)
│   └── graphLayout.ts                 # NEW: dagre layout utility
└── types/
    ├── api.ts                          # Existing + extended with KM response types
    └── knowledgeModel.ts              # NEW: Frontend-specific KM types (if needed)
```

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| Store | State transitions, cache logic, navigation history | Vitest; test fetchKnowledgeModel transitions, selectElement/navigateToElement/goBack, cache invalidation, reset |
| Components | Rendering and interactions | Vitest + React Testing Library; test ElementCard renders correct data, TypeGroup groups correctly, detail panel opens on selection, keyboard navigation |
| API Client | Request construction, response parsing, error classification | Vitest with mocked fetch; verify correct URL, timeout handling, error status mapping |
| Graph | Node/edge rendering, layout | Vitest + React Testing Library; verify correct nodes rendered from elements, edges from relationships, contradicts edges bidirectional |
| Accessibility | ARIA labels, keyboard flow, focus management | React Testing Library + axe-core (jest-axe); verify aria-labels on verification indicators, keyboard navigation, focus management on panel open/close |
| Integration | Full visualization flow | Vitest + MSW; simulate fetch → render → navigate → back flow |
| Property Tests | Correctness properties (data integrity, navigation, cache) | Vitest + fast-check; property-based tests for store state invariants |

**Property Test Configuration:**
- Minimum 100 iterations per property test
- Library: fast-check (TypeScript property-based testing)
- Each property test references its design document property
- Tag format: **Feature: km-visualization-exploration, Property {number}: {property_text}**

---

## Dependencies

| Package | Purpose | Justification |
|---------|---------|---------------|
| reactflow | Graph visualization | Project standard (tech stack: "Visualización relaciones: React Flow") |
| @dagrejs/dagre | Automatic graph layout (TypeScript-compatible dagre fork) | Active fork with TS types; standard pairing with React Flow for directed graph layout |
| fast-check | Property-based testing | Standard PBT library for TypeScript/Vitest |
| All existing (Feature 2) | React, TypeScript, Vite, Tailwind, shadcn/ui, Zustand, Vitest, MSW | Already installed |

No additional UI dependencies beyond React Flow and dagre are introduced. All component styling uses the existing Tailwind + shadcn/ui toolkit.

---

## Traceability to Requirements

| Requirement | Design Components |
|-------------|-------------------|
| Req 1: Data Fetching & State Management | `knowledgeModelStore`, `api/knowledgeModel.ts`, `LoadingState`, `EmptyState`, `ErrorState`, cache logic |
| Req 2: Element List/Grid View | `ElementListView`, `TypeGroup`, `ElementCard`, taxonomy ordering, keyboard nav |
| Req 3: Element Detail Panel | `ElementDetailPanel`, `EvidenceSection`, `RelatedElements`, focus management, close/back behavior |
| Req 4: Evidence Display & Verification | `EvidenceSection`, verification icons in `ElementCard` and detail panel, `KMHeader` verification rate |
| Req 5: Relationship Visualization | `RelationshipGraphView`, `ElementNode`, `RelationshipEdge`, dagre layout, contradicts bidirectional styling |
| Req 6: Navigation Between Elements | `navigateToElement`, `goBack`, navigation history stack, related element click handlers |
| Req 7: Responsive Layout & Shell Integration | Breakpoint-based layouts, master-detail pattern, shell stability |
| Req 8: Accessibility | ARIA labels, keyboard navigation, accessible graph alternative, color+shape encoding, focus management, contrast |
