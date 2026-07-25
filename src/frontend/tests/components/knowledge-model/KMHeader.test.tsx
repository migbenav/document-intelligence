import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { KMHeader } from '@/components/knowledge-model/KMHeader';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('KMHeader', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders the page title from i18n', () => {
    renderWithProviders(<KMHeader verificationRate={0.85} />);

    expect(screen.getByText('Knowledge Model')).toBeInTheDocument();
  });

  it('displays verification rate as a rounded percentage', () => {
    renderWithProviders(<KMHeader verificationRate={0.85} />);

    expect(screen.getByText('85% of elements verified')).toBeInTheDocument();
  });

  it('rounds verification rate correctly (0.856 → 86%)', () => {
    renderWithProviders(<KMHeader verificationRate={0.856} />);

    expect(screen.getByText('86% of elements verified')).toBeInTheDocument();
  });

  it('handles 0% verification rate', () => {
    renderWithProviders(<KMHeader verificationRate={0} />);

    expect(screen.getByText('0% of elements verified')).toBeInTheDocument();
  });

  it('handles 100% verification rate', () => {
    renderWithProviders(<KMHeader verificationRate={1} />);

    expect(screen.getByText('100% of elements verified')).toBeInTheDocument();
  });

  it('renders list and graph view toggle buttons', () => {
    renderWithProviders(<KMHeader verificationRate={0.85} />);

    expect(screen.getByText('List view')).toBeInTheDocument();
    expect(screen.getByText('Graph view')).toBeInTheDocument();
  });

  it('indicates list view as active by default', () => {
    renderWithProviders(<KMHeader verificationRate={0.85} />);

    const listButton = screen.getByText('List view').closest('button')!;
    expect(listButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('indicates graph view as inactive by default', () => {
    renderWithProviders(<KMHeader verificationRate={0.85} />);

    const graphButton = screen.getByText('Graph view').closest('button')!;
    expect(graphButton).toHaveAttribute('aria-pressed', 'false');
  });

  it('calls setViewMode("graph") when graph button is clicked', () => {
    renderWithProviders(<KMHeader verificationRate={0.85} />);

    fireEvent.click(screen.getByText('Graph view'));

    expect(useKnowledgeModelStore.getState().viewMode).toBe('graph');
  });

  it('calls setViewMode("list") when list button is clicked', () => {
    // Set view mode to graph first
    useKnowledgeModelStore.getState().setViewMode('graph');

    renderWithProviders(<KMHeader verificationRate={0.85} />);

    fireEvent.click(screen.getByText('List view'));

    expect(useKnowledgeModelStore.getState().viewMode).toBe('list');
  });

  it('updates active button state when view mode changes', () => {
    useKnowledgeModelStore.getState().setViewMode('graph');

    renderWithProviders(<KMHeader verificationRate={0.85} />);

    const graphButton = screen.getByText('Graph view').closest('button')!;
    const listButton = screen.getByText('List view').closest('button')!;

    expect(graphButton).toHaveAttribute('aria-pressed', 'true');
    expect(listButton).toHaveAttribute('aria-pressed', 'false');
  });

  it('has a role="group" container for toggle buttons', () => {
    renderWithProviders(<KMHeader verificationRate={0.85} />);

    expect(screen.getByRole('group')).toBeInTheDocument();
  });
});
