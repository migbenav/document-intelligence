import { Component } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from '@/i18n';
import type { SourceRefResponse } from '@/types/knowledgeModel';

// --- Props ---

interface EvidenceSectionProps {
  sourceRef: SourceRefResponse;
  verified: boolean;
}

// --- Error Boundary ---

interface EvidenceErrorBoundaryState {
  hasError: boolean;
}

interface EvidenceErrorBoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
}

class EvidenceErrorBoundary extends Component<
  EvidenceErrorBoundaryProps,
  EvidenceErrorBoundaryState
> {
  constructor(props: EvidenceErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): EvidenceErrorBoundaryState {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

// --- Sub-components ---

function VerifiedStatus() {
  const { t } = useTranslation();

  return (
    <div className="flex items-start gap-2 text-sm text-green-700" data-testid="evidence-verified">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="mt-0.5 h-4 w-4 shrink-0"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
          clipRule="evenodd"
        />
      </svg>
      <span aria-label={t('km.element.verified')}>{t('km.element.verified')}</span>
    </div>
  );
}

function NotVerifiedStatus() {
  const { t } = useTranslation();

  return (
    <div className="flex items-start gap-2 text-sm text-amber-600" data-testid="evidence-not-verified">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="mt-0.5 h-4 w-4 shrink-0"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 5Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
          clipRule="evenodd"
        />
      </svg>
      <span aria-label={t('km.element.notVerified')}>{t('km.element.notVerified')}</span>
    </div>
  );
}

function ContextualMetadata({ sourceRef }: { sourceRef: SourceRefResponse }) {
  const { t } = useTranslation();

  const hasSection = sourceRef.section !== null && sourceRef.section !== '';
  const hasPage = sourceRef.page !== null;

  if (!hasSection && !hasPage) {
    return null;
  }

  return (
    <div className="mt-2 text-xs text-muted-foreground" data-testid="evidence-metadata">
      {hasSection && <span>{sourceRef.section}</span>}
      {hasSection && hasPage && <span className="mx-1">·</span>}
      {hasPage && <span>{t('km.element.evidence')} — p. {sourceRef.page}</span>}
    </div>
  );
}

// --- Main Component ---

function EvidenceSectionContent({ sourceRef, verified }: EvidenceSectionProps) {
  const { t } = useTranslation();

  return (
    <section aria-labelledby="evidence-heading" data-testid="evidence-section">
      <h3 id="evidence-heading" className="mb-2 text-sm font-semibold">
        {t('km.element.evidence')}
      </h3>

      <blockquote className="border-l-4 border-primary/30 bg-muted/50 py-2 pl-4 pr-3 text-sm italic">
        {sourceRef.evidence}
      </blockquote>

      <ContextualMetadata sourceRef={sourceRef} />

      <div className="mt-3">
        {verified ? <VerifiedStatus /> : <NotVerifiedStatus />}
      </div>
    </section>
  );
}

export function EvidenceSection({ sourceRef, verified }: EvidenceSectionProps) {
  const { t } = useTranslation();

  return (
    <EvidenceErrorBoundary
      fallback={
        <p className="text-sm text-destructive" data-testid="evidence-error">
          {t('km.element.evidenceError')}
        </p>
      }
    >
      <EvidenceSectionContent sourceRef={sourceRef} verified={verified} />
    </EvidenceErrorBoundary>
  );
}
