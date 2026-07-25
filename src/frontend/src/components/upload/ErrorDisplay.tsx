import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

export function ErrorDisplay() {
  const { t } = useTranslation();
  const step = useUploadStore((s) => s.step);
  const error = useUploadStore((s) => s.error);
  const reset = useUploadStore((s) => s.reset);
  const startUpload = useUploadStore((s) => s.startUpload);

  if (step !== 'error' || !error) {
    return null;
  }

  const handleRetry = () => {
    // Transition back to uploading state and re-invoke the upload
    useUploadStore.setState({ step: 'uploading', error: null });
    void startUpload();
  };

  const handleStartOver = () => {
    reset();
  };

  return (
    <div data-testid="error-display">
      <Alert variant="destructive">
        <AlertTitle>{t('status.failed')}</AlertTitle>
        <AlertDescription>
          <p className="mb-4" data-testid="error-message">
            {error.message}
          </p>
          <div className="flex gap-2">
            {error.canRetry && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleRetry}
                data-testid="retry-button"
              >
                {t('actions.retry')}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleStartOver}
              data-testid="start-over-button"
            >
              {t('actions.startOver')}
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  );
}
