import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/i18n';
import { cn } from '@/lib/utils';
import type { SectionRelation, SourceRef } from '@/types/analysis';

export interface RelationsListViewProps {
  relations: SectionRelation[];
}

/** v2 relation types in display order. */
const RELATION_TYPES_V2 = ['enables', 'restricts', 'requires', 'implements', 'contradicts'] as const;

/** Legacy v1 relation types (kept for backward compat). */
const RELATION_TYPES_LEGACY = ['constrains', 'depends_on', 'complements'] as const;

/** All recognized relation types (v2 first, then legacy). */
const ALL_RELATION_TYPES = [...RELATION_TYPES_V2, ...RELATION_TYPES_LEGACY] as const;

type RelationType = (typeof ALL_RELATION_TYPES)[number];

/**
 * RelationsListView — displays section relations grouped by type.
 *
 * Each group has an expandable heading with a count badge.
 * Each relation shows "{source_section} → {target_section}" with
 * its description and an expandable source_ref section.
 */
export function RelationsListView({ relations }: RelationsListViewProps) {
  const { t } = useTranslation();

  // Group relations by type
  const grouped = ALL_RELATION_TYPES.reduce(
    (acc, type) => {
      acc[type] = relations.filter((r) => r.type === type);
      return acc;
    },
    {} as Record<RelationType, SectionRelation[]>,
  );

  // Only render groups that have relations
  const nonEmptyTypes = ALL_RELATION_TYPES.filter((type) => grouped[type].length > 0);

  if (relations.length === 0) {
    return (
      <section aria-label={t('analysis.relations.title')} data-testid="relations-list-view">
        <p className="text-sm text-muted-foreground italic">
          {t('analysis.relations.empty')}
        </p>
      </section>
    );
  }

  return (
    <section aria-label={t('analysis.relations.title')} data-testid="relations-list-view">
      <div className="space-y-4">
        {nonEmptyTypes.map((type) => (
          <RelationGroup
            key={type}
            type={type}
            relations={grouped[type]}
          />
        ))}
      </div>
    </section>
  );
}

// --- Relation Group (collapsible by type) ---

interface RelationGroupProps {
  type: RelationType;
  relations: SectionRelation[];
}

function RelationGroup({ type, relations }: RelationGroupProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(true);

  const typeLabel = t(`analysis.relations.types.${type}`);
  const count = relations.length;

  return (
    <section
      aria-labelledby={`relation-group-heading-${type}`}
      data-testid={`relation-group-${type}`}
    >
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-controls={`relation-group-content-${type}`}
        className={cn(
          'flex w-full items-center justify-between rounded-md px-3 py-2',
          'hover:bg-accent transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
      >
        <h3
          id={`relation-group-heading-${type}`}
          className="text-sm font-semibold"
        >
          {typeLabel}
        </h3>
        <Badge variant="secondary" className="ml-2">
          {count}
        </Badge>
      </button>

      <div
        id={`relation-group-content-${type}`}
        hidden={!isExpanded}
        className="mt-1 space-y-2 px-1"
      >
        {relations.map((relation, index) => (
          <RelationCard
            key={`${relation.source_section}-${relation.target_section}-${index}`}
            relation={relation}
          />
        ))}
      </div>
    </section>
  );
}

// --- Individual Relation Card ---

interface RelationCardProps {
  relation: SectionRelation;
}

function RelationCard({ relation }: RelationCardProps) {
  const { t } = useTranslation();

  return (
    <Card data-testid="relation-card">
      <CardContent className="p-3 space-y-1.5">
        <p className="text-sm font-medium" data-testid="relation-path">
          <span>{relation.source_section}</span>
          <span className="mx-1.5 text-muted-foreground" aria-hidden="true">→</span>
          <span className="sr-only"> to </span>
          <span>{relation.target_section}</span>
        </p>
        <p className="text-xs text-muted-foreground" data-testid="relation-description">
          {relation.description}
        </p>
        {relation.domain && (
          <p className="text-xs text-muted-foreground italic" data-testid="relation-domain">
            {t('analysis.relations.domain', { domain: relation.domain })}
          </p>
        )}
        {relation.source_ref && (
          <SourceRefExpandable sourceRef={relation.source_ref} />
        )}
      </CardContent>
    </Card>
  );
}

// --- Expandable Source Reference ---

interface SourceRefExpandableProps {
  sourceRef: SourceRef;
}

function SourceRefExpandable({ sourceRef }: SourceRefExpandableProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="mt-1" data-testid="source-ref-expandable">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-controls="source-ref-content"
        className={cn(
          'text-xs font-medium text-primary',
          'hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm',
        )}
        data-testid="source-ref-toggle"
      >
        {isExpanded
          ? t('analysis.relations.sourceRef.hide')
          : t('analysis.relations.sourceRef.show')}
      </button>

      {isExpanded && (
        <div
          className="mt-1.5 rounded-md border border-border bg-muted/30 p-2 text-xs"
          data-testid="source-ref-content"
        >
          <p className="text-foreground whitespace-pre-wrap">
            {sourceRef.text_excerpt}
          </p>
          {sourceRef.section && (
            <p className="mt-1 text-muted-foreground">
              {t('analysis.relations.sourceRef.section', { section: sourceRef.section })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
