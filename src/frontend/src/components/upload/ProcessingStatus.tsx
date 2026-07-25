import { useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useTranslation } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

export function ProcessingStatus() {
  const { t } = useTranslation();
  const step = useUploadStore((s) => s.step);
  const result = useUploadStore((s) => s.result);
  const startPolling = useUploadStore((s) => s.startPolling);
  const stopPolling = useUploadStore((s) => s.stopPolling);

  useEffect(() => {
    if (step === 'processing') {
      startPolling();
    }
    return () => {
      stopPolling();
    };
  }, [step, startPolling, stopPolling]);

  if (step === 'processing') {
    return (
      <div className="flex flex-col items-center gap-3 py-8" data-testid="processing-status">
        <div
          className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary"
          role="status"
          aria-label={t('status.processing')}
        />
        <p className="text-sm text-muted-foreground">{t('status.processing')}</p>
      </div>
    );
  }

  if (step === 'ready' && result) {
    return (
      <div className="space-y-4" data-testid="processing-status-ready">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t('status.ready')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-muted-foreground">Filename</dt>
              <dd data-testid="result-filename">{result.filename}</dd>

              <dt className="text-muted-foreground">Language</dt>
              <dd data-testid="result-language">{result.language ?? 'Unknown'}</dd>

              <dt className="text-muted-foreground">Chunks</dt>
              <dd data-testid="result-chunk-count">{result.chunkCount}</dd>
            </dl>
          </CardContent>
        </Card>

        {result.warnings.length > 0 && (
          <div className="space-y-2" data-testid="warnings-list">
            {result.warnings.map((warning, index) => (
              <Alert key={index} variant="default">
                <AlertDescription>{warning}</AlertDescription>
              </Alert>
            ))}
          </div>
        )}
      </div>
    );
  }

  return null;
}
