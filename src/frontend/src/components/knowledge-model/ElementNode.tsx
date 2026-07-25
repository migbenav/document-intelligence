import { memo } from 'react';
import { Handle, Position } from 'reactflow';
import type { NodeProps } from 'reactflow';
import {
  Target,
  Lightbulb,
  User,
  Shield,
  ArrowRightLeft,
  Lock,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { KnowledgeElementType } from '@/types/knowledgeModel';

export interface ElementNodeData {
  name: string;
  type: KnowledgeElementType;
  selected: boolean;
}

/**
 * Type configuration mapping each KnowledgeElementType to a unique color
 * AND a unique icon for color-blind accessibility (Req 8.7).
 */
const TYPE_CONFIG: Record<
  KnowledgeElementType,
  {
    icon: React.ComponentType<{ className?: string }>;
    bgColor: string;
    borderColor: string;
    iconColor: string;
    label: string;
  }
> = {
  proposito: {
    icon: Target,
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-400',
    iconColor: 'text-blue-600',
    label: 'Purpose',
  },
  concepto: {
    icon: Lightbulb,
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-400',
    iconColor: 'text-purple-600',
    label: 'Concept',
  },
  actor: {
    icon: User,
    bgColor: 'bg-green-50',
    borderColor: 'border-green-400',
    iconColor: 'text-green-600',
    label: 'Actor',
  },
  regla: {
    icon: Shield,
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-400',
    iconColor: 'text-orange-600',
    label: 'Rule',
  },
  proceso: {
    icon: ArrowRightLeft,
    bgColor: 'bg-teal-50',
    borderColor: 'border-teal-400',
    iconColor: 'text-teal-600',
    label: 'Process',
  },
  restriccion: {
    icon: Lock,
    bgColor: 'bg-red-50',
    borderColor: 'border-red-400',
    iconColor: 'text-red-600',
    label: 'Constraint',
  },
};

/**
 * Custom React Flow node representing a Knowledge Element in the relationship graph.
 *
 * Displays the element name with a type-specific icon and color.
 * Uses both color AND shape/icon per type for color-blind accessibility.
 * Highlights when selected via a ring/glow effect.
 */
function ElementNodeComponent({ data }: NodeProps<ElementNodeData>) {
  const config = TYPE_CONFIG[data.type];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'rounded-lg border-2 px-3 py-2 shadow-sm transition-shadow min-w-[140px] max-w-[200px]',
        config.bgColor,
        config.borderColor,
        data.selected && 'ring-2 ring-primary ring-offset-2 shadow-md',
      )}
      role="treeitem"
      aria-label={`${data.name}, ${config.label}`}
      aria-selected={data.selected}
      data-testid={`element-node-${data.type}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-muted-foreground !w-2 !h-2"
      />

      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4 shrink-0', config.iconColor)} aria-hidden="true" />
        <span className="text-xs font-medium leading-tight truncate">{data.name}</span>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-muted-foreground !w-2 !h-2"
      />
    </div>
  );
}

export const ElementNode = memo(ElementNodeComponent);
