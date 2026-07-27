import { AlertTriangle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
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
  modelId?: string | null;
  fallbackUsed?: boolean;
  onReanalyze?: () => void;
}

/**
 * AnalysisResultView — Routes to the correct result view component based on
 * analysis type and shows an outdated banner when results are stale.
 *
 * Requirements: Req 8 (criteria 6, 7), Req 5 (criterion 4)
 */
export function AnalysisResultView({
  analysisType,
  result,
  status,
  modelId,
  fallbackUsed,
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
      {modelId && (
        <div className="flex items-center gap-2" data-testid="model-badge">
          <Badge variant="secondary" className="text-xs font-normal">
            {shortenModelId(modelId)}
            {fallbackUsed && ' (fallback)'}
          </Badge>
        </div>
      )}

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

// --- Helpers ---

/**
 * Shorten a full model identifier to a readable display name.
 * Examples:
 *   "gemini/gemini-2.5-flash" → "gemini-2.5-flash"
 *   "groq/llama-3.3-70b-versatile" → "llama-3.3"
 *   "groq/meta-llama/llama-4-maverick-17b-128e" → "llama-4-maverick"
 */
function shortenModelId(modelId: string): string {
  // Take the last segment after any provider prefix (e.g. "gemini/", "groq/", "groq/meta-llama/")
  const segments = modelId.split('/');
  const name = segments[segments.length - 1] ?? modelId;

  // Common shortening patterns
  const shortenings: [RegExp, string][] = [
    [/^gemini-(\d+\.\d+-\w+).*$/, 'gemini-$1'],
    [/^llama-(\d+\.\d+).*$/, 'llama-$1'],
    [/^llama-(\d+)-(\w+).*$/, 'llama-$1-$2'],
  ];

  for (const [pattern, replacement] of shortenings) {
    if (pattern.test(name)) {
      return name.replace(pattern, replacement);
    }
  }

  return name;
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
      return <IndexTreeView tree={data.tree} documentPurpose={data.document_purpose} />;
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
          coherenceNote={data.coherence_note}
        />
      );
    }
    case 'conclusions': {
      const data = result as ConclusionsResult;
      return <ConclusionsView observations={data.observations} domains_identified={data.domains_identified} />;
    }
    default:
      return null;
  }
}
