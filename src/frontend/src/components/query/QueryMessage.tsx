import { useTranslation } from '@/i18n';
import { cn } from '@/lib/utils';
import { EvidenceReference } from './EvidenceReference';
import type { Message } from '@/store/queryStore';

interface QueryMessageProps {
  message: Message;
  onNavigateToSource?: (chunkId: string) => void;
}

/**
 * Displays a question-answer pair in the query conversation.
 *
 * - User question: right-aligned bubble with distinct style
 * - System answer: left-aligned bubble with evidence references
 * - Unanswerable: informational message suggesting rephrasing
 * - Error: apologetic message without technical details
 */
export function QueryMessage({ message, onNavigateToSource }: QueryMessageProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-3" data-testid="query-message">
      {/* User question bubble */}
      <div className="flex justify-end">
        <div
          className={cn(
            'max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5',
            'bg-primary text-primary-foreground',
          )}
          data-testid="query-message-question"
        >
          <p className="text-sm">{message.question}</p>
        </div>
      </div>

      {/* System response */}
      {message.error !== null && (
        <ErrorResponse errorMessage={message.error} />
      )}

      {message.answer !== null && !message.answer.answerable && (
        <CannotAnswerResponse answerText={message.answer.answer} />
      )}

      {message.answer !== null && message.answer.answerable && (
        <AnswerResponse message={message} onNavigateToSource={onNavigateToSource} />
      )}

      {/* Loading state — answer and error both null means still loading */}
      {message.answer === null && message.error === null && (
        <div className="flex justify-start">
          <div
            className={cn(
              'max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-2.5',
              'bg-muted text-muted-foreground',
            )}
            data-testid="query-message-loading"
            aria-live="polite"
            aria-label={t('query.message.loading')}
          >
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-muted-foreground/60" />
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-muted-foreground/60 [animation-delay:150ms]" />
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-muted-foreground/60 [animation-delay:300ms]" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Renders a successful answer with evidence references.
 */
function AnswerResponse({
  message,
  onNavigateToSource,
}: {
  message: Message;
  onNavigateToSource?: (chunkId: string) => void;
}) {
  const answer = message.answer!;

  return (
    <div className="flex justify-start">
      <div
        className={cn(
          'max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-2.5',
          'bg-muted text-foreground',
        )}
        data-testid="query-message-answer"
      >
        <p className="text-sm whitespace-pre-wrap">{answer.answer}</p>

        {/* Evidence references */}
        {answer.source_refs.length > 0 && (
          <div className="mt-3 flex flex-col gap-2" data-testid="query-message-sources">
            {answer.source_refs.map((ref, index) => (
              <EvidenceReference
                key={`${ref.chunk_id}-${index}`}
                sourceRef={ref}
                onNavigate={onNavigateToSource}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Displays an informational message when the question cannot be answered.
 * Suggests the user rephrase or try a different question.
 */
function CannotAnswerResponse({ answerText }: { answerText: string }) {
  const { t } = useTranslation();

  return (
    <div className="flex justify-start">
      <div
        className={cn(
          'max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-2.5',
          'bg-blue-50 text-blue-900 border border-blue-200',
        )}
        data-testid="query-message-cannot-answer"
      >
        <p className="text-sm">{answerText}</p>
        <p className="mt-2 text-xs text-blue-700">
          {t('query.message.cannotAnswerHint')}
        </p>
      </div>
    </div>
  );
}

/**
 * Displays an apologetic error message without technical details.
 */
function ErrorResponse({ errorMessage }: { errorMessage: string }) {
  const { t } = useTranslation();

  // We display a user-friendly message; the errorMessage from the store
  // is already user-facing (classified by queryStore), but we wrap it
  // in the apologetic tone per requirements.
  return (
    <div className="flex justify-start">
      <div
        className={cn(
          'max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-2.5',
          'bg-destructive/10 text-destructive border border-destructive/20',
        )}
        data-testid="query-message-error"
        role="alert"
      >
        <p className="text-sm font-medium">{t('query.message.errorTitle')}</p>
        <p className="mt-1 text-sm">{errorMessage}</p>
        <p className="mt-2 text-xs opacity-80">
          {t('query.message.errorHint')}
        </p>
      </div>
    </div>
  );
}
