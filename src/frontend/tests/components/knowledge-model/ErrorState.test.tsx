import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ErrorState } from '@/components/knowledge-model/ErrorState';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('ErrorState', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders the error message passed as prop', () => {
    renderWithProviders(
      <ErrorState message="Unable to reach the server." documentId="doc-1" />,
    );

    expect(screen.getByText('Unable to reach the server.')).toBeInTheDocument();
  });

  it('renders in a destructive alert', () => {
    renderWithProviders(
      <ErrorState message="Document not found." documentId="doc-1" />,
    );

    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
  });

  it('renders a retry button with i18n text', () => {
    renderWithProviders(
      <ErrorState message="Network error." documentId="doc-1" />,
    );

    const retryButton = screen.getByTestId('km-retry-button');
    expect(retryButton).toBeInTheDocument();
    expect(retryButton).toHaveTextContent('Try again');
  });

  it('calls fetchKnowledgeModel with documentId on retry click', () => {
    const mockFetch = vi.fn().mockResolvedValue(undefined);
    useKnowledgeModelStore.setState({ fetchKnowledgeModel: mockFetch });

    renderWithProviders(
      <ErrorState message="Network error." documentId="doc-123" />,
    );

    fireEvent.click(screen.getByTestId('km-retry-button'));

    expect(mockFetch).toHaveBeenCalledWith('doc-123');
  });

  it('renders with the test id', () => {
    renderWithProviders(
      <ErrorState message="Error occurred." documentId="doc-1" />,
    );

    expect(screen.getByTestId('km-error-state')).toBeInTheDocument();
  });

  it('displays the error message in the designated element', () => {
    renderWithProviders(
      <ErrorState message="Analysis is not yet completed." documentId="doc-1" />,
    );

    const messageEl = screen.getByTestId('km-error-message');
    expect(messageEl).toHaveTextContent('Analysis is not yet completed.');
  });
});
