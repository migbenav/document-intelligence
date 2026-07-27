import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import type { Observation } from '@/types/analysis';

export interface ConclusionsViewProps {
  observations: Observation[];
}

/** All valid observation categories in display order. */
const CATEGORY_ORDER: Observation['category'][] = [
  'coherence',
  'reordering',
  'duplication',
  'orphan',
  'missing',
];

/**
 * ConclusionsView — Displays structural observations grouped by category.
 *
 * Each observation shows the description (in ui_language), a visually distinct
 * suggestion block (in document_language), section_ref as a badge, and an
 * expandable source_ref with text excerpt and section context.
 */
export function ConclusionsView({ observations }: ConclusionsViewProps) {
  const { t } = useTranslation();

  // Group observations by category
  const grouped = CATEGORY_ORDER.reduce<
    Partial<Record<Observation['category'], Observation[]>>
  >((acc, category) => {
    const items = observations.filter((o) => o.category === category);
    if (items.length > 0) {
      acc[category] = items;
    }
    return acc;
  }, {});

  const categoryKeys = CATEGORY_ORDER.filter((cat) => grouped[cat]);

  if (observations.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="conclusions-empty">
        {t('analysis.conclusions.empty')}
      </p>
    );
  }

  return (
    <section aria-label={t('analysis.conclusions.ariaLabel')} data-testid="conclusions-view">
      <div className="space-y-6">
        {categoryKeys.map((category) => (
          <CategoryGroup
            key={category}
            category={category}
            observations={grouped[category]!}
          />
        ))}
      </div>
    </section>
  );
}

// --- Category Group ---

interface CategoryGroupProps {
  category: Observation['category'];
  observations: Observation[];
}

function CategoryGroup({ category, observations }: CategoryGroupProps) {
  const { t } = useTranslation();

  const categoryLabel = t(`analysis.conclusions.categories.${category}`);

  return (
    <div role="group" aria-labelledby={`category-heading-${category}`}>
      <h3
        id={`category-heading-${category}`}
        className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3"
      >
        {categoryLabel}
      </h3>
      <ul className="space-y-4" aria-label={categoryLabel}>
        {observations.map((observation, index) => (
          <li key={`${category}-${index}`}>
            <ObservationItem observation={observation} />
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Observation Item ---

interface ObservationItemProps {
  observation: Observation;
}

function ObservationItem({ observation }: ObservationItemProps) {
  const { t } = useTranslation();

  return (
    <article className="rounded-md border p-4 space-y-3" data-testid="observation-item">
      {/* Description in ui_language */}
      <p className="text-sm text-foreground">{observation.description}</p>

      {/* Suggestion in document_language — visually distinct */}
      {observation.suggestion && (
        <blockquote
          className="border-l-4 border-primary/30 bg-muted/50 pl-3 py-2 text-sm italic text-muted-foreground"
          aria-label={t('analysis.conclusions.suggestion')}
        >
          {observation.suggestion}
        </blockquote>
      )}

      {/* Section ref badge + expandable source ref */}
      <div className="flex items-center gap-2 flex-wrap">
        {observation.section_ref && (
          <Badge variant="secondary" aria-label={t('analysis.conclusions.sectionRef')}>
            {observation.section_ref}
          </Badge>
        )}

        {observation.source_ref && (
          <ExpandableSourceRef
            textExcerpt={observation.source_ref.text_excerpt}
            section={observation.source_ref.section}
          />
        )}
      </div>
    </article>
  );
}

// --- Expandable Source Reference ---
// Inline implementation until SourceRefPopover (task 9.5) is available.

interface ExpandableSourceRefProps {
  textExcerpt: string;
  section: string | null;
}

function ExpandableSourceRef({ textExcerpt, section }: ExpandableSourceRefProps) {
  const [expanded, setExpanded] = useState(false);
  const { t } = useTranslation();

  return (
    <div className="inline-flex flex-col">
      <Button
        variant="ghost"
        size="sm"
        className="text-xs h-auto py-1 px-2"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={t('analysis.conclusions.sourceRef')}
      >
        {expanded
          ? t('analysis.conclusions.hideSource')
          : t('analysis.conclusions.showSource')}
      </Button>

      {expanded && (
        <div className="mt-2 rounded bg-muted p-3 text-xs space-y-1">
          {section && (
            <p className="font-medium text-muted-foreground">
              {t('analysis.conclusions.sectionContext', { section })}
            </p>
          )}
          <p className="text-foreground whitespace-pre-wrap">{textExcerpt}</p>
        </div>
      )}
    </div>
  );
}
