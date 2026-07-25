import { Graph, layout } from '@dagrejs/dagre';
import type { Node, Edge } from 'reactflow';

const DEFAULT_NODE_WIDTH = 180;
const DEFAULT_NODE_HEIGHT = 60;

/**
 * Applies a dagre directed-graph layout to React Flow nodes and edges.
 * Uses a top-to-bottom hierarchy that minimizes edge crossings.
 *
 * @param nodes - React Flow nodes to position
 * @param edges - React Flow edges defining relationships
 * @returns A new array of nodes with updated positions from the dagre layout
 */
export function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new Graph({ directed: true });

  g.setGraph({
    rankdir: 'TB',
    nodesep: 50,
    ranksep: 80,
  });

  // Add nodes to the dagre graph
  for (const node of nodes) {
    g.setNode(node.id, {
      width: node.width ?? DEFAULT_NODE_WIDTH,
      height: node.height ?? DEFAULT_NODE_HEIGHT,
    });
  }

  // Add edges to the dagre graph
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  // Run the dagre layout algorithm
  layout(g);

  // Map back the computed positions to React Flow nodes
  return nodes.map((node) => {
    const nodeWithPosition = g.node(node.id);

    if (!nodeWithPosition) {
      return node;
    }

    // Dagre gives center coordinates; React Flow uses top-left origin.
    // Offset by half the node dimensions to convert.
    const width = node.width ?? DEFAULT_NODE_WIDTH;
    const height = node.height ?? DEFAULT_NODE_HEIGHT;

    return {
      ...node,
      position: {
        x: (nodeWithPosition.x ?? 0) - width / 2,
        y: (nodeWithPosition.y ?? 0) - height / 2,
      },
    };
  });
}
