import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { SourceRefPopover } from '@/components/analysis/SourceRefPopover';
import { TranslationProvider } from '@/i18n';
import type { SourceRef } from '@/types/analysis';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider locale="en">{ui}</TranslationProvider>);
}

const mockSourceRef: SourceRef = {
  chunk_ids: ['chunk-1', 'chunk-2'],
  text_excerpt: 'This is the relevant text excerpt from the document.',
  section: 'Introduction',
};

const mockSourceRefNoSection: SourceRef = {
  chunk_ids: ['chunk-3'],
  text_excerpt: 'Another excerpt without section context.',
  section: null,
};

describe('SourceRefPopover', () => {
  describe('when sourceRef is null', () => {
    it('renders an "Unverified" badge', () => {
      renderWithProviders(<SourceRefPopover sourceRef={null} />);
      const badge = screen.getByTestId('source-ref-unverified');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent('Unverified');
    });

    it('does not render a trigger button', () => {
      renderWithProviders(<SourceRefPopover sourceRef={null} />);
      expect(screen.queryByTestId('source-ref-trigger')).not.toBeInTheDocument();
    });
  });

  describe('when sourceRef is provided', () => {
    it('renders a "Show source" trigger button', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      const trigger = screen.getByTestId('source-ref-trigger');
      expect(trigger).toBeInTheDocument();
      expect(trigger).toHaveTextContent('Show source');
    });

    it('trigger has aria-expanded=false initially', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      const trigger = screen.getByTestId('source-ref-trigger');
      expect(trigger).toHaveAttribute('aria-expanded', 'false');
    });

    it('does not show content initially', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      expect(screen.queryByTestId('source-ref-content')).not.toBeInTheDocument();
    });

    it('does not render an "Unverified" badge', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      expect(screen.queryByTestId('source-ref-unverified')).not.toBeInTheDocument();
    });
  });

  describe('expand/collapse behavior', () => {
    it('expands on click to show text_excerpt', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      const trigger = screen.getByTestId('source-ref-trigger');
      fireEvent.click(trigger);

      expect(trigger).toHaveAttribute('aria-expanded', 'true');
      expect(trigger).toHaveTextContent('Hide source');
      expect(screen.getByTestId('source-ref-content')).toBeInTheDocument();
      expect(screen.getByText(/This is the relevant text excerpt/)).toBeInTheDocument();
    });

    it('shows section context when section is present', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      fireEvent.click(screen.getByTestId('source-ref-trigger'));

      expect(screen.getByText('Section: Introduction')).toBeInTheDocument();
    });

    it('does not show section context when section is null', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRefNoSection} />);
      fireEvent.click(screen.getByTestId('source-ref-trigger'));

      expect(screen.getByText(/Another excerpt without section context/)).toBeInTheDocument();
      expect(screen.queryByText(/Section:/)).not.toBeInTheDocument();
    });

    it('collapses on second click', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      const trigger = screen.getByTestId('source-ref-trigger');
      fireEvent.click(trigger);
      fireEvent.click(trigger);

      expect(trigger).toHaveAttribute('aria-expanded', 'false');
      expect(trigger).toHaveTextContent('Show source');
      expect(screen.queryByTestId('source-ref-content')).not.toBeInTheDocument();
    });
  });

  describe('keyboard accessibility', () => {
    it('expands on Enter key press', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      const trigger = screen.getByTestId('source-ref-trigger');
      fireEvent.keyDown(trigger, { key: 'Enter' });

      expect(trigger).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByTestId('source-ref-content')).toBeInTheDocument();
    });

    it('expands on Space key press', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      const trigger = screen.getByTestId('source-ref-trigger');
      fireEvent.keyDown(trigger, { key: ' ' });

      expect(trigger).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByTestId('source-ref-content')).toBeInTheDocument();
    });

    it('does not expand on other key presses', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      const trigger = screen.getByTestId('source-ref-trigger');
      fireEvent.keyDown(trigger, { key: 'Tab' });

      expect(trigger).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByTestId('source-ref-content')).not.toBeInTheDocument();
    });
  });

  describe('does not display chunk_ids', () => {
    it('chunk_ids are not rendered in the expanded content', () => {
      renderWithProviders(<SourceRefPopover sourceRef={mockSourceRef} />);
      fireEvent.click(screen.getByTestId('source-ref-trigger'));

      const content = screen.getByTestId('source-ref-content');
      expect(content.textContent).not.toContain('chunk-1');
      expect(content.textContent).not.toContain('chunk-2');
    });
  });
});
