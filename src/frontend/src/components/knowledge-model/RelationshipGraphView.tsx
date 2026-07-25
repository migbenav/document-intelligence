import { useMemo, useCallback, useState } from 'react';
import ReactFlow, { type Node, type Edge, type NodeTypes, type EdgeTypes } from 'reactflow';
import 'reactflow/dist/style.css';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import { applyDagreLayout } from '@/lib/graphLayout';
import { ElementNode } from './ElementNode';
import { RelationshipEdge } from './RelationshipEdge';
import { AccessibleRelationshipList } from './AccessibleRelationshipList';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';
import type { ElementNodeData } from './ElementNode';
import type { RelationshipEdgeData } from './RelationshipEdge';

interface RelationshipGraphViewProps {
  elements: KnowledgeElementResponse[];
}

const nodeTypes: NodeTypes = {
  elementNode: ElementNode,
};

const edgeTypes: EdgeTypes = {
  relationshipEdge: RelationshipEdge,
};

/**
 * React Flow graph view for Knowledge Model relationships.
 * Converts KM elements to nodes and relationships to edges,
 * applies dagre auto-layout, and enables standard interactions.
 *
 * Displays an explanatory message when no relationships exist.
 * Includes a toggle to switch to an accessible text-based list alternative.
 */
export function RelationshipGraphView({ elements }: RelationshipGraphViewProps) {
  const { t } = useTranslation();
  const selectedElementId = useKnowledgeModelStore((state) => state.selectedElementId);
  const selectElement = useKnowledgeModelStore((state) => state.selectElement);
  const [showAccessibleList, setShowAccessibleList] = useState(false);

  const { nodes, edges } = useMemo(() => {
    // Convert elements to React Flow nodes
    const rawNodes: Node<ElementNodeData>[] = elements.map((element) => ({
      id: element.id,
      type: 'elementNode',
      data: {
        name: element.name,
        type: element.type,
        selected: element.id === selectedElementId,
      },
      position: { x: 0, y: 0 },
    }));

    // Convert relationships to React Flow edges
    const rawEdges: Edge<RelationshipEdgeData>[] = [];
    const edgeIdSet = new Set<string>();

    for (const element of elements) {
      for (const relation of element.relations) {
        const edgeId = `${element.id}-${relation.target_id}-${relation.type}`;

        // Avoid duplicate forward edges (e.g., both A→B and B→A declare contradicts)
        if (!edgeIdSet.has(edgeId)) {
          edgeIdSet.add(edgeId);
          rawEdges.push({
            id: edgeId,
            source: element.id,
            target: relation.target_id,
            type: 'relationshipEdge',
            data: { type: relation.type },
          });
        }

        // For 'contradicts' type, also create a reverse edge (bidirectional)
        if (relation.type === 'contradicts') {
          const reverseEdgeId = `${relation.target_id}-${element.id}-${relation.type}`;
          if (!edgeIdSet.has(reverseEdgeId)) {
            edgeIdSet.add(reverseEdgeId);
            rawEdges.push({
              id: reverseEdgeId,
              source: relation.target_id,
              target: element.id,
              type: 'relationshipEdge',
              data: { type: relation.type },
            });
          }
        }
      }
    }

    // Apply dagre layout to position nodes
    const layoutedNodes = applyDagreLayout(rawNodes, rawEdges);

    return { nodes: layoutedNodes, edges: rawEdges };
  }, [elements, selectedElementId]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectElement(node.id);
    },
    [selectElement],
  );

  const toggleAccessibleView = useCallback(() => {
    setShowAccessibleList((prev) => !prev);
  }, []);

  // If no relationships exist, show explanatory message
  if (edges.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-full p-8 text-center"
        data-testid="graph-no-relationships"
      >
        <p className="text-muted-foreground text-sm max-w-md">
          {t('km.graph.noRelationships')}
        </p>
      </div>
    );
  }

  return (
    <div className="h-full w-full flex flex-col" data-testid="relationship-graph">
      {/* Accessible view toggle */}
      <div className="flex justify-end px-4 py-2 border-b border-border">
        <button
          type="button"
          onClick={toggleAccessibleView}
          className="text-sm text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded px-2 py-1"
          aria-pressed={showAccessibleList}
          data-testid="accessible-view-toggle"
        >
          {t('km.graph.accessibleView')}
        </button>
      </div>

      {showAccessibleList ? (
        <div className="flex-1 overflow-auto">
          <AccessibleRelationshipList elements={elements} />
        </div>
      ) : (
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodeClick={handleNodeClick}
            fitView
            minZoom={0.5}
            maxZoom={2}
          />
        </div>
      )}
    </div>
  );
}
