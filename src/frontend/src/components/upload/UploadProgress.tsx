import { useEffect, useState } from 'react';
import { Progress } from '@/components/ui/progress';
import { useTranslation } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

const COLD_START_DELAY_MS = 3000;

export function UploadProgress() {
  const { t } = useTranslation();
  const step = useUploadStore((s) => s.step);
  const uploadProgress = useUploadStore((s) => s.uploadProgress);
  const [showColdStart, setShowColdStart] = useState(false);

  useEffect(() => {
    if (step !== 'uploading') {
      setShowColdStart(false);
      return;
    }

    const timer = setTimeout(() => {
      setShowColdStart(true);
    }, COLD_START_DELAY_MS);

    return () => {
      clearTimeout(timer);
    };
  }, [step]);

  if (step !== 'uploading') {
    return null;
  }

  return (
    <div className="flex flex-col items-center gap-3" role="status" aria-live="polite">
      <div className="flex items-center gap-2">
        <svg
          className="h-5 w-5 animate-spin text-primary"
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
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <p className="text-sm text-muted-foreground">{t('status.uploading')}</p>
      </div>

      <Progress value={uploadProgress} className="w-full max-w-xs" aria-label={t('status.uploading')} />

      <p className="text-xs text-muted-foreground">{uploadProgress}%</p>

      {showColdStart && (
        <p className="text-xs text-muted-foreground italic">
          {t('status.coldStart')}
        </p>
      )}
    </div>
  );
}
