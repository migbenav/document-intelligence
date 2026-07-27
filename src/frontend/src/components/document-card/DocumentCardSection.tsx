import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import { useDocumentCardStore } from '@/store/documentCardStore';
import { fetchCard as fetchCardApi, CardApiError } from '@/api/documentCard';
import type { DocumentCard } from '@/types/documentCard';
import { DocumentCardSkeleton } from './DocumentCardSkeleton';
import { DocumentCardView } from './DocumentCardView';

const CARD_POLL_INTERVAL_MS = 1500;
const CARD_MAX_POLL_ATTEMPTS = 10;

export interface DocumentCardSectionProps {
  documentId: string;
}

/**
 * Manages the lifecycle of showing a document card after upload:
 * 1. Shows skeleton while polling for the card
 * 2. Shows DocumentCardView once card is available
 * 3. Shows informational message + retry if polling exhausts
 * 4. Handles retryLlm for partial cards
 */
export function DocumentCardSection({ documentId }: DocumentCardSectionProps) {
  const { t } = useTranslation();
  const retryLlm = useDocumentCardStore((s) => s.retryLlm);
  const storeCard = useDocumentCardStore((s) => s.card);

  const [card, setCard] = useState<DocumentCard | null>(null);
  const [pollExhausted, setPollExhausted] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const pollCountRef = useRef(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const setStoreCard = useDocumentCardStore((s) => s.setCard);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const pollForCard = useCallback(async () => {
    pollCountRef.current += 1;

    try {
      const result = await fetchCardApi(documentId);
      // Card is available — update both local and global state
      setCard(result);
      setStoreCard(result);
      stopPolling();
    } catch (err) {
      if (
        err instanceof CardApiError &&
        err.status === 404 &&
        err.code === 'card_not_found'
      ) {
        // Card not ready yet — continue polling unless exhausted
        if (pollCountRef.current >= CARD_MAX_POLL_ATTEMPTS) {
          stopPolling();
          setPollExhausted(true);
        }
      } else {
        // Unexpected error — stop polling, show exhausted state
        if (pollCountRef.current >= CARD_MAX_POLL_ATTEMPTS) {
          stopPolling();
          setPollExhausted(true);
        }
      }
    }
  }, [documentId, stopPolling]);

  // Start polling when the component mounts (upload step is 'ready')
  useEffect(() => {
    setCard(null);
    setPollExhausted(false);
    pollCountRef.current = 0;

    // First poll immediately
    void pollForCard();

    // Then set interval for subsequent polls
    intervalRef.current = setInterval(() => {
      void pollForCard();
    }, CARD_POLL_INTERVAL_MS);

    return () => {
      stopPolling();
    };
  }, [documentId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync card from store (when retryLlm updates it)
  useEffect(() => {
    if (storeCard) {
      setCard(storeCard);
    }
  }, [storeCard]);

  const handleManualFetch = useCallback(() => {
    setPollExhausted(false);
    pollCountRef.current = 0;

    // Start a new polling cycle
    void pollForCard();
    intervalRef.current = setInterval(() => {
      void pollForCard();
    }, CARD_POLL_INTERVAL_MS);
  }, [pollForCard]);

  const handleRetryLlm = useCallback(async () => {
    setRetrying(true);
    try {
      await retryLlm(documentId);
    } finally {
      setRetrying(false);
    }
  }, [documentId, retryLlm]);

  // Card is available — show it
  if (card) {
    return (
      <DocumentCardView
        card={card}
        onRetry={handleRetryLlm}
      />
    );
  }

  // Polling exhausted — show message + manual retry button
  if (pollExhausted) {
    return (
      <div data-testid="document-card-poll-exhausted" className="space-y-3">
        <Alert>
          <AlertDescription>
            {t('card.pollExhausted')}
          </AlertDescription>
        </Alert>
        <Button
          variant="outline"
          onClick={handleManualFetch}
          aria-label={t('card.manualRetry')}
          data-testid="card-manual-retry-button"
        >
          {t('card.manualRetry')}
        </Button>
      </div>
    );
  }

  // Retrying LLM — show loading state
  if (retrying) {
    return <DocumentCardSkeleton />;
  }

  // Default: show skeleton while polling
  return <DocumentCardSkeleton />;
}
