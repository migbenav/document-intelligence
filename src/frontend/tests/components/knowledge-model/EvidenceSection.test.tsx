import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { EvidenceSection } from '@/components/knowledge-model/EvidenceSection';
import { TranslationProvider } from '@/i18n';
import type { SourceRefResponse } from '@/types/knowledgeModel';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function makeSourceRef(overrides: Partial<SourceRefResponse> = {}): SourceRefResponse {
  return {
    document_id: 'doc-1',
    chunk_id: 'chunk-1',
    page: null,
    section: null,
    evidence: 'This is the evidence text from the source document.',
    ...overrides,
  };
}

describe('EvidenceSection', () => {
  it('renders the section heading from i18n', () => {
    renderWithProviders(
      <EvidenceSection sourceRef={makeSourceRef()} verified={true} />,
    );

    expect(screen.getByText('Source Evidence')).toBeInTheDocument();
  });

  it('renders evidence text in a blockquote', () => {
    const evidence = 'The system shall process documents within 5 seconds.';
    renderWithProviders(
      <EvidenceSection sourceRef={makeSourceRef({ evidence })} verified={true} />,
    );

    const blockquote = screen.getByText(evidence).closest('blockquote');
    expect(blockquote).toBeInTheDocument();
  });

  it('displays section metadata when section is provided', () => {
    renderWithProviders(
      <EvidenceSection
        sourceRef={makeSourceRef({ section: 'Introduction' })}
        verified={true}
      />,
    );

    expect(screen.getByTestId('evidence-metadata')).toHaveTextContent('Introduction');
  });

  it('displays page metadata when page is provided', () => {
    renderWithProviders(
      <EvidenceSection
        sourceRef={makeSourceRef({ page: 5 })}
        verified={true}
      />,
    );

    expect(screen.getByTestId('evidence-metadata')).toHaveTextContent('p. 5');
  });

  it('displays both section and page metadata when both are provided', () => {
    renderWithProviders(
      <EvidenceSection
        sourceRef={makeSourceRef({ section: 'Chapter 2', page: 12 })}
        verified={true}
      />,
    );

    const metadata = screen.getByTestId('evidence-metadata');
    expect(metadata).toHaveTextContent('Chapter 2');
    expect(metadata).toHaveTextContent('p. 12');
  });

  it('does not render metadata when neither section nor page is available', () => {
    renderWithProviders(
      <EvidenceSection
        sourceRef={makeSourceRef({ section: null, page: null })}
        verified={true}
      />,
    );

    expect(screen.queryByTestId('evidence-metadata')).not.toBeInTheDocument();
  });

  it('shows verified status with checkmark icon and text when verified=true', () => {
    renderWithProviders(
      <EvidenceSection sourceRef={makeSourceRef()} verified={true} />,
    );

    expect(screen.getByTestId('evidence-verified')).toBeInTheDocument();
    expect(
      screen.getByText('Verified: evidence confirmed in source document'),
    ).toBeInTheDocument();
  });

  it('shows not-verified status with warning icon and text when verified=false', () => {
    renderWithProviders(
      <EvidenceSection sourceRef={makeSourceRef()} verified={false} />,
    );

    expect(screen.getByTestId('evidence-not-verified')).toBeInTheDocument();
    expect(
      screen.getByText('Not verified: evidence not found in source document'),
    ).toBeInTheDocument();
  });

  it('shows inline error message when evidence content throws during render', () => {
    // Suppress console.error from the intentional error boundary trigger
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Force a render error by passing a sourceRef where accessing evidence throws
    const badSourceRef = new Proxy(makeSourceRef(), {
      get(target, prop) {
        if (prop === 'evidence') {
          throw new Error('Simulated render failure');
        }
        return Reflect.get(target, prop);
      },
    });

    renderWithProviders(
      <EvidenceSection sourceRef={badSourceRef} verified={true} />,
    );

    expect(screen.getByTestId('evidence-error')).toBeInTheDocument();
    expect(screen.getByText('Evidence could not be loaded')).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it('renders the evidence section with proper test id', () => {
    renderWithProviders(
      <EvidenceSection sourceRef={makeSourceRef()} verified={true} />,
    );

    expect(screen.getByTestId('evidence-section')).toBeInTheDocument();
  });

  it('renders aria-labelledby linking to the heading', () => {
    renderWithProviders(
      <EvidenceSection sourceRef={makeSourceRef()} verified={true} />,
    );

    const section = screen.getByTestId('evidence-section');
    expect(section).toHaveAttribute('aria-labelledby', 'evidence-heading');
  });
});
