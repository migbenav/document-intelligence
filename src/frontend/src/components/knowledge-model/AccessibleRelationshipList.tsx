import { useCallback } from 'react';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { KnowledgeElementResponse } from '@/types/knowledgeModel';

interface AccessibleRelationshipListProps {
  elements: KnowledgeElementResponse[];
}

interface RelationshipEntry {
  sourceId: string;
  sourceName: string;
  targetId: string;
  targetName: string;
  type: string;
}

/**
 * Accessible alternative to the visual React Flow graph (Req 8.3, 8.7).
 * Renders all relationships as a structured list in the format:
 * "Element A → [relationship type] → Element B"
 *
 * All element names are keyboard-navigable and trigger navigation on click/Enter.
 * This component is toggled via a button labeled "View as accessible list".
 */
export function AccessibleRelationshipList({ elements }: AccessibleRelationshipListProps) {
  const { t } = useTranslation();

  // Build a flat list of all relationships from all elements
  const relationships: RelationshipEntry[] = [];

  for (const element of elements) {
    for (const relation of element.relations) {
      const targetElement = elements.find((el) => el.id === relation.target_id);
      const targetName = targetElement?.name ?? relation.target_id;

      relationships.push({
        sourceId: element.id,
        sourceName: element.name,
        targetId: relation.target_id,
        targetName,
        type: relation.type,
      });
    }
  }

  if (relationships.length === 0) {
    return (
      <div
        className="p-4 text-center"
        data-testid="accessible-list-empty"
      >
        <p className="text-sm text-muted-foreground">
          {t('km.graph.noRelationships')}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="accessible-relationship-list" className="p-4">
      <ul role="list" className="space-y-2">
        {relationships.map((entry, index) => (
          <RelationshipListItem
            key={`${entry.sourceId}-${entry.targetId}-${entry.type}-${index}`}
            entry={entry}
          />
        ))}
      </ul>
    </div>
  );
}

interface RelationshipListItemProps {
  entry: RelationshipEntry;
}

function RelationshipListItem({ entry }: RelationshipListItemProps) {
  const { t } = useTranslation();
  const navigateToElement = useKnowledgeModelStore((s) => s.navigateToElement);

  const relationshipLabel = t(`km.relationships.${entry.type}`);

  const handleNavigate = useCallback(
    (elementId: string) => {
      navigateToElement(elementId);
    },
    [navigateToElement],
  );

  const handleKeyDown = useCallback(
    (elementId: string) => (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        navigateToElement(elementId);
      }
    },
    [navigateToElement],
  );

  return (
    <li
      className="flex items-center gap-1 text-sm flex-wrap"
      data-testid={`relationship-entry-${entry.sourceId}-${entry.targetId}`}
    >
      <span
        role="button"
        tabIndex={0}
        onClick={() => handleNavigate(entry.sourceId)}
        onKeyDown={handleKeyDown(entry.sourceId)}
        className="font-medium text-primary underline-offset-4 hover:underline cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 rounded px-1"
        aria-label={entry.sourceName}
      >
        {entry.sourceName}
      </span>

      <span className="text-muted-foreground" aria-hidden="true">→</span>

      <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
        {relationshipLabel}
      </span>

      <span className="text-muted-foreground" aria-hidden="true">→</span>

      <span
        role="button"
        tabIndex={0}
        onClick={() => handleNavigate(entry.targetId)}
        onKeyDown={handleKeyDown(entry.targetId)}
        className="font-medium text-primary underline-offset-4 hover:underline cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 rounded px-1"
        aria-label={entry.targetName}
      >
        {entry.targetName}
      </span>
    </li>
  );
}
