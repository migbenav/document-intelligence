import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RelationsListView } from '@/components/analysis/RelationsListView';
import { TranslationProvider } from '@/i18n';
import type { SectionRelation } from '@/types/analysis';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider locale="en">{ui}</TranslationProvider>);
}

const mockRelations: SectionRelation[] = [
  {
    source_section: 'Requirements',
    target_section: 'Implementation',
    type: 'constrains',
    description: 'Requirements constrain the implementation scope.',
    source_ref: {
      chunk_ids: ['chunk-1'],
      text_excerpt: 'All implementations must satisfy these requirements.',
      section: 'Requirements Overview',
    },
  },
  {
    source_section: 'Design',
    target_section: 'Requirements',
    type: 'depends_on',
    description: 'Design depends on finalized requirements.',
    source_ref: null,
  },
  {
    source_section: 'Appendix A',
    target_section: 'Introduction',
    type: 'complements',
    description: 'Appendix provides supporting data for the introduction.',
    source_ref: {
      chunk_ids: ['chunk-3'],
      text_excerpt: 'See supporting data below.',
      section: null,
    },
  },
  {
    source_section: 'Section 3.1',
    target_section: 'Section 4.2',
    type: 'contradicts',
    description: 'These sections present conflicting deadlines.',
    source_ref: {
      chunk_ids: ['chunk-4'],
      text_excerpt: 'Deadline is Q1 2025.',
      section: 'Timelines',
    },
  },
  {
    source_section: 'Auth Module',
    target_section: 'API Gateway',
    type: 'constrains',
    description: 'Auth module constrains API gateway configuration.',
    source_ref: null,
  },
];

describe('RelationsListView', () => {
  describe('empty state', () => {
    it('renders empty message when no relations provided', () => {
      renderWithProviders(<RelationsListView relations={[]} />);
      expect(screen.getByText('No relations were identified between sections.')).toBeInTheDocument();
    });

    it('has aria-label on the section', () => {
      renderWithProviders(<RelationsListView relations={[]} />);
      expect(screen.getByTestId('relations-list-view')).toHaveAttribute('aria-label', 'Section Relations');
    });
  });

  describe('grouping by type', () => {
    it('renders groups for all types that have relations', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      expect(screen.getByTestId('relation-group-constrains')).toBeInTheDocument();
      expect(screen.getByTestId('relation-group-depends_on')).toBeInTheDocument();
      expect(screen.getByTestId('relation-group-complements')).toBeInTheDocument();
      expect(screen.getByTestId('relation-group-contradicts')).toBeInTheDocument();
    });

    it('does not render groups for types with no relations', () => {
      const subset: SectionRelation[] = [mockRelations[0]!]; // only constrains
      renderWithProviders(<RelationsListView relations={subset} />);
      expect(screen.getByTestId('relation-group-constrains')).toBeInTheDocument();
      expect(screen.queryByTestId('relation-group-depends_on')).not.toBeInTheDocument();
      expect(screen.queryByTestId('relation-group-complements')).not.toBeInTheDocument();
      expect(screen.queryByTestId('relation-group-contradicts')).not.toBeInTheDocument();
    });

    it('shows the correct count badge per group', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      // constrains has 2 relations
      const constrainsGroup = screen.getByTestId('relation-group-constrains');
      expect(constrainsGroup).toHaveTextContent('2');
    });

    it('shows type labels as headings', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      expect(screen.getByText('Constrains (v1)')).toBeInTheDocument();
      expect(screen.getByText('Depends On (v1)')).toBeInTheDocument();
      expect(screen.getByText('Complements (v1)')).toBeInTheDocument();
      expect(screen.getByText('Contradicts')).toBeInTheDocument();
    });
  });

  describe('relation cards', () => {
    it('renders source → target path for each relation', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      const paths = screen.getAllByTestId('relation-path');
      // contradicts renders first (v2 type), then constrains, depends_on, complements (legacy)
      expect(paths[0]).toHaveTextContent('Section 3.1');
      expect(paths[0]).toHaveTextContent('Section 4.2');
    });

    it('renders description for each relation', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      expect(screen.getByText('Requirements constrain the implementation scope.')).toBeInTheDocument();
      expect(screen.getByText('Design depends on finalized requirements.')).toBeInTheDocument();
    });

    it('does not show source ref toggle when source_ref is null', () => {
      const noRef: SectionRelation[] = [mockRelations[1]!]; // depends_on with null source_ref
      renderWithProviders(<RelationsListView relations={noRef} />);
      expect(screen.queryByTestId('source-ref-expandable')).not.toBeInTheDocument();
    });
  });

  describe('expandable source reference', () => {
    it('shows the source ref toggle when source_ref is present', () => {
      const withRef: SectionRelation[] = [mockRelations[0]!]; // constrains with source_ref
      renderWithProviders(<RelationsListView relations={withRef} />);
      expect(screen.getByTestId('source-ref-toggle')).toBeInTheDocument();
      expect(screen.getByText('Show source')).toBeInTheDocument();
    });

    it('toggle has aria-expanded=false initially', () => {
      const withRef: SectionRelation[] = [mockRelations[0]!];
      renderWithProviders(<RelationsListView relations={withRef} />);
      const toggle = screen.getByTestId('source-ref-toggle');
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
    });

    it('expands to show text_excerpt on click', () => {
      const withRef: SectionRelation[] = [mockRelations[0]!];
      renderWithProviders(<RelationsListView relations={withRef} />);
      const toggle = screen.getByTestId('source-ref-toggle');
      fireEvent.click(toggle);

      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByText('All implementations must satisfy these requirements.')).toBeInTheDocument();
      expect(screen.getByText('Hide source')).toBeInTheDocument();
    });

    it('shows section context when section is present in source_ref', () => {
      const withRef: SectionRelation[] = [mockRelations[0]!];
      renderWithProviders(<RelationsListView relations={withRef} />);
      fireEvent.click(screen.getByTestId('source-ref-toggle'));

      expect(screen.getByText('Section: Requirements Overview')).toBeInTheDocument();
    });

    it('does not show section context when section is null', () => {
      const withRef: SectionRelation[] = [mockRelations[2]!]; // complements with section: null
      renderWithProviders(<RelationsListView relations={withRef} />);
      fireEvent.click(screen.getByTestId('source-ref-toggle'));

      expect(screen.getByText('See supporting data below.')).toBeInTheDocument();
      expect(screen.queryByText(/Section:/)).not.toBeInTheDocument();
    });

    it('collapses on second click', () => {
      const withRef: SectionRelation[] = [mockRelations[0]!];
      renderWithProviders(<RelationsListView relations={withRef} />);
      const toggle = screen.getByTestId('source-ref-toggle');
      fireEvent.click(toggle);
      fireEvent.click(toggle);

      expect(toggle).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByText('All implementations must satisfy these requirements.')).not.toBeInTheDocument();
    });
  });

  describe('group expand/collapse', () => {
    it('groups are expanded by default', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      // Relations should be visible
      expect(screen.getByText('Requirements constrain the implementation scope.')).toBeInTheDocument();
    });

    it('clicking group heading collapses the group', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      const constrainsButton = screen.getByRole('button', { name: /Constrains \(v1\)/i });
      fireEvent.click(constrainsButton);

      // The aria-expanded should now be false
      expect(constrainsButton).toHaveAttribute('aria-expanded', 'false');
    });

    it('clicking collapsed group heading expands it again', () => {
      renderWithProviders(<RelationsListView relations={mockRelations} />);
      const constrainsButton = screen.getByRole('button', { name: /Constrains \(v1\)/i });
      fireEvent.click(constrainsButton);
      fireEvent.click(constrainsButton);

      expect(constrainsButton).toHaveAttribute('aria-expanded', 'true');
    });
  });
});
