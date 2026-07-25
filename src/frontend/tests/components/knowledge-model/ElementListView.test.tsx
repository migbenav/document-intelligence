import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ElementListView } from '@/components/knowledge-model/ElementListView';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function makeElement(overrides: Partial<KnowledgeElementResponse> = {}): KnowledgeElementResponse {
  return {
    id: 'elem-1',
    type: 'concepto',
    name: 'Test Element',
    content: 'This is a test element description.',
    source_ref: {
      document_id: 'doc-1',
      chunk_id: 'chunk-1',
      page: null,
      section: 'Introduction',
      evidence: 'Some evidence text.',
    },
    relations: [],
    verified: true,
    ...overrides,
  };
}

describe('ElementListView', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders a nav element with aria-label', () => {
    renderWithProviders(<ElementListView elements={[]} />);

    const nav = screen.getByRole('navigation');
    expect(nav).toHaveAttribute('aria-label', 'Knowledge Model');
  });

  it('renders all six type groups in fixed taxonomy order', () => {
    renderWithProviders(<ElementListView elements={[]} />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings).toHaveLength(6);
    expect(headings[0]).toHaveTextContent('Purpose');
    expect(headings[1]).toHaveTextContent('Concepts');
    expect(headings[2]).toHaveTextContent('Actors');
    expect(headings[3]).toHaveTextContent('Rules');
    expect(headings[4]).toHaveTextContent('Processes');
    expect(headings[5]).toHaveTextContent('Constraints');
  });

  it('renders all six type groups even when all are empty', () => {
    renderWithProviders(<ElementListView elements={[]} />);

    expect(screen.getByTestId('type-group-proposito')).toBeInTheDocument();
    expect(screen.getByTestId('type-group-concepto')).toBeInTheDocument();
    expect(screen.getByTestId('type-group-actor')).toBeInTheDocument();
    expect(screen.getByTestId('type-group-regla')).toBeInTheDocument();
    expect(screen.getByTestId('type-group-proceso')).toBeInTheDocument();
    expect(screen.getByTestId('type-group-restriccion')).toBeInTheDocument();
  });

  it('groups elements into their correct type groups', () => {
    const elements = [
      makeElement({ id: 'e1', type: 'concepto', name: 'Concept A' }),
      makeElement({ id: 'e2', type: 'actor', name: 'Actor B' }),
      makeElement({ id: 'e3', type: 'concepto', name: 'Concept C' }),
      makeElement({ id: 'e4', type: 'regla', name: 'Rule D' }),
    ];

    renderWithProviders(<ElementListView elements={elements} />);

    // Concepts should be in the concepto group
    expect(screen.getByText('Concept A')).toBeInTheDocument();
    expect(screen.getByText('Concept C')).toBeInTheDocument();
    // Actor should be in actor group
    expect(screen.getByText('Actor B')).toBeInTheDocument();
    // Rule should be in regla group
    expect(screen.getByText('Rule D')).toBeInTheDocument();
  });

  it('passes selectedElementId from the store to TypeGroup', () => {
    const elements = [
      makeElement({ id: 'e1', type: 'concepto', name: 'Concept A' }),
      makeElement({ id: 'e2', type: 'concepto', name: 'Concept B' }),
    ];

    useKnowledgeModelStore.getState().selectElement('e2');

    renderWithProviders(<ElementListView elements={elements} />);

    const options = screen.getAllByRole('option');
    const selected = options.find(
      (opt) => opt.getAttribute('aria-selected') === 'true',
    );
    expect(selected).toBeDefined();
    expect(selected).toHaveAttribute('data-testid', 'element-card-e2');
  });

  it('has data-testid on the container', () => {
    renderWithProviders(<ElementListView elements={[]} />);

    expect(screen.getByTestId('element-list-view')).toBeInTheDocument();
  });
});
