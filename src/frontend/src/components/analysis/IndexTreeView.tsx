import { useState, useCallback } from 'react';
import { ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { StructureNode, SourceRef } from '@/types/analysis';

// --- Props ---

export interface IndexTreeViewProps {
  /** The top-level tree nodes to render. */
  tree: StructureNode[];
}

/**
 * IndexTreeView — renders a StructureNode tree as an accessible,
 * expandable/collapsible tree widget with keyboard navigation.
 *
 * Requirements: Req 8 (criterion 1), Req 9 (criterion 2)
 */
export function IndexTreeView({ tree }: IndexTreeViewProps) {
  if (tree.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic" data-testid="index-tree-empty">
        No structure data available.
      </p>
    );
  }

  return (
    <ul role="tree" aria-label="Document structure" data-testid="index-tree" className="space-y-1">
      {tree.map((node) => (
        <TreeNode key={node.id} node={node} level={1} />
      ))}
    </ul>
  );
}

// --- Recursive TreeNode ---

interface TreeNodeProps {
  node: StructureNode;
  level: number;
}

function TreeNode({ node, level }: TreeNodeProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasChildren = node.children.length > 0;
  const hasExpandableContent = hasChildren || node.source_ref !== null;

  const toggle = useCallback(() => {
    if (hasExpandableContent) {
      setIsExpanded((prev) => !prev);
    }
  }, [hasExpandableContent]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'Enter':
        case ' ':
          if (hasExpandableContent) {
            e.preventDefault();
            toggle();
          }
          break;
        case 'ArrowRight':
          if (hasExpandableContent && !isExpanded) {
            e.preventDefault();
            setIsExpanded(true);
          }
          break;
        case 'ArrowLeft':
          if (isExpanded) {
            e.preventDefault();
            setIsExpanded(false);
          }
          break;
      }
    },
    [hasExpandableContent, isExpanded, toggle],
  );

  return (
    <li
      role="treeitem"
      aria-expanded={hasExpandableContent ? isExpanded : undefined}
      aria-level={level}
      data-testid={`tree-node-${node.id}`}
    >
      {/* Node header — clickable row */}
      <div
        className={cn(
          'flex items-start gap-1.5 rounded-md px-2 py-1.5 cursor-pointer',
          'hover:bg-accent transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
        style={{ paddingLeft: `${(level - 1) * 1.25 + 0.5}rem` }}
        tabIndex={0}
        onClick={toggle}
        onKeyDown={handleKeyDown}
        aria-label={node.title}
      >
        {/* Expand/collapse chevron */}
        <span className="mt-0.5 shrink-0 w-4 h-4 flex items-center justify-center">
          {hasExpandableContent ? (
            <ChevronRight
              className={cn(
                'h-3.5 w-3.5 text-muted-foreground transition-transform',
                isExpanded && 'rotate-90',
              )}
              aria-hidden="true"
            />
          ) : (
            <span className="w-3.5" />
          )}
        </span>

        {/* Node content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{node.title}</span>
            {node.role && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {node.role}
              </Badge>
            )}
          </div>
          {node.question_answered && (
            <p className="text-xs text-muted-foreground italic mt-0.5 truncate">
              {node.question_answered}
            </p>
          )}
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="ml-4" style={{ paddingLeft: `${(level - 1) * 1.25 + 0.5}rem` }}>
          {/* Source reference display */}
          {node.source_ref && (
            <SourceRefInline sourceRef={node.source_ref} />
          )}

          {/* Recursive children */}
          {hasChildren && (
            <ul role="group" className="space-y-0.5 mt-1">
              {node.children.map((child) => (
                <TreeNode key={child.id} node={child} level={level + 1} />
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

// --- SourceRef inline display (placeholder until SourceRefPopover is created) ---

interface SourceRefInlineProps {
  sourceRef: SourceRef;
}

function SourceRefInline({ sourceRef }: SourceRefInlineProps) {
  return (
    <div
      className="mt-1 mb-1.5 rounded border border-border bg-muted/40 px-3 py-2 text-xs"
      data-testid="source-ref-inline"
    >
      {sourceRef.section && (
        <span className="block text-muted-foreground font-medium mb-0.5">
          {sourceRef.section}
        </span>
      )}
      <span className="text-muted-foreground leading-relaxed line-clamp-3">
        {sourceRef.text_excerpt}
      </span>
    </div>
  );
}
