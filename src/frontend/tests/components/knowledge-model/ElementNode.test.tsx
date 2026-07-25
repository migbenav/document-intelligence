import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ReactFlowProvider } from 'reactflow';
import { ElementNode } from '@/components/knowledge-model/ElementNode';
import type { ElementNodeData } from '@/components/knowledge-model/ElementNode';
import type { KnowledgeElementType } from '@/types/knowledgeModel';

/**
 * Helper to render ElementNode within a ReactFlowProvider (required for Handle components).
 * NodeProps requires several fields; we supply minimal mock data.
 */
function renderElementNode(data: ElementNodeData) {
  const nodeProps = {
    id: 'node-1',
    data,
    type: 'elementNode',
    selected: false,
    zIndex: 0,
    isConnectable: true,
    xPos: 0,
    yPos: 0,
    dragging: false,
  } as any; // eslint-disable-line @typescript-eslint/no-explicit-any

  return render(
    <ReactFlowProvider>
      <ElementNode {...nodeProps} />
    </ReactFlowProvider>,
  );
}

describe('ElementNode', () => {
  it('renders the element name', () => {
    renderElementNode({ name: 'User Authentication', type: 'concepto', selected: false });

    expect(screen.getByText('User Authentication')).toBeInTheDocument();
  });

  it('has appropriate aria-label with name and type label', () => {
    renderElementNode({ name: 'Login Flow', type: 'proceso', selected: false });

    expect(screen.getByRole('treeitem')).toHaveAttribute(
      'aria-label',
      'Login Flow, Process',
    );
  });

  it('sets aria-selected=true when selected', () => {
    renderElementNode({ name: 'A Rule', type: 'regla', selected: true });

    expect(screen.getByRole('treeitem')).toHaveAttribute('aria-selected', 'true');
  });

  it('sets aria-selected=false when not selected', () => {
    renderElementNode({ name: 'A Rule', type: 'regla', selected: false });

    expect(screen.getByRole('treeitem')).toHaveAttribute('aria-selected', 'false');
  });

  it('applies highlight ring class when selected', () => {
    const { container } = renderElementNode({ name: 'Test', type: 'proposito', selected: true });

    const node = container.querySelector('[role="treeitem"]');
    expect(node?.className).toContain('ring-2');
    expect(node?.className).toContain('ring-primary');
  });

  it('does not apply highlight ring class when not selected', () => {
    const { container } = renderElementNode({ name: 'Test', type: 'proposito', selected: false });

    const node = container.querySelector('[role="treeitem"]');
    expect(node?.className).not.toContain('ring-2');
  });

  describe.each<{ type: KnowledgeElementType; label: string; colorClass: string }>([
    { type: 'proposito', label: 'Purpose', colorClass: 'border-blue-400' },
    { type: 'concepto', label: 'Concept', colorClass: 'border-purple-400' },
    { type: 'actor', label: 'Actor', colorClass: 'border-green-400' },
    { type: 'regla', label: 'Rule', colorClass: 'border-orange-400' },
    { type: 'proceso', label: 'Process', colorClass: 'border-teal-400' },
    { type: 'restriccion', label: 'Constraint', colorClass: 'border-red-400' },
  ])('type: $type', ({ type, label, colorClass }) => {
    it(`renders with correct border color (${colorClass})`, () => {
      const { container } = renderElementNode({ name: 'Element', type, selected: false });

      const node = container.querySelector('[role="treeitem"]');
      expect(node?.className).toContain(colorClass);
    });

    it(`includes type label "${label}" in aria-label`, () => {
      renderElementNode({ name: 'Item', type, selected: false });

      expect(screen.getByRole('treeitem')).toHaveAttribute(
        'aria-label',
        `Item, ${label}`,
      );
    });

    it(`renders the correct data-testid`, () => {
      renderElementNode({ name: 'Node', type, selected: false });

      expect(screen.getByTestId(`element-node-${type}`)).toBeInTheDocument();
    });
  });

  it('renders source and target handles', () => {
    const { container } = renderElementNode({ name: 'Test', type: 'actor', selected: false });

    // React Flow handles have data-handlepos attributes
    const handles = container.querySelectorAll('.react-flow__handle');
    expect(handles.length).toBe(2);
  });
});
