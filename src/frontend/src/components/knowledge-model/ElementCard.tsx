import { useCallback } from 'react';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import { cn } from '@/lib/utils';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

interface ElementCardProps {
  element: KnowledgeElementResponse;
  isSelected?: boolean;
}

/**
 * Truncates a description to a maximum of 120 characters or the first sentence,
 * whichever is shorter. A first sentence ends at the first period followed by
 * a space or end-of-string.
 */
function truncateDescription(content: string): string {
  if (!content) return '';

  // Find first sentence: period followed by a space or end-of-string
  const sentenceMatch = content.match(/^(.*?\.)(?:\s|$)/);
  const firstSentence = sentenceMatch ? sentenceMatch[1] : null;

  // Use whichever is shorter: first 120 chars or first sentence
  if (firstSentence && firstSentence.length <= 120) {
    return firstSentence;
  }

  if (content.length <= 120) {
    return content;
  }

  return content.slice(0, 120) + '…';
}

export function ElementCard({ element, isSelected = false }: ElementCardProps) {
  const selectElement = useKnowledgeModelStore((s) => s.selectElement);

  const handleSelect = useCallback(() => {
    selectElement(element.id);
  }, [selectElement, element.id]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        selectElement(element.id);
      }
    },
    [selectElement, element.id],
  );

  const truncated = truncateDescription(element.content);

  return (
    <div
      role="option"
      aria-selected={isSelected}
      tabIndex={0}
      onClick={handleSelect}
      onKeyDown={handleKeyDown}
      className={cn(
        'cursor-pointer rounded-md border px-4 py-3 transition-colors',
        'hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        isSelected && 'border-primary bg-accent',
      )}
      data-testid={`element-card-${element.id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-tight">{element.name}</p>
          {truncated && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {truncated}
            </p>
          )}
        </div>
        <VerificationIcon verified={element.verified} />
      </div>
    </div>
  );
}

function VerificationIcon({ verified }: { verified: boolean }) {
  const { t } = useTranslation();

  if (verified) {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="h-4 w-4 shrink-0 text-green-600"
        aria-label={t('km.element.verified')}
        role="img"
      >
        <path
          fillRule="evenodd"
          d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
          clipRule="evenodd"
        />
      </svg>
    );
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="h-4 w-4 shrink-0 text-amber-500"
      aria-label={t('km.element.notVerified')}
      role="img"
    >
      <path
        fillRule="evenodd"
        d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 5Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
        clipRule="evenodd"
      />
    </svg>
  );
}
