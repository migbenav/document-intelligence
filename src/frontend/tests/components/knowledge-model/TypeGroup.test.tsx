import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { TypeGroup } from '@/components/knowledge-model/TypeGroup';
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

describe('TypeGroup', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders the type name from i18n as a heading', () => {
    renderWithProviders(
      <TypeGroup type="concepto" elements={[]} selectedElementId={null} />,
    );

    const heading = screen.getByRole('heading', { level: 3 });
    expect(heading).toHaveTextContent('Concepts');
  });

  it('renders element count badge when elements are present', () => {
    const elements = [
      makeElement({ id: 'elem-1', name: 'First' }),
      makeElement({ id: 'elem-2', name: 'Second' }),
    ];

    renderWithProviders(
      <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
    );

    expect(screen.getByText('2 elements')).toBeInTheDocument();
  });

  it('renders "No elements" badge when count is zero', () => {
    renderWithProviders(
      <TypeGroup type="actor" elements={[]} selectedElementId={null} />,
    );

    // Badge shows "No elements"
    expect(screen.getAllByText('No elements').length).toBeGreaterThan(0);
  });

  it('renders empty state indicator when no elements', () => {
    renderWithProviders(
      <TypeGroup type="regla" elements={[]} selectedElementId={null} />,
    );

    // The content area shows the "No elements" text
    expect(screen.getAllByText('No elements').length).toBeGreaterThan(0);
  });

  it('renders ElementCard for each element in the group', () => {
    const elements = [
      makeElement({ id: 'elem-1', name: 'Alpha' }),
      makeElement({ id: 'elem-2', name: 'Beta' }),
      makeElement({ id: 'elem-3', name: 'Gamma' }),
    ];

    renderWithProviders(
      <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
    );

    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByText('Gamma')).toBeInTheDocument();
  });

  it('passes selectedElementId to ElementCard for highlight', () => {
    const elements = [
      makeElement({ id: 'elem-1', name: 'Alpha' }),
      makeElement({ id: 'elem-2', name: 'Beta' }),
    ];

    renderWithProviders(
      <TypeGroup type="concepto" elements={elements} selectedElementId="elem-2" />,
    );

    const options = screen.getAllByRole('option');
    const selectedOption = options.find(
      (opt) => opt.getAttribute('aria-selected') === 'true',
    );
    expect(selectedOption).toBeDefined();
    expect(selectedOption).toHaveAttribute('data-testid', 'element-card-elem-2');
  });

  it('uses semantic h3 heading element', () => {
    renderWithProviders(
      <TypeGroup type="proposito" elements={[]} selectedElementId={null} />,
    );

    const heading = screen.getByRole('heading', { level: 3 });
    expect(heading).toBeInTheDocument();
    expect(heading).toHaveTextContent('Purpose');
  });

  it('collapses content when header button is clicked', () => {
    const elements = [makeElement({ id: 'elem-1', name: 'Alpha' })];

    renderWithProviders(
      <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
    );

    // Initially expanded - element should be visible
    expect(screen.getByText('Alpha')).toBeVisible();

    // Click the collapse button
    const button = screen.getByRole('button', { expanded: true });
    fireEvent.click(button);

    // After collapse, content should be hidden
    expect(screen.getByText('Alpha')).not.toBeVisible();
  });

  it('expands content when collapsed header button is clicked again', () => {
    const elements = [makeElement({ id: 'elem-1', name: 'Alpha' })];

    renderWithProviders(
      <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
    );

    const button = screen.getByRole('button');

    // Collapse
    fireEvent.click(button);
    expect(screen.getByText('Alpha')).not.toBeVisible();

    // Expand again
    fireEvent.click(button);
    expect(screen.getByText('Alpha')).toBeVisible();
  });

  it('sets aria-expanded on the toggle button', () => {
    renderWithProviders(
      <TypeGroup type="concepto" elements={[]} selectedElementId={null} />,
    );

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'false');
  });

  it('sets aria-controls on the toggle button matching content id', () => {
    renderWithProviders(
      <TypeGroup type="proceso" elements={[]} selectedElementId={null} />,
    );

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-controls', 'type-group-content-proceso');
  });

  it('renders correct type names for all taxonomy types', () => {
    const typeLabels: Record<string, string> = {
      proposito: 'Purpose',
      concepto: 'Concepts',
      actor: 'Actors',
      regla: 'Rules',
      proceso: 'Processes',
      restriccion: 'Constraints',
    };

    for (const [type, label] of Object.entries(typeLabels)) {
      const { unmount } = renderWithProviders(
        <TypeGroup
          type={type as any}
          elements={[]}
          selectedElementId={null}
        />,
      );

      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(label);
      unmount();
    }
  });

  it('has a listbox role on the content area', () => {
    const elements = [makeElement({ id: 'elem-1', name: 'Alpha' })];

    renderWithProviders(
      <TypeGroup type="concepto" elements={elements} selectedElementId={null} />,
    );

    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('has a section element with aria-labelledby pointing to the heading', () => {
    const { container } = renderWithProviders(
      <TypeGroup type="actor" elements={[]} selectedElementId={null} />,
    );

    const section = container.querySelector('section');
    expect(section).toHaveAttribute('aria-labelledby', 'type-group-heading-actor');
  });
});
