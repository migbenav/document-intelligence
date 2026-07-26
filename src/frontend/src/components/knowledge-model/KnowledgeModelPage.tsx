import { useEffect } from 'react';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import { KMHeader } from './KMHeader';
import { ElementListView } from './ElementListView';
import { ElementDetailPanel } from './ElementDetailPanel';
import { LoadingState } from './LoadingState';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { QueryPanel } from '@/components/query/QueryPanel';

interface KnowledgeModelPageProps {
  documentId: string;
}

/**
 * Top-level orchestrator for the Knowledge Model visualization.
 *
 * Responsibilities:
 * - Fetches the KM on mount (store handles cache internally).
 * - Renders the appropriate state view (loading, empty, error, loaded).
 * - Composes the layout: KMHeader + content view (list or graph) + detail panel.
 * - Responsive master-detail layout using Tailwind breakpoints.
 */
export function KnowledgeModelPage({ documentId }: KnowledgeModelPageProps) {
  const status = useKnowledgeModelStore((s) => s.status);
  const knowledgeModel = useKnowledgeModelStore((s) => s.knowledgeModel);
  const selectedElementId = useKnowledgeModelStore((s) => s.selectedElementId);
  const viewMode = useKnowledgeModelStore((s) => s.viewMode);
  const error = useKnowledgeModelStore((s) => s.error);
  const fetchKnowledgeModel = useKnowledgeModelStore((s) => s.fetchKnowledgeModel);

  // Fetch knowledge model on mount (store skips if already cached for this documentId)
  useEffect(() => {
    void fetchKnowledgeModel(documentId);
  }, [documentId, fetchKnowledgeModel]);

  // Loading or idle state
  if (status === 'loading' || status === 'idle') {
    return (
      <div data-testid="km-page">
        <LoadingState />
      </div>
    );
  }

  // Empty state
  if (status === 'empty') {
    return (
      <div data-testid="km-page">
        <EmptyState />
      </div>
    );
  }

  // Error state
  if (status === 'error') {
    return (
      <div data-testid="km-page">
        <ErrorState message={error ?? ''} documentId={documentId} />
      </div>
    );
  }

  // Loaded state — knowledgeModel is guaranteed non-null here
  const km = knowledgeModel!;

  // Resolve the selected element if one is active
  const selectedElement = selectedElementId
    ? km.elements.find((el) => el.id === selectedElementId) ?? null
    : null;

  return (
    <div className="flex flex-col gap-6" data-testid="km-page">
      <KMHeader verificationRate={km.extraction_metadata.verification_rate} />

      <div className="lg:grid lg:grid-cols-[2fr_3fr] lg:gap-0 min-h-0 flex-1">
        {/* Left column: list or graph view */}
        <div className="min-h-0 overflow-y-auto">
          {viewMode === 'list' && <ElementListView elements={km.elements} />}
          {viewMode === 'graph' && (
            <div
              className="flex items-center justify-center py-12 text-sm text-muted-foreground"
              data-testid="km-graph-placeholder"
            >
              Graph view coming soon
            </div>
          )}
        </div>

        {/* Right column: detail panel (shown when an element is selected) */}
        {selectedElement && (
          <ElementDetailPanel element={selectedElement} allElements={km.elements} />
        )}
      </div>

      {/* Query Panel: shown alongside KM visualization when KM is completed */}
      <div className="min-h-[300px] max-h-[500px]" data-testid="km-query-panel-container">
        <QueryPanel documentId={documentId} isKmCompleted={status === 'loaded'} />
      </div>
    </div>
  );
}
