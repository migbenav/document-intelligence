import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { IndexTreeView } from '@/components/analysis/IndexTreeView';
import { TranslationProvider } from '@/i18n';
import type { StructureNode } from '@/types/analysis';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider locale="en">{ui}</TranslationProvider>);
}

const mockTree: StructureNode[] = [
  {
    id: 'node-1',
    title: 'Introduction',
    level: 1,
    role: 'overview',
    question_answered: 'What is this document about?',
    source_ref: {
      chunk_ids: ['chunk-1'],
      text_excerpt: 'This document introduces the system.',
      section: 'Intro Section',
    },
    children: [
      {
        id: 'node-1-1',
        title: 'Background',
        level: 2,
        role: null,
        question_answered: null,
        source_ref: null,
        children: [],
      },
    ],
  },
  {
    id: 'node-2',
    title: 'Requirements',
    level: 1,
    role: 'specification',
    question_answered: null,
    source_ref: null,
    children: [],
  },
];

describe('IndexTreeView', () => {
  describe('rendering', () => {
    it('renders empty state when tree is empty', () => {
      renderWithProviders(<IndexTreeView tree={[]} />);
      expect(screen.getByTestId('index-tree-empty')).toBeInTheDocument();
    });

    it('renders a tree with role="tree"', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      expect(screen.getByRole('tree')).toBeInTheDocument();
    });

    it('renders all top-level nodes as treeitems', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      expect(screen.getByTestId('tree-node-node-1')).toBeInTheDocument();
      expect(screen.getByTestId('tree-node-node-2')).toBeInTheDocument();
    });

    it('displays the title of each node', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      expect(screen.getByText('Introduction')).toBeInTheDocument();
      expect(screen.getByText('Requirements')).toBeInTheDocument();
    });

    it('shows a role badge when role is present', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      expect(screen.getByText('overview')).toBeInTheDocument();
      expect(screen.getByText('specification')).toBeInTheDocument();
    });

    it('shows question_answered in italic when present', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      expect(screen.getByText('What is this document about?')).toBeInTheDocument();
    });
  });

  describe('expand/collapse', () => {
    it('does not show children or source_ref initially', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      expect(screen.queryByTestId('tree-node-node-1-1')).not.toBeInTheDocument();
      expect(screen.queryByTestId('source-ref-inline')).not.toBeInTheDocument();
    });

    it('expands node on click to show children and source_ref', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const nodeHeader = screen.getByLabelText('Introduction');
      fireEvent.click(nodeHeader);

      expect(screen.getByTestId('tree-node-node-1-1')).toBeInTheDocument();
      expect(screen.getByText('Background')).toBeInTheDocument();
      expect(screen.getByTestId('source-ref-inline')).toBeInTheDocument();
      expect(screen.getByText('This document introduces the system.')).toBeInTheDocument();
      expect(screen.getByText('Intro Section')).toBeInTheDocument();
    });

    it('collapses node on second click', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const nodeHeader = screen.getByLabelText('Introduction');
      fireEvent.click(nodeHeader);
      fireEvent.click(nodeHeader);

      expect(screen.queryByTestId('tree-node-node-1-1')).not.toBeInTheDocument();
    });

    it('sets aria-expanded on expandable nodes', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const node1 = screen.getByTestId('tree-node-node-1');
      expect(node1).toHaveAttribute('aria-expanded', 'false');

      fireEvent.click(screen.getByLabelText('Introduction'));
      expect(node1).toHaveAttribute('aria-expanded', 'true');
    });
  });

  describe('keyboard navigation', () => {
    it('expands node with Enter key', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const nodeHeader = screen.getByLabelText('Introduction');
      fireEvent.keyDown(nodeHeader, { key: 'Enter' });

      expect(screen.getByTestId('tree-node-node-1-1')).toBeInTheDocument();
    });

    it('expands node with Space key', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const nodeHeader = screen.getByLabelText('Introduction');
      fireEvent.keyDown(nodeHeader, { key: ' ' });

      expect(screen.getByTestId('tree-node-node-1-1')).toBeInTheDocument();
    });

    it('expands with ArrowRight when collapsed', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const nodeHeader = screen.getByLabelText('Introduction');
      fireEvent.keyDown(nodeHeader, { key: 'ArrowRight' });

      expect(screen.getByTestId('tree-node-node-1')).toHaveAttribute('aria-expanded', 'true');
    });

    it('collapses with ArrowLeft when expanded', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const nodeHeader = screen.getByLabelText('Introduction');
      fireEvent.keyDown(nodeHeader, { key: 'ArrowRight' });
      fireEvent.keyDown(nodeHeader, { key: 'ArrowLeft' });

      expect(screen.getByTestId('tree-node-node-1')).toHaveAttribute('aria-expanded', 'false');
    });

    it('does nothing for ArrowLeft on already collapsed node', () => {
      renderWithProviders(<IndexTreeView tree={mockTree} />);
      const nodeHeader = screen.getByLabelText('Introduction');
      fireEvent.keyDown(nodeHeader, { key: 'ArrowLeft' });

      expect(screen.getByTestId('tree-node-node-1')).toHaveAttribute('aria-expanded', 'false');
    });
  });

  describe('non-expandable nodes', () => {
    it('node without children or source_ref has no aria-expanded', () => {
      const leafTree: StructureNode[] = [
        {
          id: 'leaf-1',
          title: 'Leaf Node',
          level: 1,
          role: null,
          question_answered: null,
          source_ref: null,
          children: [],
        },
      ];
      renderWithProviders(<IndexTreeView tree={leafTree} />);
      const node = screen.getByTestId('tree-node-leaf-1');
      expect(node).not.toHaveAttribute('aria-expanded');
    });
  });
});
