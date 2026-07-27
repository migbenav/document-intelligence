import { useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';
import { useDocumentCardStore } from '@/store/documentCardStore';
import { useAnalysisStore } from '@/store/analysisStore';
import { UploadZone } from './UploadZone';
import { FileInfo } from './FileInfo';
import { ConsentDialog } from './ConsentDialog';
import { UploadProgress } from './UploadProgress';
import { ProcessingStatus } from './ProcessingStatus';
import { ErrorDisplay } from './ErrorDisplay';
import { DocumentCardSection } from '@/components/document-card/DocumentCardSection';
import { OptionsPanel } from '@/components/analysis/OptionsPanel';
import { AnalysisResultView } from '@/components/analysis/AnalysisResultView';
import type { AnalysisType, AnalysisStatus } from '@/types/analysis';

export function UploadPage() {
  const { t } = useTranslation();
  const step = useUploadStore((s) => s.step);
  const error = useUploadStore((s) => s.error);
  const documentId = useUploadStore((s) => s.documentId);
  const openConsent = useUploadStore((s) => s.openConsent);
  const card = useDocumentCardStore((s) => s.card);

  const activeAnalysis = useAnalysisStore((s) => s.activeAnalysis);
  const results = useAnalysisStore((s) => s.results);
  const statuses = useAnalysisStore((s) => s.statuses);
  const triggerAnalysis = useAnalysisStore((s) => s.triggerAnalysis);

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

  // Determine which analysis result to display:
  // Show the active/last-triggered analysis that has a result
  const displayedAnalysisType = ((): AnalysisType | null => {
    // Prefer the active analysis if it has results
    if (activeAnalysis && results[activeAnalysis] != null) {
      return activeAnalysis;
    }
    // Still loading — don't show stale result from a different type
    if (activeAnalysis) return null;
    // Fall back to the most recently completed analysis with a result
    const typesWithResults = (Object.keys(results) as AnalysisType[]).filter(
      (type) => results[type] != null
    );
    return typesWithResults[typesWithResults.length - 1] ?? null;
  })();

  const displayedResult = displayedAnalysisType ? results[displayedAnalysisType] : null;
  const displayedStatus: AnalysisStatus | undefined = displayedAnalysisType
    ? statuses?.[displayedAnalysisType]?.status
    : undefined;

  const handleReanalyze = useCallback(() => {
    if (displayedAnalysisType && documentId) {
      void triggerAnalysis(documentId, displayedAnalysisType);
    }
  }, [displayedAnalysisType, documentId, triggerAnalysis]);

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

      {showDocumentCard && card && (
        <OptionsPanel
          documentId={documentId!}
          classification={card.classification ?? null}
        />
      )}

      {showDocumentCard && displayedAnalysisType && displayedResult != null && (
        <AnalysisResultView
          analysisType={displayedAnalysisType}
          result={displayedResult}
          status={displayedStatus}
          onReanalyze={handleReanalyze}
        />
      )}

      {showError && <ErrorDisplay />}
    </div>
  );
}
