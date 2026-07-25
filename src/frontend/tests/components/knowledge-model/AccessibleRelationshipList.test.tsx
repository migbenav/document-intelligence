import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { AccessibleRelationshipList } from '@/components/knowledge-model/AccessibleRelationshipList';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

function renderComponent(elements: KnowledgeElementResponse[]) {
  return render(
    <TranslationProvider locale="en">
      <AccessibleRelationshipList elements={elements} />
    </TranslationProvider>,
  );
}

function createTestElement(
  overrides: Partial<KnowledgeElementResponse> = {},
): KnowledgeElementResponse {
  return {
    id: 'el-1',
    type: 'concepto',
    name: 'Test Element',
    content: 'Content of the element',
    source_ref: {
      document_id: 'doc-1',
      chunk_id: 'chunk-1',
      page: 1,
      section: 'Section A',
      evidence: 'Evidence text',
    },
    relations: [],
    verified: true,
    ...overrides,
  };
}

describe('AccessibleRelationshipList', () => {
  beforeEach(() => {
    useKnowledgeModelStore.setState({
      selectedElementId: null,
      navigationHistory: [],
    });
  });

  describe('Empty state', () => {
    it('displays no-relationships message when elements have no relations', () => {
      const elements = [
        createTestElement({ id: 'el-1', name: 'Element A', relations: [] }),
        createTestElement({ id: 'el-2', name: 'Element B', relations: [] }),
      ];

      renderComponent(elements);

      expect(screen.getByTestId('accessible-list-empty')).toBeInTheDocument();
      expect(screen.getByText(/No relationships were identified/)).toBeInTheDocument();
    });
  });

  describe('Relationship rendering', () => {
    const elements: KnowledgeElementResponse[] = [
      createTestElement({
        id: 'el-1',
        name: 'Purpose A',
        type: 'proposito',
        relations: [{ target_id: 'el-2', type: 'depends_on', description: null }],
      }),
      createTestElement({
        id: 'el-2',
        name: 'Concept B',
        type: 'concepto',
        relations: [{ target_id: 'el-1', type: 'constrains', description: null }],
      }),
    ];

    it('renders a list of relationships', () => {
      renderComponent(elements);

      expect(screen.getByTestId('accessible-relationship-list')).toBeInTheDocument();
    });

    it('displays source element name, relationship type, and target element name', () => {
      renderComponent(elements);

      // Both element names appear (possibly multiple times as source and target)
      expect(screen.getAllByText('Purpose A').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Concept B').length).toBeGreaterThanOrEqual(1);

      // Relationship type labels
      expect(screen.getByText('Depends on')).toBeInTheDocument();
      expect(screen.getByText('Constrains')).toBeInTheDocument();
    });

    it('renders correct number of relationship entries', () => {
      renderComponent(elements);

      const entries = screen.getAllByRole('listitem');
      expect(entries).toHaveLength(2);
    });
  });

  describe('Keyboard navigation', () => {
    const elements: KnowledgeElementResponse[] = [
      createTestElement({
        id: 'el-1',
        name: 'Element A',
        relations: [{ target_id: 'el-2', type: 'participates_in', description: null }],
      }),
      createTestElement({
        id: 'el-2',
        name: 'Element B',
        relations: [],
      }),
    ];

    it('element names are focusable (have tabIndex)', () => {
      renderComponent(elements);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((button) => {
        expect(button).toHaveAttribute('tabindex', '0');
      });
    });

    it('navigates to source element on Enter key', () => {
      renderComponent(elements);

      const sourceButton = screen.getByText('Element A');
      fireEvent.keyDown(sourceButton, { key: 'Enter' });

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('el-1');
    });

    it('navigates to target element on Enter key', () => {
      renderComponent(elements);

      const targetButton = screen.getByText('Element B');
      fireEvent.keyDown(targetButton, { key: 'Enter' });

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('el-2');
    });

    it('navigates to element on Space key', () => {
      renderComponent(elements);

      const sourceButton = screen.getByText('Element A');
      fireEvent.keyDown(sourceButton, { key: ' ' });

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('el-1');
    });
  });

  describe('Click navigation', () => {
    const elements: KnowledgeElementResponse[] = [
      createTestElement({
        id: 'el-1',
        name: 'Element A',
        relations: [{ target_id: 'el-2', type: 'depends_on', description: null }],
      }),
      createTestElement({
        id: 'el-2',
        name: 'Element B',
        relations: [],
      }),
    ];

    it('navigates to source element on click', () => {
      renderComponent(elements);

      fireEvent.click(screen.getByText('Element A'));

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('el-1');
    });

    it('navigates to target element on click', () => {
      renderComponent(elements);

      fireEvent.click(screen.getByText('Element B'));

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('el-2');
    });

    it('uses navigateToElement which pushes to history', () => {
      useKnowledgeModelStore.setState({ selectedElementId: 'el-1' });

      renderComponent(elements);

      fireEvent.click(screen.getByText('Element B'));

      const state = useKnowledgeModelStore.getState();
      expect(state.selectedElementId).toBe('el-2');
      expect(state.navigationHistory).toContain('el-1');
    });
  });

  describe('Accessibility', () => {
    const elements: KnowledgeElementResponse[] = [
      createTestElement({
        id: 'el-1',
        name: 'Rule X',
        relations: [{ target_id: 'el-2', type: 'contradicts', description: null }],
      }),
      createTestElement({
        id: 'el-2',
        name: 'Rule Y',
        relations: [],
      }),
    ];

    it('uses a semantic list structure', () => {
      renderComponent(elements);

      expect(screen.getByRole('list')).toBeInTheDocument();
    });

    it('element name buttons have aria-label', () => {
      renderComponent(elements);

      expect(screen.getByLabelText('Rule X')).toBeInTheDocument();
      expect(screen.getByLabelText('Rule Y')).toBeInTheDocument();
    });

    it('arrow characters are hidden from screen readers', () => {
      renderComponent(elements);

      const arrows = screen.getAllByText('→');
      arrows.forEach((arrow) => {
        expect(arrow).toHaveAttribute('aria-hidden', 'true');
      });
    });
  });
});
