import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { EvidenceReference } from '@/components/query/EvidenceReference';
import { TranslationProvider } from '@/i18n';
import type { QuerySourceRef } from '@/store/queryStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function makeSourceRef(overrides: Partial<QuerySourceRef> = {}): QuerySourceRef {
  return {
    document_id: 'doc-1',
    chunk_id: 'chunk-001',
    page: null,
    section: null,
    evidence: 'The system processes documents using natural language analysis.',
    evidence_verified: true,
    ...overrides,
  };
}

describe('EvidenceReference', () => {
  describe('evidence text display', () => {
    it('renders full evidence text when under 200 characters', () => {
      const evidence = 'Short evidence text.';
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef({ evidence })} />,
      );

      expect(screen.getByTestId('evidence-text')).toHaveTextContent(evidence);
      expect(screen.queryByTestId('evidence-toggle')).not.toBeInTheDocument();
    });

    it('truncates evidence text to 200 chars with ellipsis when longer', () => {
      const evidence = 'A'.repeat(250);
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef({ evidence })} />,
      );

      const displayed = screen.getByTestId('evidence-text').textContent!;
      expect(displayed.length).toBe(201); // 200 chars + ellipsis
      expect(displayed.endsWith('…')).toBe(true);
    });

    it('shows "Show more" toggle for long evidence text', () => {
      const evidence = 'B'.repeat(250);
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef({ evidence })} />,
      );

      expect(screen.getByTestId('evidence-toggle')).toHaveTextContent('Show more');
    });

    it('expands evidence text on "Show more" click', async () => {
      const user = userEvent.setup();
      const evidence = 'C'.repeat(250);
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef({ evidence })} />,
      );

      await user.click(screen.getByTestId('evidence-toggle'));

      expect(screen.getByTestId('evidence-text')).toHaveTextContent(evidence);
      expect(screen.getByTestId('evidence-toggle')).toHaveTextContent('Show less');
    });

    it('collapses evidence text on "Show less" click', async () => {
      const user = userEvent.setup();
      const evidence = 'D'.repeat(250);
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef({ evidence })} />,
      );

      await user.click(screen.getByTestId('evidence-toggle'));
      await user.click(screen.getByTestId('evidence-toggle'));

      const displayed = screen.getByTestId('evidence-text').textContent!;
      expect(displayed.length).toBe(201);
      expect(screen.getByTestId('evidence-toggle')).toHaveTextContent('Show more');
    });
  });

  describe('metadata display', () => {
    it('shows section when available', () => {
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ section: 'Introduction' })}
        />,
      );

      expect(screen.getByTestId('evidence-metadata')).toHaveTextContent(
        'Section: Introduction',
      );
    });

    it('shows page when available', () => {
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef({ page: 5 })} />,
      );

      expect(screen.getByTestId('evidence-metadata')).toHaveTextContent('Page 5');
    });

    it('shows both section and page separated by a dot', () => {
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ section: 'Chapter 2', page: 12 })}
        />,
      );

      const metadata = screen.getByTestId('evidence-metadata');
      expect(metadata).toHaveTextContent('Section: Chapter 2');
      expect(metadata).toHaveTextContent('Page 12');
    });

    it('does not render metadata when neither section nor page is available', () => {
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ section: null, page: null })}
        />,
      );

      expect(screen.queryByTestId('evidence-metadata')).not.toBeInTheDocument();
    });
  });

  describe('verification badge', () => {
    it('shows verified badge when evidence_verified is true', () => {
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ evidence_verified: true })}
        />,
      );

      expect(
        screen.getByTestId('verification-badge-verified'),
      ).toBeInTheDocument();
    });

    it('shows not-verified badge when evidence_verified is false', () => {
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ evidence_verified: false })}
        />,
      );

      expect(
        screen.getByTestId('verification-badge-unverified'),
      ).toBeInTheDocument();
    });
  });

  describe('navigation', () => {
    it('calls onNavigate with chunk_id on click', async () => {
      const user = userEvent.setup();
      const onNavigate = vi.fn();
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ chunk_id: 'chunk-042' })}
          onNavigate={onNavigate}
        />,
      );

      await user.click(screen.getByTestId('evidence-reference'));

      expect(onNavigate).toHaveBeenCalledWith('chunk-042');
      expect(onNavigate).toHaveBeenCalledTimes(1);
    });

    it('calls onNavigate on Enter key press', async () => {
      const user = userEvent.setup();
      const onNavigate = vi.fn();
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ chunk_id: 'chunk-007' })}
          onNavigate={onNavigate}
        />,
      );

      const button = screen.getByTestId('evidence-reference');
      button.focus();
      await user.keyboard('{Enter}');

      expect(onNavigate).toHaveBeenCalledWith('chunk-007');
    });

    it('calls onNavigate on Space key press', async () => {
      const user = userEvent.setup();
      const onNavigate = vi.fn();
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ chunk_id: 'chunk-009' })}
          onNavigate={onNavigate}
        />,
      );

      const button = screen.getByTestId('evidence-reference');
      button.focus();
      await user.keyboard(' ');

      expect(onNavigate).toHaveBeenCalledWith('chunk-009');
    });

    it('does not throw when onNavigate is not provided', async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef()} />,
      );

      await expect(
        user.click(screen.getByTestId('evidence-reference')),
      ).resolves.not.toThrow();
    });
  });

  describe('accessibility', () => {
    it('renders as a button element', () => {
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef()} />,
      );

      const element = screen.getByTestId('evidence-reference');
      expect(element.tagName).toBe('BUTTON');
    });

    it('has an accessible label for navigation', () => {
      renderWithProviders(
        <EvidenceReference sourceRef={makeSourceRef()} />,
      );

      expect(screen.getByTestId('evidence-reference')).toHaveAttribute(
        'aria-label',
        'Navigate to source',
      );
    });

    it('toggle has aria-expanded attribute', () => {
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ evidence: 'E'.repeat(250) })}
        />,
      );

      const toggle = screen.getByTestId('evidence-toggle');
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
    });

    it('toggle aria-expanded becomes true after expanding', async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ evidence: 'F'.repeat(250) })}
        />,
      );

      await user.click(screen.getByTestId('evidence-toggle'));

      expect(screen.getByTestId('evidence-toggle')).toHaveAttribute(
        'aria-expanded',
        'true',
      );
    });

    it('toggle is keyboard activatable with Enter', async () => {
      const user = userEvent.setup();
      const evidence = 'G'.repeat(250);
      const onNavigate = vi.fn();
      renderWithProviders(
        <EvidenceReference
          sourceRef={makeSourceRef({ evidence })}
          onNavigate={onNavigate}
        />,
      );

      const toggle = screen.getByTestId('evidence-toggle');
      toggle.focus();
      await user.keyboard('{Enter}');

      // Toggle should expand without navigating
      expect(screen.getByTestId('evidence-text')).toHaveTextContent(evidence);
      expect(onNavigate).not.toHaveBeenCalled();
    });
  });
});
