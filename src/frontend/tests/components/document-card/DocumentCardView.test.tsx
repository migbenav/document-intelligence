import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { DocumentCardView } from '@/components/document-card/DocumentCardView';
import type { DocumentCard } from '@/types/documentCard';

const completedCard: DocumentCard = {
  id: 'card-1',
  document_id: 'doc-1',
  title: 'Reglamento de Propiedad Horizontal',
  summary:
    'Este documento establece las normas de convivencia y administración para propiedades horizontales.',
  classification: 'normative',
  organization_type: 'numbered_articles',
  statistics: {
    total_chunks: 45,
    sections_detected: 12,
    hierarchy_levels: 3,
    has_existing_index: true,
  },
  file_metadata: {
    size_bytes: 234500,
    format: 'pdf',
    language: 'es',
    last_modified: null,
  },
  status: 'completed',
  outdated: false,
  model_id: 'groq/llama-3.3-70b-versatile',
  prompt_version: 'base-analysis-v1',
  created_at: '2026-07-26T10:30:00Z',
  updated_at: '2026-07-26T10:30:04Z',
};

const partialCard: DocumentCard = {
  id: 'card-2',
  document_id: 'doc-2',
  title: 'Manual de Usuario',
  summary: null,
  classification: null,
  organization_type: 'headed_sections',
  statistics: {
    total_chunks: 20,
    sections_detected: 5,
    hierarchy_levels: 2,
    has_existing_index: false,
  },
  file_metadata: {
    size_bytes: 102400,
    format: 'markdown',
    language: 'es',
    last_modified: null,
  },
  status: 'partial',
  outdated: false,
  model_id: null,
  prompt_version: null,
  created_at: '2026-07-26T10:30:00Z',
  updated_at: '2026-07-26T10:30:00Z',
};

describe('DocumentCardView', () => {
  describe('completed card', () => {
    it('renders the title prominently', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(
        screen.getByText('Reglamento de Propiedad Horizontal'),
      ).toBeInTheDocument();
    });

    it('renders the summary text', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(
        screen.getByText(completedCard.summary!),
      ).toBeInTheDocument();
    });

    it('renders the classification badge', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(screen.getByText('Normativo')).toBeInTheDocument();
    });

    it('renders the organization type', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(screen.getByText('Artículos numerados')).toBeInTheDocument();
    });

    it('renders statistics', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(screen.getByText('45')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
      expect(screen.getByText('Sí')).toBeInTheDocument();
    });

    it('renders file metadata', () => {
      render(<DocumentCardView card={completedCard} />);
      // formatBytes(234500) → "229 KB"
      expect(screen.getByText('229 KB')).toBeInTheDocument();
      // CSS text-transform uppercase makes them display as PDF/ES, but DOM text is lowercase
      expect(screen.getByText('pdf')).toBeInTheDocument();
      expect(screen.getByText('es')).toBeInTheDocument();
    });

    it('does not show the retry button', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(
        screen.queryByRole('button', { name: /reintentar/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe('partial card', () => {
    it('renders local fields (title, statistics, org type, metadata)', () => {
      render(<DocumentCardView card={partialCard} />);
      expect(screen.getByText('Manual de Usuario')).toBeInTheDocument();
      expect(screen.getByText('20')).toBeInTheDocument();
      expect(screen.getByText('Secciones con encabezados')).toBeInTheDocument();
    });

    it('shows the retry button instead of summary/classification', () => {
      render(<DocumentCardView card={partialCard} />);
      expect(
        screen.getByRole('button', { name: /reintentar análisis/i }),
      ).toBeInTheDocument();
    });

    it('does not show placeholder text for missing fields', () => {
      render(<DocumentCardView card={partialCard} />);
      // No classification badge
      expect(screen.queryByText('Normativo')).not.toBeInTheDocument();
      // No empty summary paragraph
      const summaryParagraph = screen
        .queryAllByRole('generic')
        .find((el) => el.tagName === 'P' && el.textContent === '');
      expect(summaryParagraph).toBeUndefined();
    });

    it('calls onRetry when retry button is clicked', async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();
      render(<DocumentCardView card={partialCard} onRetry={onRetry} />);

      await user.click(
        screen.getByRole('button', { name: /reintentar análisis/i }),
      );
      expect(onRetry).toHaveBeenCalledTimes(1);
    });
  });

  describe('outdated indicator', () => {
    it('displays an outdated indicator when card.outdated is true', () => {
      const outdatedCard = { ...completedCard, outdated: true };
      render(<DocumentCardView card={outdatedCard} />);
      expect(screen.getByText('Desactualizado')).toBeInTheDocument();
    });

    it('does not display outdated indicator when card.outdated is false', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(screen.queryByText('Desactualizado')).not.toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('retry button is keyboard accessible', () => {
      render(<DocumentCardView card={partialCard} />);
      const button = screen.getByRole('button', {
        name: /reintentar análisis/i,
      });
      expect(button).toBeInTheDocument();
      // Button elements are inherently focusable and keyboard-navigable
      expect(button.tagName).toBe('BUTTON');
    });

    it('classification badge has an aria-label', () => {
      render(<DocumentCardView card={completedCard} />);
      expect(
        screen.getByLabelText(/clasificación: normativo/i),
      ).toBeInTheDocument();
    });

    it('outdated badge has an aria-label', () => {
      const outdatedCard = { ...completedCard, outdated: true };
      render(<DocumentCardView card={outdatedCard} />);
      expect(
        screen.getByLabelText(/documento desactualizado/i),
      ).toBeInTheDocument();
    });
  });
});
