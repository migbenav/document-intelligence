import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';

interface ErrorStateProps {
  message: string;
  documentId: string;
}

export function ErrorState({ message, documentId }: ErrorStateProps) {
  const { t } = useTranslation();
  const fetchKnowledgeModel = useKnowledgeModelStore((s) => s.fetchKnowledgeModel);

  const handleRetry = () => {
    void fetchKnowledgeModel(documentId);
  };

  return (
    <div
      className="flex flex-col items-center justify-center gap-4 py-12"
      data-testid="km-error-state"
    >
      <Alert variant="destructive" className="max-w-md">
        <AlertDescription data-testid="km-error-message">
          {message}
        </AlertDescription>
      </Alert>
      <Button
        variant="outline"
        size="sm"
        onClick={handleRetry}
        data-testid="km-retry-button"
      >
        {t('km.states.retry')}
      </Button>
    </div>
  );
}
