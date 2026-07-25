import { useMemo } from 'react';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import { TypeGroup } from './TypeGroup';
import type { KnowledgeElementResponse, KnowledgeElementType } from '@/types/knowledgeModel';

interface ElementListViewProps {
  elements: KnowledgeElementResponse[];
}

/**
 * Fixed taxonomy order for element type grouping.
 * All types are always rendered, even if the group is empty.
 */
const TAXONOMY_ORDER: KnowledgeElementType[] = [
  'proposito',
  'concepto',
  'actor',
  'regla',
  'proceso',
  'restriccion',
];

/**
 * Groups elements by their type, maintaining the fixed taxonomy order.
 */
function groupElementsByType(
  elements: KnowledgeElementResponse[],
): Record<KnowledgeElementType, KnowledgeElementResponse[]> {
  const groups: Record<KnowledgeElementType, KnowledgeElementResponse[]> = {
    proposito: [],
    concepto: [],
    actor: [],
    regla: [],
    proceso: [],
    restriccion: [],
  };

  for (const element of elements) {
    if (element.type in groups) {
      groups[element.type].push(element);
    }
  }

  return groups;
}

export function ElementListView({ elements }: ElementListViewProps) {
  const { t } = useTranslation();
  const selectedElementId = useKnowledgeModelStore((s) => s.selectedElementId);

  const groupedElements = useMemo(() => groupElementsByType(elements), [elements]);

  return (
    <nav
      aria-label={t('km.title')}
      className="space-y-4 overflow-y-auto"
      data-testid="element-list-view"
    >
      {TAXONOMY_ORDER.map((type) => (
        <TypeGroup
          key={type}
          type={type}
          elements={groupedElements[type]}
          selectedElementId={selectedElementId}
        />
      ))}
    </nav>
  );
}
