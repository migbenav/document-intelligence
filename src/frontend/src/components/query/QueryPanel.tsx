import { useEffect, useRef, useCallback } from 'react';
import { useTranslation } from '@/i18n';
import { useQueryStore } from '@/store/queryStore';
import { QueryInput } from './QueryInput';
import { QueryMessage } from './QueryMessage';

export interface QueryPanelProps {
  /** The document ID to query against. */
  documentId: string;
  /** Whether the Knowledge Model extraction has completed for this document. */
  isKmCompleted: boolean;
}

/**
 * QueryPanel is the main container for the natural language query chat interface.
 *
 * Responsibilities:
 * - Renders a scrollable list of QueryMessage components (conversation history).
 * - Renders the QueryInput at the bottom for submitting new questions.
 * - Connects to the Zustand query store for state management.
 * - Shows a loading indicator with ARIA live region announcements while processing.
 * - Displays a timeout message if no response within 30 seconds.
 * - Clears the conversation on component unmount (page navigation/refresh).
 * - Only renders when the document has a completed Knowledge Model.
 * - Auto-scrolls to the bottom when new messages arrive.
 *
 * Accessibility:
 * - ARIA live region announces loading state changes to screen readers.
 * - Keyboard navigable via standard tab order.
 * - Semantic structure with appropriate roles and labels.
 */
export function QueryPanel({ documentId, isKmCompleted }: QueryPanelProps) {
  const { t } = useTranslation();
  const messages = useQueryStore((s) => s.messages);
  const isLoading = useQueryStore((s) => s.isLoading);
  const submitQuery = useQueryStore((s) => s.submitQuery);
  const clearMessages = useQueryStore((s) => s.clearMessages);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Clear messages on unmount (page lifecycle cleanup)
  useEffect(() => {
    return () => {
      clearMessages();
    };
  }, [clearMessages]);

  // Auto-scroll to bottom when new messages arrive or loading state changes
  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  const handleSubmit = useCallback(
    (question: string) => {
      void submitQuery(documentId, question);
    },
    [documentId, submitQuery],
  );

  // Don't render if KM is not completed
  if (!isKmCompleted) {
    return null;
  }

  return (
    <div
      className="flex h-full flex-col rounded-lg border bg-background"
      data-testid="query-panel"
      role="region"
      aria-label={t('query.panel.ariaLabel')}
    >
      {/* Scrollable message area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4"
        data-testid="query-panel-messages"
      >
        {messages.length === 0 && (
          <div
            className="flex h-full items-center justify-center text-sm text-muted-foreground"
            data-testid="query-panel-empty"
          >
            <p>{t('query.panel.emptyState')}</p>
          </div>
        )}

        {messages.length > 0 && (
          <div className="flex flex-col gap-4">
            {messages.map((message, index) => (
              <QueryMessage key={index} message={message} />
            ))}
          </div>
        )}

        {/* Scroll anchor */}
        <div ref={messagesEndRef} />
      </div>

      {/* ARIA live region for loading state announcements */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="query-panel-status"
      >
        {isLoading ? t('query.panel.loading') : ''}
      </div>

      {/* Input area at the bottom */}
      <div className="border-t p-4" data-testid="query-panel-input-area">
        <QueryInput onSubmit={handleSubmit} isLoading={isLoading} />
      </div>
    </div>
  );
}
