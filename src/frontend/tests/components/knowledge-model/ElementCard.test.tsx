import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ElementCard } from '@/components/knowledge-model/ElementCard';
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

describe('ElementCard', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders element name', () => {
    const element = makeElement({ name: 'My Concept' });

    renderWithProviders(<ElementCard element={element} />);

    expect(screen.getByText('My Concept')).toBeInTheDocument();
  });

  it('renders truncated description (first sentence if shorter than 120 chars)', () => {
    const element = makeElement({
      content: 'This is the first sentence. This is the second sentence that should not appear.',
    });

    renderWithProviders(<ElementCard element={element} />);

    expect(screen.getByText('This is the first sentence.')).toBeInTheDocument();
    expect(screen.queryByText(/second sentence/)).not.toBeInTheDocument();
  });

  it('truncates description at 120 characters when no sentence boundary is shorter', () => {
    const longContent = 'A'.repeat(200);
    const element = makeElement({ content: longContent });

    renderWithProviders(<ElementCard element={element} />);

    const descriptionEl = screen.getByText(/A+…$/);
    expect(descriptionEl.textContent).toBe('A'.repeat(120) + '…');
  });

  it('shows full content when shorter than 120 chars and no sentence boundary', () => {
    const element = makeElement({ content: 'Short content without a period' });

    renderWithProviders(<ElementCard element={element} />);

    expect(screen.getByText('Short content without a period')).toBeInTheDocument();
  });

  it('displays checkmark icon with correct aria-label when verified', () => {
    const element = makeElement({ verified: true });

    renderWithProviders(<ElementCard element={element} />);

    const icon = screen.getByLabelText('Verified: evidence confirmed in source document');
    expect(icon).toBeInTheDocument();
  });

  it('displays warning triangle icon with correct aria-label when not verified', () => {
    const element = makeElement({ verified: false });

    renderWithProviders(<ElementCard element={element} />);

    const icon = screen.getByLabelText('Not verified: evidence not found in source document');
    expect(icon).toBeInTheDocument();
  });

  it('has role="option" for listbox accessibility', () => {
    const element = makeElement();

    renderWithProviders(<ElementCard element={element} />);

    expect(screen.getByRole('option')).toBeInTheDocument();
  });

  it('sets aria-selected=true when isSelected is true', () => {
    const element = makeElement();

    renderWithProviders(<ElementCard element={element} isSelected={true} />);

    expect(screen.getByRole('option')).toHaveAttribute('aria-selected', 'true');
  });

  it('sets aria-selected=false when isSelected is false', () => {
    const element = makeElement();

    renderWithProviders(<ElementCard element={element} isSelected={false} />);

    expect(screen.getByRole('option')).toHaveAttribute('aria-selected', 'false');
  });

  it('calls selectElement on click', () => {
    const element = makeElement({ id: 'elem-42' });

    renderWithProviders(<ElementCard element={element} />);

    fireEvent.click(screen.getByRole('option'));

    expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-42');
  });

  it('calls selectElement on Enter key press', () => {
    const element = makeElement({ id: 'elem-99' });

    renderWithProviders(<ElementCard element={element} />);

    fireEvent.keyDown(screen.getByRole('option'), { key: 'Enter' });

    expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-99');
  });

  it('calls selectElement on Space key press', () => {
    const element = makeElement({ id: 'elem-77' });

    renderWithProviders(<ElementCard element={element} />);

    fireEvent.keyDown(screen.getByRole('option'), { key: ' ' });

    expect(useKnowledgeModelStore.getState().selectedElementId).toBe('elem-77');
  });

  it('renders empty description gracefully when content is empty', () => {
    const element = makeElement({ content: '' });

    const { container } = renderWithProviders(<ElementCard element={element} />);

    // Name should still render
    expect(screen.getByText('Test Element')).toBeInTheDocument();
    // No description paragraph should be rendered
    expect(container.querySelector('.text-muted-foreground.text-xs')).not.toBeInTheDocument();
  });
});
