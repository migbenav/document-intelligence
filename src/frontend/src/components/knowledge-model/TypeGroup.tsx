import { useState } from 'react';
import { useTranslation } from '@/i18n';
import { cn } from '@/lib/utils';
import { ElementCard } from './ElementCard';
import type { KnowledgeElementType, KnowledgeElementResponse } from '@/types/knowledgeModel';

interface TypeGroupProps {
  type: KnowledgeElementType;
  elements: KnowledgeElementResponse[];
  selectedElementId: string | null;
}

export function TypeGroup({ type, elements, selectedElementId }: TypeGroupProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(true);

  const count = elements.length;
  const typeName = t(`km.typeGroups.${type}`);
  const countLabel = count > 0
    ? t('km.count.elements', { count: String(count) })
    : t('km.count.noElements');

  return (
    <section
      aria-labelledby={`type-group-heading-${type}`}
      data-testid={`type-group-${type}`}
    >
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-controls={`type-group-content-${type}`}
        className={cn(
          'flex w-full items-center justify-between rounded-md px-3 py-2',
          'hover:bg-accent transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
      >
        <h3
          id={`type-group-heading-${type}`}
          className="text-sm font-semibold"
        >
          {typeName}
        </h3>
        <span className={cn(
          'ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
          count > 0
            ? 'bg-muted text-muted-foreground'
            : 'bg-muted/50 text-muted-foreground/70',
        )}>
          {countLabel}
        </span>
      </button>

      {count === 0 ? (
        <div
          id={`type-group-content-${type}`}
          hidden={!isExpanded}
          className="mt-1 space-y-2 px-1"
        >
          <p className="px-3 py-2 text-xs text-muted-foreground/70 italic">
            {t('km.count.noElements')}
          </p>
        </div>
      ) : (
        <div
          id={`type-group-content-${type}`}
          role="listbox"
          aria-label={typeName}
          hidden={!isExpanded}
          className="mt-1 space-y-2 px-1"
        >
          {elements.map((element) => (
            <ElementCard
              key={element.id}
              element={element}
              isSelected={element.id === selectedElementId}
            />
          ))}
        </div>
      )}
    </section>
  );
}
