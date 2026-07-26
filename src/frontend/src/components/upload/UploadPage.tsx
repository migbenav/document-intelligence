import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';
import { UploadZone } from './UploadZone';
import { FileInfo } from './FileInfo';
import { ConsentDialog } from './ConsentDialog';
import { UploadProgress } from './UploadProgress';
import { ProcessingStatus } from './ProcessingStatus';
import { ErrorDisplay } from './ErrorDisplay';
import { DocumentCardSection } from '@/components/document-card/DocumentCardSection';

export function UploadPage() {
  const { t } = useTranslation();
  const step = useUploadStore((s) => s.step);
  const error = useUploadStore((s) => s.error);
  const documentId = useUploadStore((s) => s.documentId);
  const openConsent = useUploadStore((s) => s.openConsent);

  const showUploadZone =
    step === 'idle' ||
    step === 'file-selected' ||
    step === 'consent-pending' ||
    (step === 'error' && error?.type === 'validation');

  const showFileInfo = step === 'file-selected' || step === 'consent-pending';
  const showUploadButton = step === 'file-selected';
  const showUploadProgress = step === 'uploading';
  const showProcessingStatus = step === 'processing' || step === 'ready';
  const showDocumentCard = step === 'ready' && documentId !== null;
  const showError = step === 'error';

  return (
    <div className="space-y-6">
      {showUploadZone && <UploadZone />}

      {showFileInfo && <FileInfo />}

      {showUploadButton && (
        <Button
          onClick={openConsent}
          className="w-full"
          data-testid="upload-button"
        >
          {t('upload.button')}
        </Button>
      )}

      <ConsentDialog />

      {showUploadProgress && <UploadProgress />}

      {showProcessingStatus && <ProcessingStatus />}

      {showDocumentCard && <DocumentCardSection documentId={documentId!} />}

      {showError && <ErrorDisplay />}
    </div>
  );
}
