import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { RelatedElements } from '@/components/knowledge-model/RelatedElements';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type {
  KnowledgeElementResponse,
  RelationResponse,
} from '@/types/knowledgeModel';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function makeElement(overrides: Partial<KnowledgeElementResponse> = {}): KnowledgeElementResponse {
  return {
    id: 'elem-1',
    type: 'concepto',
    name: 'Test Element',
    content: 'Test content.',
    source_ref: {
      document_id: 'doc-1',
      chunk_id: 'chunk-1',
      page: null,
      section: null,
      evidence: 'Evidence text.',
    },
    relations: [],
    verified: true,
    ...overrides,
  };
}

function makeRelation(overrides: Partial<RelationResponse> = {}): RelationResponse {
  return {
    target_id: 'elem-2',
    type: 'depends_on',
    description: null,
    ...overrides,
  };
}

describe('RelatedElements', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders the section heading', () => {
    renderWithProviders(
      <RelatedElements relations={[]} allElements={[]} />,
    );

    expect(screen.getByText('Related Elements')).toBeInTheDocument();
  });

  it('shows empty state message when no relations', () => {
    renderWithProviders(
      <RelatedElements relations={[]} allElements={[]} />,
    );

    expect(screen.getByText('No relationships identified')).toBeInTheDocument();
  });

  it('renders related element name from allElements lookup', () => {
    const target = makeElement({ id: 'elem-2', name: 'Target Element', type: 'actor' });
    const relation = makeRelation({ target_id: 'elem-2' });

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    expect(screen.getByText('Target Element')).toBeInTheDocument();
  });

  it('displays type badge for the target element', () => {
    const target = makeElement({ id: 'elem-2', name: 'My Actor', type: 'actor' });
    const relation = makeRelation({ target_id: 'elem-2' });

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    expect(screen.getByText('Actors')).toBeInTheDocument();
  });

  it('displays relationship type label', () => {
    const target = makeElement({ id: 'elem-2', name: 'Dep Element', type: 'proceso' });
    const relation = makeRelation({ target_id: 'elem-2', type: 'depends_on' });

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    expect(screen.getByText('Depends on')).toBeInTheDocument();
  });

  it('renders all relationship type labels correctly', () => {
    const elements = [
      makeElement({ id: 'e1', name: 'E1', type: 'regla' }),
      makeElement({ id: 'e2', name: 'E2', type: 'concepto' }),
      makeElement({ id: 'e3', name: 'E3', type: 'restriccion' }),
      makeElement({ id: 'e4', name: 'E4', type: 'proposito' }),
    ];
    const relations: RelationResponse[] = [
      { target_id: 'e1', type: 'constrains', description: null },
      { target_id: 'e2', type: 'participates_in', description: null },
      { target_id: 'e3', type: 'depends_on', description: null },
      { target_id: 'e4', type: 'contradicts', description: null },
    ];

    renderWithProviders(
      <RelatedElements relations={relations} allElements={elements} />,
    );

    expect(screen.getByText('Constrains')).toBeInTheDocument();
    expect(screen.getByText('Participates in')).toBeInTheDocument();
    expect(screen.getByText('Depends on')).toBeInTheDocument();
    expect(screen.getByText('Contradicts')).toBeInTheDocument();
  });

  it('falls back to target_id when element not found in allElements', () => {
    const relation = makeRelation({ target_id: 'unknown-id' });

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[]} />,
    );

    expect(screen.getByText('unknown-id')).toBeInTheDocument();
  });

  it('calls navigateToElement on click', () => {
    const target = makeElement({ id: 'elem-nav', name: 'Nav Target', type: 'regla' });
    const relation = makeRelation({ target_id: 'elem-nav' });

    // Set up a current selection so navigation history works
    useKnowledgeModelStore.getState().selectElement('current-elem');

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    fireEvent.click(screen.getByTestId('related-element-elem-nav'));

    const state = useKnowledgeModelStore.getState();
    expect(state.selectedElementId).toBe('elem-nav');
    expect(state.navigationHistory).toContain('current-elem');
  });

  it('calls navigateToElement on Enter key press', () => {
    const target = makeElement({ id: 'elem-key', name: 'Key Target', type: 'actor' });
    const relation = makeRelation({ target_id: 'elem-key' });

    useKnowledgeModelStore.getState().selectElement('current-elem');

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    fireEvent.keyDown(screen.getByTestId('related-element-elem-key'), { key: 'Enter' });

    expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-key');
  });

  it('calls navigateToElement on Space key press', () => {
    const target = makeElement({ id: 'elem-space', name: 'Space Target', type: 'proceso' });
    const relation = makeRelation({ target_id: 'elem-space' });

    useKnowledgeModelStore.getState().selectElement('current-elem');

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    fireEvent.keyDown(screen.getByTestId('related-element-elem-space'), { key: ' ' });

    expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-space');
  });

  it('each related element item is focusable (tabIndex=0)', () => {
    const target = makeElement({ id: 'elem-focus', name: 'Focus Target', type: 'concepto' });
    const relation = makeRelation({ target_id: 'elem-focus' });

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    const item = screen.getByTestId('related-element-elem-focus');
    expect(item).toHaveAttribute('tabindex', '0');
  });

  it('provides aria-label with element name, type, and relationship', () => {
    const target = makeElement({ id: 'elem-aria', name: 'Aria Target', type: 'restriccion' });
    const relation = makeRelation({ target_id: 'elem-aria', type: 'constrains' });

    renderWithProviders(
      <RelatedElements relations={[relation]} allElements={[target]} />,
    );

    const item = screen.getByTestId('related-element-elem-aria');
    expect(item).toHaveAttribute(
      'aria-label',
      'Aria Target, Constraints, Constrains',
    );
  });

  it('renders multiple relations as a list', () => {
    const elements = [
      makeElement({ id: 'e1', name: 'First', type: 'actor' }),
      makeElement({ id: 'e2', name: 'Second', type: 'regla' }),
    ];
    const relations: RelationResponse[] = [
      { target_id: 'e1', type: 'participates_in', description: null },
      { target_id: 'e2', type: 'contradicts', description: null },
    ];

    renderWithProviders(
      <RelatedElements relations={relations} allElements={elements} />,
    );

    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });
});
