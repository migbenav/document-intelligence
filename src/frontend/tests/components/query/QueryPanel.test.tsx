import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { QueryPanel } from '@/components/query/QueryPanel';
import { TranslationProvider } from '@/i18n';
import { useQueryStore } from '@/store/queryStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('QueryPanel', () => {
  beforeEach(() => {
    // Reset the store before each test
    useQueryStore.getState().clearMessages();
  });

  describe('rendering', () => {
    it('renders the panel when isKmCompleted is true', () => {
      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      expect(screen.getByTestId('query-panel')).toBeInTheDocument();
    });

    it('does not render when isKmCompleted is false', () => {
      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={false} />,
      );

      expect(screen.queryByTestId('query-panel')).not.toBeInTheDocument();
    });

    it('renders the empty state message when no messages exist', () => {
      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      expect(screen.getByTestId('query-panel-empty')).toBeInTheDocument();
      expect(screen.getByText('Ask a question about this document to get started.')).toBeInTheDocument();
    });

    it('renders the input area at the bottom', () => {
      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      expect(screen.getByTestId('query-panel-input-area')).toBeInTheDocument();
      expect(screen.getByTestId('query-input')).toBeInTheDocument();
    });

    it('has the correct ARIA label for the region', () => {
      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      const panel = screen.getByTestId('query-panel');
      expect(panel).toHaveAttribute('role', 'region');
      expect(panel).toHaveAttribute('aria-label', 'Document query chat');
    });
  });

  describe('messages display', () => {
    it('renders messages from the store', () => {
      useQueryStore.setState({
        messages: [
          {
            question: 'What is the main topic?',
            answer: {
              answer: 'The main topic is testing.',
              answerable: true,
              source_refs: [],
              all_evidence_unverified: false,
              metadata: {
                prompt_version: 'query-answering-v1',
                model_id: 'gemini/gemini-2.5-flash',
                temperature: 0.1,
                timestamp: '2026-01-01T00:00:00Z',
              },
            },
            error: null,
          },
        ],
        isLoading: false,
        error: null,
      });

      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      expect(screen.queryByTestId('query-panel-empty')).not.toBeInTheDocument();
      expect(screen.getByTestId('query-message')).toBeInTheDocument();
    });

    it('renders multiple messages', () => {
      useQueryStore.setState({
        messages: [
          {
            question: 'First question',
            answer: {
              answer: 'First answer.',
              answerable: true,
              source_refs: [],
              all_evidence_unverified: false,
              metadata: {
                prompt_version: 'query-answering-v1',
                model_id: 'model-1',
                temperature: 0.1,
                timestamp: '2026-01-01T00:00:00Z',
              },
            },
            error: null,
          },
          {
            question: 'Second question',
            answer: null,
            error: null,
          },
        ],
        isLoading: true,
        error: null,
      });

      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      const messageElements = screen.getAllByTestId('query-message');
      expect(messageElements).toHaveLength(2);
    });
  });

  describe('loading state', () => {
    it('announces loading state in ARIA live region', () => {
      useQueryStore.setState({
        messages: [{ question: 'Test?', answer: null, error: null }],
        isLoading: true,
        error: null,
      });

      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      const statusRegion = screen.getByTestId('query-panel-status');
      expect(statusRegion).toHaveAttribute('aria-live', 'polite');
      expect(statusRegion).toHaveTextContent('Processing your question, please wait.');
    });

    it('clears ARIA live region when not loading', () => {
      useQueryStore.setState({
        messages: [],
        isLoading: false,
        error: null,
      });

      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      const statusRegion = screen.getByTestId('query-panel-status');
      expect(statusRegion).toHaveTextContent('');
    });
  });

  describe('submit interaction', () => {
    it('calls submitQuery with documentId and question on submit', async () => {
      const user = userEvent.setup();
      const submitQueryMock = vi.fn();

      useQueryStore.setState({
        messages: [],
        isLoading: false,
        error: null,
        submitQuery: submitQueryMock,
      });

      renderWithProviders(
        <QueryPanel documentId="doc-42" isKmCompleted={true} />,
      );

      const input = screen.getByTestId('query-input-field');
      await user.type(input, 'What are the actors?');
      await user.click(screen.getByTestId('query-input-submit'));

      expect(submitQueryMock).toHaveBeenCalledWith('doc-42', 'What are the actors?');
    });
  });

  describe('unmount cleanup', () => {
    it('calls clearMessages on unmount', () => {
      const clearMessagesMock = vi.fn();

      useQueryStore.setState({
        messages: [
          {
            question: 'Leftover question',
            answer: null,
            error: null,
          },
        ],
        isLoading: false,
        error: null,
        clearMessages: clearMessagesMock,
      });

      const { unmount } = renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      unmount();

      expect(clearMessagesMock).toHaveBeenCalled();
    });
  });

  describe('accessibility', () => {
    it('has an ARIA live region for status announcements', () => {
      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      const statusRegion = screen.getByTestId('query-panel-status');
      expect(statusRegion).toHaveAttribute('aria-live', 'polite');
      expect(statusRegion).toHaveAttribute('aria-atomic', 'true');
    });

    it('has a region role with appropriate label', () => {
      renderWithProviders(
        <QueryPanel documentId="doc-1" isKmCompleted={true} />,
      );

      const region = screen.getByRole('region', { name: 'Document query chat' });
      expect(region).toBeInTheDocument();
    });
  });
});
