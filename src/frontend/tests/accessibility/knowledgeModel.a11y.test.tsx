import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import { ElementCard } from '@/components/knowledge-model/ElementCard';
import { TypeGroup } from '@/components/knowledge-model/TypeGroup';
import { ElementListView } from '@/components/knowledge-model/ElementListView';
import { ElementDetailPanel } from '@/components/knowledge-model/ElementDetailPanel';
import { KMHeader } from '@/components/knowledge-model/KMHeader';
import { AccessibleRelationshipList } from '@/components/knowledge-model/AccessibleRelationshipList';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

// Extend expect with jest-axe matchers
expect.extend(toHaveNoViolations);

// Mock window.matchMedia for ElementDetailPanel tests
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// --- Helpers ---

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function makeElement(overrides: Partial<KnowledgeElementResponse> = {}): KnowledgeElementResponse {
  return {
    id: 'elem-1',
    type: 'concepto',
    name: 'Test Element',
    content: 'This is a test element description for accessibility testing.',
    source_ref: {
      document_id: 'doc-1',
      chunk_id: 'chunk-1',
      page: 3,
      section: 'Introduction',
      evidence: 'Evidence text from the source document.',
    },
    relations: [],
    verified: true,
    ...overrides,
  };
}

// --- Tests ---

describe('Accessibility Tests — Knowledge Model Components', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  // ================================================================
  // ElementCard — axe-core + aria-labels + keyboard
  // ================================================================
  describe('ElementCard', () => {
    it('has no accessibility violations', async () => {
      const element = makeElement();
      // Wrap in a listbox since ElementCard uses role="option"
      const { container } = render(
        <TranslationProvider>
          <div role="listbox" aria-label="Elements">
            <ElementCard element={element} />
          </div>
        </TranslationProvider>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('verified icon has correct aria-label', () => {
      const element = makeElement({ verified: true });
      renderWithProviders(
        <div role="listbox" aria-label="Elements">
          <ElementCard element={element} />
        </div>,
      );

      const icon = screen.getByLabelText('Verified: evidence confirmed in source document');
      expect(icon).toBeInTheDocument();
      expect(icon).toHaveAttribute('role', 'img');
    });

    it('not-verified icon has correct aria-label', () => {
      const element = makeElement({ verified: false });
      renderWithProviders(
        <div role="listbox" aria-label="Elements">
          <ElementCard element={element} />
        </div>,
      );

      const icon = screen.getByLabelText('Not verified: evidence not found in source document');
      expect(icon).toBeInTheDocument();
      expect(icon).toHaveAttribute('role', 'img');
    });

    it('triggers selection on Enter key press', () => {
      const element = makeElement({ id: 'elem-keyboard' });
      renderWithProviders(
        <div role="listbox" aria-label="Elements">
          <ElementCard element={element} />
        </div>,
      );

      const card = screen.getByRole('option');
      fireEvent.keyDown(card, { key: 'Enter' });

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-keyboard');
    });

    it('is focusable via tabIndex', () => {
      const element = makeElement();
      renderWithProviders(
        <div role="listbox" aria-label="Elements">
          <ElementCard element={element} />
        </div>,
      );

      const card = screen.getByRole('option');
      expect(card).toHaveAttribute('tabindex', '0');
    });
  });

  // ================================================================
  // TypeGroup — axe-core + heading structure
  // ================================================================
  describe('TypeGroup', () => {
    it('has no accessibility violations', async () => {
      const elements = [makeElement({ id: 'e1', name: 'Concept A' })];
      const { container } = renderWithProviders(
        <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('uses semantic heading element for type name', () => {
      const elements = [makeElement()];
      renderWithProviders(
        <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
      );

      const heading = screen.getByRole('heading', { level: 3 });
      expect(heading).toHaveTextContent('Concepts');
    });

    it('has aria-expanded attribute on the toggle button', () => {
      const elements = [makeElement()];
      renderWithProviders(
        <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-expanded', 'true');
    });
  });

  // ================================================================
  // ElementListView — axe-core + navigation landmark
  // ================================================================
  describe('ElementListView', () => {
    it('has no accessibility violations', async () => {
      const elements = [
        makeElement({ id: 'e1', type: 'proposito', name: 'Purpose A' }),
        makeElement({ id: 'e2', type: 'concepto', name: 'Concept B' }),
      ];
      const { container } = renderWithProviders(
        <ElementListView elements={elements} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('renders as a navigation landmark', () => {
      const elements = [makeElement()];
      renderWithProviders(<ElementListView elements={elements} />);

      const nav = screen.getByRole('navigation');
      expect(nav).toBeInTheDocument();
      expect(nav).toHaveAttribute('aria-label', 'Knowledge Model');
    });
  });

  // ================================================================
  // ElementDetailPanel — axe-core + focus management + keyboard
  // ================================================================
  describe('ElementDetailPanel', () => {
    it('has no accessibility violations', async () => {
      const element = makeElement();
      const { container } = renderWithProviders(
        <ElementDetailPanel element={element} allElements={[element]} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('moves focus to heading on mount', () => {
      const element = makeElement({ id: 'focus-elem', name: 'Focused Element' });
      renderWithProviders(
        <ElementDetailPanel element={element} allElements={[element]} />,
      );

      const heading = screen.getByTestId('detail-panel-heading');
      expect(document.activeElement).toBe(heading);
    });

    it('navigates back on Escape key press', () => {
      useKnowledgeModelStore.getState().selectElement('elem-prev');
      useKnowledgeModelStore.getState().navigateToElement('elem-current');

      const element = makeElement({ id: 'elem-current' });
      renderWithProviders(
        <ElementDetailPanel element={element} allElements={[element]} />,
      );

      const panel = screen.getByTestId('element-detail-panel');
      fireEvent.keyDown(panel, { key: 'Escape' });

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-prev');
    });

    it('has region role with aria-label', () => {
      const element = makeElement({ name: 'Panel Region' });
      renderWithProviders(
        <ElementDetailPanel element={element} allElements={[element]} />,
      );

      const panel = screen.getByTestId('element-detail-panel');
      expect(panel).toHaveAttribute('role', 'region');
      expect(panel).toHaveAttribute('aria-label', 'Panel Region');
    });

    it('back button has accessible aria-label', () => {
      const element = makeElement();
      renderWithProviders(
        <ElementDetailPanel element={element} allElements={[element]} />,
      );

      const backBtn = screen.getByTestId('detail-panel-back');
      expect(backBtn).toHaveAttribute('aria-label', 'Back');
    });

    it('all interactive elements are keyboard-reachable', () => {
      const relatedElement = makeElement({ id: 'elem-2', name: 'Related', type: 'actor' });
      const element = makeElement({
        relations: [{ target_id: 'elem-2', type: 'depends_on', description: null }],
      });
      renderWithProviders(
        <ElementDetailPanel element={element} allElements={[element, relatedElement]} />,
      );

      // Back button is focusable
      const backBtn = screen.getByTestId('detail-panel-back');
      expect(backBtn.tagName).toBe('BUTTON');

      // Related element links are focusable
      const relatedLink = screen.getByText('Related');
      expect(
        relatedLink.closest('[tabindex]') !== null ||
        relatedLink.tagName === 'BUTTON' ||
        relatedLink.tagName === 'A' ||
        relatedLink.getAttribute('tabindex') === '0',
      ).toBe(true);
    });
  });

  // ================================================================
  // KMHeader — axe-core + button group
  // ================================================================
  describe('KMHeader', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderWithProviders(
        <KMHeader verificationRate={0.85} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('view mode toggle buttons have aria-pressed state', () => {
      renderWithProviders(<KMHeader verificationRate={0.85} />);

      const listBtn = screen.getByRole('button', { name: /list view/i });
      const graphBtn = screen.getByRole('button', { name: /graph view/i });

      // Default view mode is 'list'
      expect(listBtn).toHaveAttribute('aria-pressed', 'true');
      expect(graphBtn).toHaveAttribute('aria-pressed', 'false');
    });

    it('button group has role="group" with aria-label', () => {
      renderWithProviders(<KMHeader verificationRate={0.85} />);

      const group = screen.getByRole('group');
      expect(group).toHaveAttribute('aria-label', 'Knowledge Model');
    });
  });

  // ================================================================
  // AccessibleRelationshipList — axe-core + list semantics
  // ================================================================
  describe('AccessibleRelationshipList', () => {
    it('has no accessibility violations with relationships', async () => {
      const elements: KnowledgeElementResponse[] = [
        makeElement({ id: 'e1', name: 'Element A', relations: [{ target_id: 'e2', type: 'depends_on', description: null }] }),
        makeElement({ id: 'e2', name: 'Element B', relations: [] }),
      ];

      const { container } = renderWithProviders(
        <AccessibleRelationshipList elements={elements} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('has no accessibility violations with empty relationships', async () => {
      const elements: KnowledgeElementResponse[] = [
        makeElement({ id: 'e1', relations: [] }),
      ];

      const { container } = renderWithProviders(
        <AccessibleRelationshipList elements={elements} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('renders relationships as a semantic list', () => {
      const elements: KnowledgeElementResponse[] = [
        makeElement({ id: 'e1', name: 'Source', relations: [{ target_id: 'e2', type: 'constrains', description: null }] }),
        makeElement({ id: 'e2', name: 'Target', relations: [] }),
      ];

      renderWithProviders(<AccessibleRelationshipList elements={elements} />);

      const list = screen.getByRole('list');
      expect(list).toBeInTheDocument();

      const items = screen.getAllByRole('listitem');
      expect(items.length).toBeGreaterThan(0);
    });

    it('element names in list items are keyboard-navigable', () => {
      const elements: KnowledgeElementResponse[] = [
        makeElement({ id: 'e1', name: 'Source', relations: [{ target_id: 'e2', type: 'depends_on', description: null }] }),
        makeElement({ id: 'e2', name: 'Target', relations: [] }),
      ];

      renderWithProviders(<AccessibleRelationshipList elements={elements} />);

      const sourceButton = screen.getByLabelText('Source');
      const targetButton = screen.getByLabelText('Target');

      expect(sourceButton).toHaveAttribute('tabindex', '0');
      expect(targetButton).toHaveAttribute('tabindex', '0');
    });

    it('clicking element name triggers navigation', () => {
      const elements: KnowledgeElementResponse[] = [
        makeElement({ id: 'e1', name: 'Source', relations: [{ target_id: 'e2', type: 'depends_on', description: null }] }),
        makeElement({ id: 'e2', name: 'Target', relations: [] }),
      ];

      // Select e1 first so navigateToElement pushes to history
      useKnowledgeModelStore.getState().selectElement('e1');

      renderWithProviders(<AccessibleRelationshipList elements={elements} />);

      const targetButton = screen.getByLabelText('Target');
      fireEvent.click(targetButton);

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('e2');
    });
  });
});
