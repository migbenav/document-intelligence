import { useState, useCallback } from 'react';
import { useTranslation } from '@/i18n';
import { cn } from '@/lib/utils';
import { VerificationBadge } from './VerificationBadge';
import type { QuerySourceRef } from '@/store/queryStore';

const EVIDENCE_TRUNCATE_LENGTH = 200;

interface EvidenceReferenceProps {
  sourceRef: QuerySourceRef;
  onNavigate?: (chunkId: string) => void;
}

/**
 * Displays a single evidence reference from a query response.
 *
 * - Shows evidence text truncated to 200 chars with expand/collapse toggle
 * - Shows section and/or page reference when available
 * - Includes a VerificationBadge for verification status
 * - Clickable — calls onNavigate with the chunk_id
 * - Keyboard focusable and activatable (Enter/Space)
 * - Accessible with ARIA attributes
 */
export function EvidenceReference({ sourceRef, onNavigate }: EvidenceReferenceProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  const evidenceText = sourceRef.evidence;
  const needsTruncation = evidenceText.length > EVIDENCE_TRUNCATE_LENGTH;
  const displayText =
    needsTruncation && !isExpanded
      ? evidenceText.slice(0, EVIDENCE_TRUNCATE_LENGTH) + '…'
      : evidenceText;

  const handleNavigate = useCallback(() => {
    onNavigate?.(sourceRef.chunk_id);
  }, [onNavigate, sourceRef.chunk_id]);

  const handleToggleExpand = useCallback(
    (e: React.MouseEvent | React.KeyboardEvent) => {
      e.stopPropagation();
      setIsExpanded((prev) => !prev);
    },
    [],
  );

  const handleToggleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        e.stopPropagation();
        setIsExpanded((prev) => !prev);
      }
    },
    [],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleNavigate();
      }
    },
    [handleNavigate],
  );

  return (
    <button
      type="button"
      onClick={handleNavigate}
      onKeyDown={handleKeyDown}
      className={cn(
        'w-full rounded-md border border-border bg-muted/30 px-3 py-2 text-left',
        'transition-colors hover:bg-accent/50',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
        'cursor-pointer',
      )}
      aria-label={t('query.evidence.navigateToSource')}
      data-testid="evidence-reference"
    >
      {/* Evidence text */}
      <p className="text-sm text-foreground" data-testid="evidence-text">
        {displayText}
      </p>

      {/* Show more/less toggle */}
      {needsTruncation && (
        <span
          role="button"
          tabIndex={0}
          onClick={handleToggleExpand}
          onKeyDown={handleToggleKeyDown}
          className={cn(
            'mt-1 inline-block text-xs font-medium text-primary',
            'hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm',
          )}
          aria-expanded={isExpanded}
          data-testid="evidence-toggle"
        >
          {isExpanded ? t('query.evidence.showLess') : t('query.evidence.showMore')}
        </span>
      )}

      {/* Metadata: section and/or page */}
      <EvidenceMetadata sourceRef={sourceRef} />

      {/* Verification badge */}
      <div className="mt-1.5">
        <VerificationBadge verified={sourceRef.evidence_verified} />
      </div>
    </button>
  );
}

function EvidenceMetadata({ sourceRef }: { sourceRef: QuerySourceRef }) {
  const { t } = useTranslation();

  const hasSection = sourceRef.section !== null && sourceRef.section !== '';
  const hasPage = sourceRef.page !== null;

  if (!hasSection && !hasPage) {
    return null;
  }

  return (
    <p
      className="mt-1 text-xs text-muted-foreground"
      data-testid="evidence-metadata"
    >
      {hasSection && (
        <span>{t('query.evidence.section', { section: sourceRef.section! })}</span>
      )}
      {hasSection && hasPage && <span className="mx-1">&middot;</span>}
      {hasPage && (
        <span>{t('query.evidence.page', { page: String(sourceRef.page!) })}</span>
      )}
    </p>
  );
}
