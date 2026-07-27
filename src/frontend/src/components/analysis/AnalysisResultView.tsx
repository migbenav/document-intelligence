import { AlertTriangle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import type { AnalysisType, AnalysisStatus } from '@/types/analysis';
import type { IndexResult, RelationsResult, QuestionsResult, ConclusionsResult } from '@/types/analysis';
import { IndexTreeView } from './IndexTreeView';
import { RelationsListView } from './RelationsListView';
import { QuestionsCascadeView } from './QuestionsCascadeView';
import { ConclusionsView } from './ConclusionsView';

export interface AnalysisResultViewProps {
  analysisType: AnalysisType;
  result: unknown;
  status?: AnalysisStatus;
  onReanalyze?: () => void;
}

/**
 * AnalysisResultView — Routes to the correct result view component based on
 * analysis type and shows an outdated banner when results are stale.
 *
 * Requirements: Req 8 (criteria 6, 7)
 */
export function AnalysisResultView({
  analysisType,
  result,
  status,
  onReanalyze,
}: AnalysisResultViewProps) {
  const { t } = useTranslation();

  if (result == null) {
    return null;
  }

  return (
    <section
      aria-label={t('analysis.resultLabel')}
      data-testid="analysis-result-view"
      className="space-y-4"
    >
      {status === 'outdated' && (
        <Alert
          className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20"
          data-testid="outdated-banner"
        >
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <AlertDescription className="flex items-center justify-between gap-4">
            <span className="text-yellow-800 dark:text-yellow-200">
              {t('analysis.outdatedBanner')}
            </span>
            {onReanalyze && (
              <Button
                variant="outline"
                size="sm"
                onClick={onReanalyze}
                className="shrink-0"
                data-testid="reanalyze-button"
              >
                {t('analysis.actions.reanalyze')}
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      <ResultRouter analysisType={analysisType} result={result} />
    </section>
  );
}

// --- Internal routing ---

interface ResultRouterProps {
  analysisType: AnalysisType;
  result: unknown;
}

function ResultRouter({ analysisType, result }: ResultRouterProps) {
  switch (analysisType) {
    case 'build_index': {
      const data = result as IndexResult;
      return <IndexTreeView tree={data.tree} />;
    }
    case 'section_relations': {
      const data = result as RelationsResult;
      return <RelationsListView relations={data.relations} />;
    }
    case 'questions_answered': {
      const data = result as QuestionsResult;
      return (
        <QuestionsCascadeView
          documentQuestions={data.document_questions}
          sectionQuestions={data.section_questions}
        />
      );
    }
    case 'conclusions': {
      const data = result as ConclusionsResult;
      return <ConclusionsView observations={data.observations} />;
    }
    default:
      return null;
  }
}
