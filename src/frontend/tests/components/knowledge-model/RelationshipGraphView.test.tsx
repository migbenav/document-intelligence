import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RelationshipGraphView } from '@/components/knowledge-model/RelationshipGraphView';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

// Mock React Flow since it requires DOM measurements not available in jsdom
vi.mock('reactflow', async () => {
  const actual = await vi.importActual<typeof import('reactflow')>('reactflow');
  return {
    ...actual,
    default: ({ nodes, edges, onNodeClick }: any) => (
      <div data-testid="mock-react-flow" data-node-count={nodes.length} data-edge-count={edges.length}>
        {nodes.map((node: any) => (
          <div
            key={node.id}
            data-testid={`flow-node-${node.id}`}
            data-node-type={node.type}
            data-selected={node.data.selected}
            onClick={(e) => onNodeClick?.(e, node)}
          >
            {node.data.name}
          </div>
        ))}
        {edges.map((edge: any) => (
          <div
            key={edge.id}
            data-testid={`flow-edge-${edge.id}`}
            data-edge-type={edge.type}
            data-source={edge.source}
            data-target={edge.target}
            data-relation-type={edge.data?.type}
          />
        ))}
      </div>
    ),
    ReactFlowProvider: ({ children }: any) => <>{children}</>,
  };
});

// Mock dagre layout to return nodes with deterministic positions
vi.mock('@/lib/graphLayout', () => ({
  applyDagreLayout: (nodes: any[], _edges: any[]) =>
    nodes.map((node: any, index: number) => ({
      ...node,
      position: { x: index * 100, y: index * 50 },
    })),
}));

function renderComponent(elements: KnowledgeElementResponse[]) {
  return render(
    <TranslationProvider locale="en">
      <RelationshipGraphView elements={elements} />
    </TranslationProvider>,
  );
}

function createTestElement(overrides: Partial<KnowledgeElementResponse> = {}): KnowledgeElementResponse {
  return {
    id: 'el-1',
    type: 'concepto',
    name: 'Test Element',
    content: 'Content of the element',
    source_ref: {
      document_id: 'doc-1',
      chunk_id: 'chunk-1',
      page: 1,
      section: 'Section A',
      evidence: 'Evidence text',
    },
    relations: [],
    verified: true,
    ...overrides,
  };
}

describe('RelationshipGraphView', () => {
  beforeEach(() => {
    useKnowledgeModelStore.setState({
      selectedElementId: null,
    });
  });

  describe('Empty relationships', () => {
    it('displays explanatory message when no relationships exist', () => {
      const elements = [
        createTestElement({ id: 'el-1', name: 'Element A', relations: [] }),
        createTestElement({ id: 'el-2', name: 'Element B', relations: [] }),
      ];

      renderComponent(elements);

      expect(screen.getByTestId('graph-no-relationships')).toBeInTheDocument();
      expect(screen.getByText(/No relationships were identified/)).toBeInTheDocument();
    });

    it('does not render graph when no relationships exist', () => {
      const elements = [createTestElement({ id: 'el-1', relations: [] })];

      renderComponent(elements);

      expect(screen.queryByTestId('relationship-graph')).not.toBeInTheDocument();
    });
  });

  describe('Graph rendering', () => {
    const elementsWithRelations: KnowledgeElementResponse[] = [
      createTestElement({
        id: 'el-1',
        name: 'Purpose A',
        type: 'proposito',
        relations: [{ target_id: 'el-2', type: 'depends_on', description: null }],
      }),
      createTestElement({
        id: 'el-2',
        name: 'Concept B',
        type: 'concepto',
        relations: [],
      }),
    ];

    it('renders graph container when relationships exist', () => {
      renderComponent(elementsWithRelations);

      expect(screen.getByTestId('relationship-graph')).toBeInTheDocument();
    });

    it('converts elements to nodes with correct type', () => {
      renderComponent(elementsWithRelations);

      const node1 = screen.getByTestId('flow-node-el-1');
      expect(node1).toHaveAttribute('data-node-type', 'elementNode');
      expect(node1).toHaveTextContent('Purpose A');

      const node2 = screen.getByTestId('flow-node-el-2');
      expect(node2).toHaveAttribute('data-node-type', 'elementNode');
      expect(node2).toHaveTextContent('Concept B');
    });

    it('converts relationships to edges with correct type', () => {
      renderComponent(elementsWithRelations);

      const edge = screen.getByTestId('flow-edge-el-1-el-2-depends_on');
      expect(edge).toHaveAttribute('data-edge-type', 'relationshipEdge');
      expect(edge).toHaveAttribute('data-source', 'el-1');
      expect(edge).toHaveAttribute('data-target', 'el-2');
      expect(edge).toHaveAttribute('data-relation-type', 'depends_on');
    });

    it('creates bidirectional edges for contradicts relationships', () => {
      const elements: KnowledgeElementResponse[] = [
        createTestElement({
          id: 'el-1',
          name: 'Rule A',
          type: 'regla',
          relations: [{ target_id: 'el-2', type: 'contradicts', description: null }],
        }),
        createTestElement({
          id: 'el-2',
          name: 'Rule B',
          type: 'regla',
          relations: [],
        }),
      ];

      renderComponent(elements);

      // Forward edge
      expect(screen.getByTestId('flow-edge-el-1-el-2-contradicts')).toBeInTheDocument();
      // Reverse edge (bidirectional)
      expect(screen.getByTestId('flow-edge-el-2-el-1-contradicts')).toBeInTheDocument();
    });

    it('reports correct node and edge counts', () => {
      renderComponent(elementsWithRelations);

      const flow = screen.getByTestId('mock-react-flow');
      expect(flow).toHaveAttribute('data-node-count', '2');
      expect(flow).toHaveAttribute('data-edge-count', '1');
    });
  });

  describe('Node selection', () => {
    const elements: KnowledgeElementResponse[] = [
      createTestElement({
        id: 'el-1',
        name: 'Element A',
        relations: [{ target_id: 'el-2', type: 'participates_in', description: null }],
      }),
      createTestElement({
        id: 'el-2',
        name: 'Element B',
        relations: [],
      }),
    ];

    it('calls selectElement when a node is clicked', () => {
      renderComponent(elements);

      fireEvent.click(screen.getByTestId('flow-node-el-1'));

      expect(useKnowledgeModelStore.getState().selectedElementId).toBe('el-1');
    });

    it('passes selected state to node data based on store', () => {
      useKnowledgeModelStore.setState({ selectedElementId: 'el-2' });

      renderComponent(elements);

      expect(screen.getByTestId('flow-node-el-1')).toHaveAttribute('data-selected', 'false');
      expect(screen.getByTestId('flow-node-el-2')).toHaveAttribute('data-selected', 'true');
    });
  });

  describe('Deduplication of contradicts edges', () => {
    it('does not create duplicate reverse edges if both elements declare the contradicts relation', () => {
      const elements: KnowledgeElementResponse[] = [
        createTestElement({
          id: 'el-1',
          name: 'Rule A',
          type: 'regla',
          relations: [{ target_id: 'el-2', type: 'contradicts', description: null }],
        }),
        createTestElement({
          id: 'el-2',
          name: 'Rule B',
          type: 'regla',
          relations: [{ target_id: 'el-1', type: 'contradicts', description: null }],
        }),
      ];

      renderComponent(elements);

      const flow = screen.getByTestId('mock-react-flow');
      // el-1 → el-2 (from el-1's relations) + el-2 → el-1 (reverse of el-1's relation)
      // el-2 → el-1 (from el-2's relations - but already exists from reverse) + el-1 → el-2 (reverse of el-2's - but already exists)
      // The forward el-2→el-1 edge is created from el-2's own relation (different from the reverse)
      // Total: 2 forward edges + any non-duplicate reverses
      // The id for el-2's relation: "el-2-el-1-contradicts" - this matches the reverse from el-1
      // So it's created as a regular edge, and the reverse "el-1-el-2-contradicts" already exists
      // Result: 2 edges total (el-1-el-2-contradicts from forward, el-2-el-1-contradicts from forward of el-2 or reverse of el-1)
      expect(flow).toHaveAttribute('data-edge-count', '2');
    });
  });
});
