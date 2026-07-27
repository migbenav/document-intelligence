import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useTranslation } from '@/i18n';
import { useAnalysisStore } from '@/store/analysisStore';
import type { AnalysisErrorCode } from '@/api/analyses';

/**
 * Displays a classified error alert for analysis failures.
 * Shows differentiated messages depending on the error_code from the backend.
 */
export function AnalysisErrorAlert() {
  const { t } = useTranslation();
  const error = useAnalysisStore((s) => s.error);
  const errorCode = useAnalysisStore((s) => s.errorCode);
  const errorModelId = useAnalysisStore((s) => s.errorModelId);

  if (!error) return null;

  const message = getErrorMessage(t, errorCode, errorModelId);

  return (
    <div data-testid="analysis-error-alert">
      <Alert variant="destructive">
        <AlertTitle>{t('analysis.error.title')}</AlertTitle>
        <AlertDescription>
          <p data-testid="analysis-error-message">{message}</p>
        </AlertDescription>
      </Alert>
    </div>
  );
}

function getErrorMessage(
  t: (key: string, params?: Record<string, string>) => string,
  errorCode: AnalysisErrorCode | null,
  modelId: string | null,
): string {
  switch (errorCode) {
    case 'quota_exhausted':
      return t('analysis.error.quotaExhausted', { model: modelId ?? 'unknown' });
    case 'timeout':
      return t('analysis.error.timeout');
    case 'auth_error':
      return t('analysis.error.authError');
    case 'analysis_failed':
      return t('analysis.error.analysisFailed');
    default:
      return t('analysis.error.analysisFailed');
  }
}
