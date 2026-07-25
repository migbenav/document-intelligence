import type { EdgeProps } from 'reactflow';
import { getBezierPath, EdgeLabelRenderer, BaseEdge } from 'reactflow';
import { useTranslation } from '@/i18n';
import type { RelationResponse } from '@/types/knowledgeModel';

export interface RelationshipEdgeData {
  type: RelationResponse['type'];
}

/**
 * Custom React Flow edge component for Knowledge Model relationships.
 * Displays relationship type as an always-visible label on the edge.
 * Styles vary by relationship type:
 * - constrains, participates_in, depends_on: solid line, default color
 * - contradicts: dashed line, destructive color, bidirectional markers
 */
export function RelationshipEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
  style,
}: EdgeProps<RelationshipEdgeData>) {
  const { t } = useTranslation();

  const relationshipType = data?.type ?? 'depends_on';
  const label = t(`km.relationships.${relationshipType}`);

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const isContradicts = relationshipType === 'contradicts';

  // Edge styling per relationship type
  const edgeStyle: React.CSSProperties = {
    ...style,
    strokeWidth: 2,
    ...(isContradicts
      ? {
          stroke: 'hsl(0, 72%, 51%)', // red-600 equivalent — destructive color
          strokeDasharray: '5 5',
        }
      : {
          stroke: 'hsl(215, 20%, 65%)', // neutral/default edge color
        }),
  };

  // For contradicts, add bidirectional markers (both ends)
  const markerStartId = isContradicts ? 'relationship-edge-marker-contradicts' : undefined;
  const markerEndId = isContradicts
    ? 'relationship-edge-marker-contradicts'
    : (markerEnd as string | undefined);

  return (
    <>
      {/* SVG marker definition for contradicts bidirectional arrows */}
      {isContradicts && (
        <defs>
          <marker
            id="relationship-edge-marker-contradicts"
            markerWidth="8"
            markerHeight="8"
            refX="4"
            refY="4"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path
              d="M 0 0 L 8 4 L 0 8 Z"
              fill="hsl(0, 72%, 51%)"
            />
          </marker>
        </defs>
      )}

      <BaseEdge
        id={id}
        path={edgePath}
        style={edgeStyle}
        markerStart={markerStartId ? `url(#${markerStartId})` : undefined}
        markerEnd={markerEndId ? `url(#${markerEndId})` : (markerEnd as string | undefined)}
      />

      {/* Always-visible label for non-color encoding */}
      <EdgeLabelRenderer>
        <div
          data-testid={`edge-label-${id}`}
          className="pointer-events-none absolute text-xs font-medium px-1.5 py-0.5 rounded bg-background/90 border border-border shadow-sm"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            color: isContradicts ? 'hsl(0, 72%, 51%)' : undefined,
          }}
        >
          {label}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
