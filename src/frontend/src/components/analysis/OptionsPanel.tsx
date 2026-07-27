import { useEffect, useRef } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/i18n';
import { useAnalysisStore } from '@/store/analysisStore';
import type { AnalysisType, AnalysisStatus } from '@/types/analysis';

export interface OptionsPanelProps {
  documentId: string;
  classification: string | null;
}

/** All four analysis types in display order. */
const ALL_ANALYSIS_TYPES: AnalysisType[] = [
  'build_index',
  'section_relations',
  'questions_answered',
  'conclusions',
];

/** Types available for narrative documents. */
const NARRATIVE_ANALYSIS_TYPES: AnalysisType[] = [
  'questions_answered',
  'conclusions',
];

/**
 * Options Panel — displays available on-demand analyses below the document card.
 * Filters options based on classification and renders status-based UI per option.
 */
export function OptionsPanel({ documentId, classification }: OptionsPanelProps) {
  const { t } = useTranslation();
  const statuses = useAnalysisStore((s) => s.statuses);
  const activeAnalysis = useAnalysisStore((s) => s.activeAnalysis);
  const triggerAnalysis = useAnalysisStore((s) => s.triggerAnalysis);
  const fetchResult = useAnalysisStore((s) => s.fetchResult);
  const fetchStatuses = useAnalysisStore((s) => s.fetchStatuses);

  useEffect(() => {
    void fetchStatuses(documentId);
  }, [documentId, fetchStatuses]);

  // --- Live region announcement for status changes ---
  const liveRegionRef = useRef<HTMLSpanElement>(null);
  const prevActiveRef = useRef<AnalysisType | null>(null);

  useEffect(() => {
    const prev = prevActiveRef.current;
    prevActiveRef.current = activeAnalysis;

    // Analysis just started
    if (activeAnalysis !== null && prev === null) {
      const name = t(`analysis.types.${activeAnalysis}.name`);
      if (liveRegionRef.current) {
        liveRegionRef.current.textContent = t('analysis.liveRegion.started', { name });
      }
      return;
    }

    // Analysis just finished (activeAnalysis cleared)
    if (activeAnalysis === null && prev !== null) {
      const name = t(`analysis.types.${prev}.name`);
      const prevStatus = statuses?.[prev]?.status;
      if (prevStatus === 'failed') {
        if (liveRegionRef.current) {
          liveRegionRef.current.textContent = t('analysis.liveRegion.failed', { name });
        }
      } else {
        if (liveRegionRef.current) {
          liveRegionRef.current.textContent = t('analysis.liveRegion.completed', { name });
        }
      }
    }
  }, [activeAnalysis, statuses, t]);

  // Filter visible types based on classification
  const visibleTypes =
    classification === 'narrative' ? NARRATIVE_ANALYSIS_TYPES : ALL_ANALYSIS_TYPES;

  const getStatus = (type: AnalysisType): AnalysisStatus => {
    if (activeAnalysis === type) return 'in_progress';
    if (!statuses) return 'not_started';
    return statuses[type]?.status ?? 'not_started';
  };

  const handleTrigger = (type: AnalysisType) => {
    void triggerAnalysis(documentId, type);
  };

  const handleView = (type: AnalysisType) => {
    void fetchResult(documentId, type);
  };

  return (
    <section
      aria-label={t('analysis.panelLabel')}
      data-testid="options-panel"
      className="space-y-3"
    >
      {visibleTypes.map((type) => {
        const status = getStatus(type);
        return (
          <AnalysisOptionCard
            key={type}
            type={type}
            status={status}
            onTrigger={() => handleTrigger(type)}
            onView={() => handleView(type)}
          />
        );
      })}

      {/* Visually hidden live region for screen reader announcements */}
      <span
        ref={liveRegionRef}
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="analysis-live-region"
      />
    </section>
  );
}

// --- Internal sub-component per option ---

interface AnalysisOptionCardProps {
  type: AnalysisType;
  status: AnalysisStatus;
  onTrigger: () => void;
  onView: () => void;
}

function AnalysisOptionCard({ type, status, onTrigger, onView }: AnalysisOptionCardProps) {
  const { t } = useTranslation();

  const name = t(`analysis.types.${type}.name`);
  const description = t(`analysis.types.${type}.description`);

  return (
    <Card data-testid={`analysis-option-${type}`}>
      <CardContent className="flex items-center justify-between p-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">{name}</span>
            <StatusBadge status={status} />
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">
            {description}
          </p>
        </div>

        <div className="ml-4 flex items-center gap-2 shrink-0">
          <StatusActions
            type={type}
            status={status}
            onTrigger={onTrigger}
            onView={onView}
          />
        </div>
      </CardContent>
    </Card>
  );
}

// --- Status Badge ---

interface StatusBadgeProps {
  status: AnalysisStatus;
}

function StatusBadge({ status }: StatusBadgeProps) {
  const { t } = useTranslation();

  switch (status) {
    case 'not_started':
      return null;
    case 'in_progress':
      return (
        <Badge variant="secondary" aria-label={t('analysis.status.in_progress')}>
          <Spinner />
          <span className="ml-1">{t('analysis.status.in_progress')}</span>
        </Badge>
      );
    case 'completed':
      return (
        <Badge variant="default" aria-label={t('analysis.status.completed')}>
          {t('analysis.status.completed')}
        </Badge>
      );
    case 'outdated':
      return (
        <Badge
          variant="outline"
          className="border-yellow-500 text-yellow-700"
          aria-label={t('analysis.status.outdated')}
        >
          {t('analysis.status.outdated')}
        </Badge>
      );
    case 'failed':
      return (
        <Badge variant="destructive" aria-label={t('analysis.status.failed')}>
          {t('analysis.status.failed')}
        </Badge>
      );
    default:
      return null;
  }
}

// --- Status-based action buttons ---

interface StatusActionsProps {
  type: AnalysisType;
  status: AnalysisStatus;
  onTrigger: () => void;
  onView: () => void;
}

function StatusActions({ type, status, onTrigger, onView }: StatusActionsProps) {
  const { t } = useTranslation();
  const name = t(`analysis.types.${type}.name`);

  switch (status) {
    case 'not_started':
      return (
        <Button
          size="sm"
          onClick={onTrigger}
          aria-label={`${t('analysis.actions.analyze')} ${name}`}
          data-testid="analyze-button"
        >
          {t('analysis.actions.analyze')}
        </Button>
      );
    case 'in_progress':
      return (
        <Button
          size="sm"
          disabled
          aria-busy="true"
          aria-label={`${t('analysis.actions.analyzing')} ${name}`}
          data-testid="analyzing-button"
        >
          <Spinner />
          <span className="ml-1">{t('analysis.actions.analyzing')}</span>
        </Button>
      );
    case 'completed':
      return (
        <Button
          size="sm"
          variant="outline"
          onClick={onView}
          aria-label={`${t('analysis.actions.view')} ${name}`}
          data-testid="view-button"
        >
          {t('analysis.actions.view')}
        </Button>
      );
    case 'outdated':
      return (
        <>
          <Button
            size="sm"
            variant="outline"
            onClick={onView}
            aria-label={`${t('analysis.actions.view')} ${name}`}
            data-testid="view-button"
          >
            {t('analysis.actions.view')}
          </Button>
          <Button
            size="sm"
            onClick={onTrigger}
            aria-label={`${t('analysis.actions.reanalyze')} ${name}`}
            data-testid="reanalyze-button"
          >
            {t('analysis.actions.reanalyze')}
          </Button>
        </>
      );
    case 'failed':
      return (
        <Button
          size="sm"
          variant="destructive"
          onClick={onTrigger}
          aria-label={`${t('analysis.actions.retry')} ${name}`}
          data-testid="retry-button"
        >
          {t('analysis.actions.retry')}
        </Button>
      );
    default:
      return null;
  }
}

// --- Simple spinner icon ---

function Spinner() {
  return (
    <svg
      className="animate-spin h-3.5 w-3.5"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}
