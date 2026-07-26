import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryMessage } from '@/components/query/QueryMessage';
import { TranslationProvider } from '@/i18n';
import type { Message } from '@/store/queryStore';

function renderWithProviders(message: Message, onNavigateToSource?: (chunkId: string) => void) {
  return render(
    <TranslationProvider locale="en">
      <QueryMessage message={message} onNavigateToSource={onNavigateToSource} />
    </TranslationProvider>,
  );
}

describe('QueryMessage', () => {
  describe('user question display', () => {
    it('renders the user question text', () => {
      const message: Message = {
        question: 'What are the main actors?',
        answer: null,
        error: null,
      };

      renderWithProviders(message);

      expect(screen.getByTestId('query-message-question')).toHaveTextContent(
        'What are the main actors?',
      );
    });

    it('always renders the question regardless of answer state', () => {
      const message: Message = {
        question: 'My question',
        answer: {
          answer: 'The answer text',
          answerable: true,
          source_refs: [
            {
              document_id: 'doc-1',
              chunk_id: 'chunk-1',
              page: null,
              section: null,
              evidence: 'Some evidence',
              evidence_verified: true,
            },
          ],
          all_evidence_unverified: false,
          metadata: {
            prompt_version: 'query-answering-v1',
            model_id: 'gemini/gemini-2.5-flash',
            temperature: 0.1,
            timestamp: '2026-01-01T00:00:00Z',
          },
        },
        error: null,
      };

      renderWithProviders(message);

      expect(screen.getByTestId('query-message-question')).toHaveTextContent('My question');
    });
  });

  describe('loading state', () => {
    it('shows loading indicator when answer and error are both null', () => {
      const message: Message = {
        question: 'A question',
        answer: null,
        error: null,
      };

      renderWithProviders(message);

      expect(screen.getByTestId('query-message-loading')).toBeInTheDocument();
    });

    it('does not show loading when answer is present', () => {
      const message: Message = {
        question: 'A question',
        answer: {
          answer: 'An answer',
          answerable: true,
          source_refs: [
            {
              document_id: 'doc-1',
              chunk_id: 'chunk-1',
              page: null,
              section: null,
              evidence: 'ev',
              evidence_verified: true,
            },
          ],
          all_evidence_unverified: false,
          metadata: {
            prompt_version: 'v1',
            model_id: 'm1',
            temperature: 0.1,
            timestamp: '2026-01-01T00:00:00Z',
          },
        },
        error: null,
      };

      renderWithProviders(message);

      expect(screen.queryByTestId('query-message-loading')).not.toBeInTheDocument();
    });
  });

  describe('answerable response', () => {
    it('renders answer text when answerable is true', () => {
      const message: Message = {
        question: 'What is X?',
        answer: {
          answer: 'X is a concept that represents...',
          answerable: true,
          source_refs: [
            {
              document_id: 'doc-1',
              chunk_id: 'chunk-5',
              page: 2,
              section: '## Overview',
              evidence: 'X is defined as a concept',
              evidence_verified: true,
            },
          ],
          all_evidence_unverified: false,
          metadata: {
            prompt_version: 'query-answering-v1',
            model_id: 'gemini/gemini-2.5-flash',
            temperature: 0.1,
            timestamp: '2026-01-01T00:00:00Z',
          },
        },
        error: null,
      };

      renderWithProviders(message);

      expect(screen.getByTestId('query-message-answer')).toHaveTextContent(
        'X is a concept that represents...',
      );
    });

    it('renders EvidenceReference components for each source_ref', () => {
      const message: Message = {
        question: 'Tell me about actors',
        answer: {
          answer: 'There are two actors...',
          answerable: true,
          source_refs: [
            {
              document_id: 'doc-1',
              chunk_id: 'chunk-1',
              page: null,
              section: '## Actors',
              evidence: 'First actor evidence',
              evidence_verified: true,
            },
            {
              document_id: 'doc-1',
              chunk_id: 'chunk-2',
              page: null,
              section: '## Actors',
              evidence: 'Second actor evidence',
              evidence_verified: false,
            },
          ],
          all_evidence_unverified: false,
          metadata: {
            prompt_version: 'v1',
            model_id: 'm1',
            temperature: 0.1,
            timestamp: '2026-01-01T00:00:00Z',
          },
        },
        error: null,
      };

      renderWithProviders(message);

      const sources = screen.getByTestId('query-message-sources');
      expect(sources).toBeInTheDocument();

      const evidenceRefs = screen.getAllByTestId('evidence-reference');
      expect(evidenceRefs).toHaveLength(2);
    });

    it('calls onNavigateToSource when evidence reference is clicked', () => {
      const onNavigate = vi.fn();
      const message: Message = {
        question: 'Q',
        answer: {
          answer: 'A',
          answerable: true,
          source_refs: [
            {
              document_id: 'doc-1',
              chunk_id: 'chunk-42',
              page: null,
              section: null,
              evidence: 'Some evidence text',
              evidence_verified: true,
            },
          ],
          all_evidence_unverified: false,
          metadata: {
            prompt_version: 'v1',
            model_id: 'm1',
            temperature: 0.1,
            timestamp: '2026-01-01T00:00:00Z',
          },
        },
        error: null,
      };

      renderWithProviders(message, onNavigate);

      const ref = screen.getByTestId('evidence-reference');
      ref.click();

      expect(onNavigate).toHaveBeenCalledWith('chunk-42');
    });
  });

  describe('cannot answer response', () => {
    it('renders informational message when answerable is false', () => {
      const message: Message = {
        question: 'What about deployment?',
        answer: {
          answer: 'The available knowledge does not contain information about deployment.',
          answerable: false,
          source_refs: [],
          all_evidence_unverified: false,
          metadata: {
            prompt_version: 'v1',
            model_id: 'm1',
            temperature: 0.1,
            timestamp: '2026-01-01T00:00:00Z',
          },
        },
        error: null,
      };

      renderWithProviders(message);

      const cannotAnswer = screen.getByTestId('query-message-cannot-answer');
      expect(cannotAnswer).toBeInTheDocument();
      expect(cannotAnswer).toHaveTextContent(
        'The available knowledge does not contain information about deployment.',
      );
      // Should include rephrasing hint
      expect(cannotAnswer).toHaveTextContent('Try rephrasing');
    });

    it('does not render answer bubble when answerable is false', () => {
      const message: Message = {
        question: 'Q',
        answer: {
          answer: 'Cannot answer this.',
          answerable: false,
          source_refs: [],
          all_evidence_unverified: false,
          metadata: {
            prompt_version: 'v1',
            model_id: 'm1',
            temperature: 0.1,
            timestamp: '2026-01-01T00:00:00Z',
          },
        },
        error: null,
      };

      renderWithProviders(message);

      expect(screen.queryByTestId('query-message-answer')).not.toBeInTheDocument();
    });
  });

  describe('error response', () => {
    it('renders error message with apologetic tone', () => {
      const message: Message = {
        question: 'What is this about?',
        answer: null,
        error: 'An error occurred while processing your question. Please try again later.',
      };

      renderWithProviders(message);

      const errorEl = screen.getByTestId('query-message-error');
      expect(errorEl).toBeInTheDocument();
      // Should show apologetic title
      expect(errorEl).toHaveTextContent('Something went wrong');
      // Should show the error message text
      expect(errorEl).toHaveTextContent('An error occurred while processing your question');
      // Should suggest trying again later
      expect(errorEl).toHaveTextContent('Please try again later');
    });

    it('has role="alert" for accessibility', () => {
      const message: Message = {
        question: 'Q',
        answer: null,
        error: 'Server error',
      };

      renderWithProviders(message);

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('does not show loading when error is present', () => {
      const message: Message = {
        question: 'Q',
        answer: null,
        error: 'Some error',
      };

      renderWithProviders(message);

      expect(screen.queryByTestId('query-message-loading')).not.toBeInTheDocument();
    });
  });
});
