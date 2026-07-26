import { useState, useCallback, useRef } from 'react';
import { useTranslation } from '@/i18n';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

const MAX_CHARS = 1000;

export interface QueryInputProps {
  /** Called with the question text when the user submits. */
  onSubmit: (question: string) => void;
  /** Whether a query is currently being processed. */
  isLoading: boolean;
  /** Optional flag to fully disable the input. */
  disabled?: boolean;
}

/**
 * Send icon for the submit button.
 */
function SendIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path d="M3.105 2.288a.75.75 0 0 0-.826.95l1.414 4.926A1.5 1.5 0 0 0 5.135 9.25h6.115a.75.75 0 0 1 0 1.5H5.135a1.5 1.5 0 0 0-1.442 1.086l-1.414 4.926a.75.75 0 0 0 .826.95l14.095-5.638a.75.75 0 0 0 0-1.392L3.105 2.289Z" />
    </svg>
  );
}

/**
 * QueryInput provides a text input with character counter and submit button.
 *
 * Accessibility:
 * - Uses a <textarea> with an associated <label> for screen readers
 * - Character counter linked via aria-describedby
 * - Enter key submits, Shift+Enter inserts newline
 * - Submit button disabled when: empty, >1000 chars, loading, or externally disabled
 * - WCAG 2.1 AA compliant focus indicators
 */
export function QueryInput({ onSubmit, isLoading, disabled = false }: QueryInputProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const charCount = value.length;
  const isOverLimit = charCount > MAX_CHARS;
  const isEmpty = value.trim().length === 0;
  const isSubmitDisabled = isEmpty || isOverLimit || isLoading || disabled;

  const handleSubmit = useCallback(() => {
    if (isSubmitDisabled) return;
    const trimmed = value.trim();
    if (trimmed.length === 0) return;
    onSubmit(trimmed);
    setValue('');
  }, [value, isSubmitDisabled, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
  }, []);

  return (
    <div className="flex flex-col gap-1.5" data-testid="query-input">
      <label htmlFor="query-input-field" className="sr-only">
        {t('query.input.label')}
      </label>

      <div className="relative flex items-end gap-2">
        <textarea
          id="query-input-field"
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={t('query.input.placeholder')}
          disabled={disabled}
          rows={1}
          aria-describedby="query-char-counter"
          aria-invalid={isOverLimit}
          className={cn(
            'flex-1 resize-none rounded-lg border bg-background px-3 py-2.5 text-sm',
            'placeholder:text-muted-foreground',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            'disabled:cursor-not-allowed disabled:opacity-50',
            'min-h-[40px] max-h-[120px]',
            isOverLimit
              ? 'border-destructive focus-visible:ring-destructive'
              : 'border-input',
          )}
          data-testid="query-input-field"
        />

        <Button
          type="button"
          size="icon"
          onClick={handleSubmit}
          disabled={isSubmitDisabled}
          aria-label={t('query.input.submit')}
          data-testid="query-input-submit"
        >
          <SendIcon />
        </Button>
      </div>

      {/* Character counter */}
      <div
        id="query-char-counter"
        className={cn(
          'text-xs tabular-nums',
          isOverLimit ? 'text-destructive font-medium' : 'text-muted-foreground',
        )}
        aria-live="polite"
        aria-atomic="true"
        data-testid="query-char-counter"
      >
        {t('query.input.charCounter', {
          current: String(charCount),
          max: String(MAX_CHARS),
        })}
      </div>
    </div>
  );
}
