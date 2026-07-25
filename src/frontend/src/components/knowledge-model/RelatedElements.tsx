import { useCallback } from 'react';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type {
  KnowledgeElementResponse,
  RelationResponse,
} from '@/types/knowledgeModel';

interface RelatedElementsProps {
  relations: RelationResponse[];
  allElements: KnowledgeElementResponse[];
}

/**
 * Displays the list of related elements for the currently selected element.
 * Each item shows the target element's name, type badge, and relationship type.
 * Clicking or pressing Enter/Space navigates to the target element (pushes to history).
 */
export function RelatedElements({ relations, allElements }: RelatedElementsProps) {
  const { t } = useTranslation();

  if (relations.length === 0) {
    return (
      <section aria-labelledby="related-elements-heading" data-testid="related-elements">
        <h3
          id="related-elements-heading"
          className="text-sm font-semibold mb-2"
        >
          {t('km.element.relatedElements')}
        </h3>
        <p className="text-sm text-muted-foreground" data-testid="no-related-elements">
          {t('km.element.noRelatedElements')}
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="related-elements-heading" data-testid="related-elements">
      <h3
        id="related-elements-heading"
        className="text-sm font-semibold mb-2"
      >
        {t('km.element.relatedElements')}
      </h3>
      <ul className="space-y-1" role="list">
        {relations.map((relation) => (
          <RelatedElementItem
            key={relation.target_id}
            relation={relation}
            allElements={allElements}
          />
        ))}
      </ul>
    </section>
  );
}

interface RelatedElementItemProps {
  relation: RelationResponse;
  allElements: KnowledgeElementResponse[];
}

function RelatedElementItem({ relation, allElements }: RelatedElementItemProps) {
  const { t } = useTranslation();
  const navigateToElement = useKnowledgeModelStore((s) => s.navigateToElement);

  const targetElement = allElements.find((el) => el.id === relation.target_id);

  const handleNavigate = useCallback(() => {
    navigateToElement(relation.target_id);
  }, [navigateToElement, relation.target_id]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        navigateToElement(relation.target_id);
      }
    },
    [navigateToElement, relation.target_id],
  );

  const elementName = targetElement?.name ?? relation.target_id;
  const elementType = targetElement?.type;
  const relationshipLabel = t(`km.relationships.${relation.type}`);
  const typeLabel = elementType ? t(`km.typeGroups.${elementType}`) : null;

  return (
    <li
      tabIndex={0}
      role="button"
      onClick={handleNavigate}
      onKeyDown={handleKeyDown}
      className="flex items-center gap-2 rounded-md px-3 py-2 text-sm cursor-pointer transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`${elementName}, ${typeLabel ?? ''}, ${relationshipLabel}`}
      data-testid={`related-element-${relation.target_id}`}
    >
      {typeLabel && (
        <span className="inline-flex shrink-0 items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {typeLabel}
        </span>
      )}
      <span className="flex-1 truncate font-medium">{elementName}</span>
      <span className="shrink-0 text-xs text-muted-foreground">
        {relationshipLabel}
      </span>
    </li>
  );
}
