import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ElementDetailPanel } from '@/components/knowledge-model/ElementDetailPanel';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

// Mock window.matchMedia for the useIsMobile hook
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

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function makeElement(overrides: Partial<KnowledgeElementResponse> = {}): KnowledgeElementResponse {
  return {
    id: 'elem-1',
    type: 'concepto',
    name: 'Test Element',
    content: 'This is the full content of the element.',
    source_ref: {
      document_id: 'doc-1',
      chunk_id: 'chunk-1',
      page: 3,
      section: 'Introduction',
      evidence: 'Evidence text from the source.',
    },
    relations: [],
    verified: true,
    ...overrides,
  };
}

describe('ElementDetailPanel', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders element name as a heading', () => {
    const element = makeElement({ name: 'My Important Concept' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    const heading = screen.getByTestId('detail-panel-heading');
    expect(heading).toHaveTextContent('My Important Concept');
    expect(heading.tagName).toBe('H2');
  });

  it('renders the full element content', () => {
    const element = makeElement({ content: 'The complete description of this element with all details.' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    expect(screen.getByTestId('detail-panel-content')).toHaveTextContent(
      'The complete description of this element with all details.',
    );
  });

  it('renders the type badge', () => {
    const element = makeElement({ type: 'actor' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    expect(screen.getByText('Actors')).toBeInTheDocument();
  });

  it('renders the EvidenceSection with source_ref and verification status', () => {
    const element = makeElement({
      source_ref: {
        document_id: 'doc-1',
        chunk_id: 'chunk-1',
        page: null,
        section: 'Chapter 3',
        evidence: 'Direct quote from document.',
      },
      verified: true,
    });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    expect(screen.getByTestId('evidence-section')).toBeInTheDocument();
    expect(screen.getByText('Direct quote from document.')).toBeInTheDocument();
    expect(screen.getByText('Source Evidence')).toBeInTheDocument();
  });

  it('renders the RelatedElements section', () => {
    const relatedElement = makeElement({ id: 'elem-2', name: 'Related Actor', type: 'actor' });
    const element = makeElement({
      relations: [{ target_id: 'elem-2', type: 'depends_on', description: null }],
    });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element, relatedElement]} />,
    );

    expect(screen.getByText('Related Elements')).toBeInTheDocument();
    expect(screen.getByText('Related Actor')).toBeInTheDocument();
    expect(screen.getByText('Depends on')).toBeInTheDocument();
  });

  it('renders "No relationships identified" when element has no relations', () => {
    const element = makeElement({ relations: [] });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    expect(screen.getByText('No relationships identified')).toBeInTheDocument();
  });

  it('renders back button with correct aria-label', () => {
    const element = makeElement();

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    const backButton = screen.getByTestId('detail-panel-back');
    expect(backButton).toBeInTheDocument();
    expect(backButton).toHaveAttribute('aria-label', 'Back');
  });

  it('calls goBack() when back button is clicked', () => {
    // Setup: navigate to an element so there's history
    useKnowledgeModelStore.getState().selectElement('elem-prev');
    useKnowledgeModelStore.getState().navigateToElement('elem-1');

    const element = makeElement({ id: 'elem-1' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    fireEvent.click(screen.getByTestId('detail-panel-back'));

    // goBack should pop from history and go back to elem-prev
    expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-prev');
  });

  it('deselects when back button clicked with empty history', () => {
    useKnowledgeModelStore.getState().selectElement('elem-1');

    const element = makeElement({ id: 'elem-1' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    fireEvent.click(screen.getByTestId('detail-panel-back'));

    // goBack with empty history → deselect
    expect(useKnowledgeModelStore.getState().selectedElementId).toBeNull();
  });

  it('calls goBack() when Escape key is pressed', () => {
    useKnowledgeModelStore.getState().selectElement('elem-prev');
    useKnowledgeModelStore.getState().navigateToElement('elem-1');

    const element = makeElement({ id: 'elem-1' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    const panel = screen.getByTestId('element-detail-panel');
    fireEvent.keyDown(panel, { key: 'Escape' });

    expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-prev');
  });

  it('deselects on Escape when history is empty', () => {
    useKnowledgeModelStore.getState().selectElement('elem-1');

    const element = makeElement({ id: 'elem-1' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    const panel = screen.getByTestId('element-detail-panel');
    fireEvent.keyDown(panel, { key: 'Escape' });

    expect(useKnowledgeModelStore.getState().selectedElementId).toBeNull();
  });

  it('has role="region" with aria-label set to element name', () => {
    const element = makeElement({ name: 'Accessible Panel' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    const panel = screen.getByTestId('element-detail-panel');
    expect(panel).toHaveAttribute('role', 'region');
    expect(panel).toHaveAttribute('aria-label', 'Accessible Panel');
  });

  it('moves focus to heading when element changes', () => {
    const element = makeElement({ id: 'elem-1', name: 'First' });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    const heading = screen.getByTestId('detail-panel-heading');
    expect(document.activeElement).toBe(heading);
  });

  it('renders the panel with data-testid', () => {
    const element = makeElement();

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    expect(screen.getByTestId('element-detail-panel')).toBeInTheDocument();
  });

  it('renders verified evidence with checkmark status', () => {
    const element = makeElement({ verified: true });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    expect(screen.getByTestId('evidence-verified')).toBeInTheDocument();
  });

  it('renders not-verified evidence with warning status', () => {
    const element = makeElement({ verified: false });

    renderWithProviders(
      <ElementDetailPanel element={element} allElements={[element]} />,
    );

    expect(screen.getByTestId('evidence-not-verified')).toBeInTheDocument();
  });
});
