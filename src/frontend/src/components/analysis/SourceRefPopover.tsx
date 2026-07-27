import { useState, useCallback } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import { cn } from '@/lib/utils';
import type { SourceRef } from '@/types/analysis';

export interface SourceRefPopoverProps {
  /** The source reference to display. When null, renders an "Unverified" badge. */
  sourceRef: SourceRef | null;
}

/**
 * SourceRefPopover — shared component for displaying source evidence traceability.
 *
 * - When sourceRef is null: renders a Badge with "Unverified" text.
 * - When sourceRef is provided: renders a clickable trigger button that expands
 *   to show the text_excerpt and section context.
 *
 * Accessible: uses aria-expanded on the trigger, supports keyboard activation
 * (Enter/Space).
 *
 * Requirements: Req 9 (criteria 1-4)
 */
export function SourceRefPopover({ sourceRef }: SourceRefPopoverProps) {
  const { t } = useTranslation();

  if (sourceRef === null) {
    return (
      <Badge
        variant="outline"
        className="text-xs"
        data-testid="source-ref-unverified"
      >
        {t('analysis.sourceRef.unverified')}
      </Badge>
    );
  }

  return <ExpandableSourceRef sourceRef={sourceRef} />;
}

// --- Expandable Source Reference ---

interface ExpandableSourceRefProps {
  sourceRef: SourceRef;
}

function ExpandableSourceRef({ sourceRef }: ExpandableSourceRefProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  const toggle = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggle();
      }
    },
    [toggle],
  );

  return (
    <div className="inline-flex flex-col" data-testid="source-ref-popover">
      <Button
        variant="ghost"
        size="sm"
        className={cn(
          'text-xs h-auto py-1 px-2 font-medium text-primary',
          'hover:underline',
        )}
        onClick={toggle}
        onKeyDown={handleKeyDown}
        aria-expanded={isExpanded}
        aria-label={
          isExpanded
            ? t('analysis.sourceRef.hideSource')
            : t('analysis.sourceRef.showSource')
        }
        data-testid="source-ref-trigger"
      >
        {isExpanded
          ? t('analysis.sourceRef.hideSource')
          : t('analysis.sourceRef.showSource')}
      </Button>

      {isExpanded && (
        <div
          className="mt-2 rounded-md border border-border bg-muted/40 p-3 text-xs space-y-1.5"
          data-testid="source-ref-content"
        >
          {sourceRef.section && (
            <p className="font-medium text-muted-foreground">
              {t('analysis.sourceRef.section', { section: sourceRef.section })}
            </p>
          )}
          <p className="text-foreground whitespace-pre-wrap leading-relaxed">
            &ldquo;{sourceRef.text_excerpt}&rdquo;
          </p>
        </div>
      )}
    </div>
  );
}
