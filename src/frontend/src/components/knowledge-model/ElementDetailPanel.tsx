import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { EvidenceSection } from './EvidenceSection';
import { RelatedElements } from './RelatedElements';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

// --- Constants ---

const MOBILE_BREAKPOINT = 768;

// --- Props ---

interface ElementDetailPanelProps {
  element: KnowledgeElementResponse;
  allElements: KnowledgeElementResponse[];
}

// --- Hooks ---

/** Tracks whether the viewport is below the mobile breakpoint. */
function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT,
  );

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);

    const handleChange = (e: MediaQueryListEvent) => {
      setIsMobile(e.matches);
    };

    setIsMobile(mq.matches);
    mq.addEventListener('change', handleChange);
    return () => mq.removeEventListener('change', handleChange);
  }, []);

  return isMobile;
}

// --- Component ---

/**
 * Displays the full details of a selected Knowledge Element.
 * Includes the element name, type badge, content, evidence section, and related elements.
 *
 * Responsive behavior:
 * - Desktop (>=1024px): Rendered as a side panel in the right column.
 * - Tablet (768-1023px): Sliding overlay from the right.
 * - Mobile (<768px): Full-screen view with back button and aria-modal="true".
 *
 * Focus management:
 * - Moves focus to the panel heading when the element changes (panel opens or navigates).
 * - Returns focus to the previously focused element on close.
 * - Escape key calls goBack() from the store.
 */
export function ElementDetailPanel({ element, allElements }: ElementDetailPanelProps) {
  const { t } = useTranslation();
  const goBack = useKnowledgeModelStore((s) => s.goBack);
  const isMobile = useIsMobile();

  const headingRef = useRef<HTMLHeadingElement>(null);
  const triggerRef = useRef<Element | null>(null);

  // Track the trigger element (the element that had focus when this panel first mounts)
  useEffect(() => {
    triggerRef.current = document.activeElement;
  }, []);

  // Move focus to heading when element changes (panel opens or navigates to new element)
  useEffect(() => {
    headingRef.current?.focus();
  }, [element.id]);

  // Return focus to trigger on unmount (panel close)
  useEffect(() => {
    const trigger = triggerRef.current;
    return () => {
      if (trigger && trigger instanceof HTMLElement) {
        trigger.focus();
      }
    };
  }, []);

  // Escape key handler
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        goBack();
      }
    },
    [goBack],
  );

  const typeLabel = t(`km.typeGroups.${element.type}`);

  return (
    <div
      onKeyDown={handleKeyDown}
      data-testid="element-detail-panel"
      className={cn(
        // Base styles
        'flex flex-col bg-background overflow-y-auto',
        // Desktop (>=1024px): side panel in right column
        'lg:relative lg:h-full lg:border-l lg:border-border',
        // Tablet (768-1023px): sliding overlay from the right
        'max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:z-40 max-lg:w-[60%] max-lg:shadow-xl max-lg:border-l max-lg:border-border',
        // Mobile (<768px): full-screen overlay
        'max-md:w-full max-md:inset-0',
      )}
      role="region"
      aria-label={element.name}
      aria-modal={isMobile ? 'true' : undefined}
    >
      {/* Header with back button */}
      <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-background px-4 py-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={goBack}
          aria-label={t('km.navigation.back')}
          data-testid="detail-panel-back"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M17 10a.75.75 0 0 1-.75.75H5.612l4.158 3.96a.75.75 0 1 1-1.04 1.08l-5.5-5.25a.75.75 0 0 1 0-1.08l5.5-5.25a.75.75 0 1 1 1.04 1.08L5.612 9.25H16.25A.75.75 0 0 1 17 10Z"
              clipRule="evenodd"
            />
          </svg>
          <span className="md:hidden">{t('km.navigation.back')}</span>
        </Button>

        {/* Type badge */}
        <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
          {typeLabel}
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 space-y-6 px-4 py-4">
        {/* Element heading */}
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="text-lg font-semibold leading-tight outline-none"
          data-testid="detail-panel-heading"
        >
          {element.name}
        </h2>

        {/* Full description/content */}
        <div className="text-sm text-foreground leading-relaxed" data-testid="detail-panel-content">
          {element.content}
        </div>

        {/* Evidence Section */}
        <EvidenceSection sourceRef={element.source_ref} verified={element.verified} />

        {/* Related Elements */}
        <RelatedElements relations={element.relations} allElements={allElements} />
      </div>
    </div>
  );
}
