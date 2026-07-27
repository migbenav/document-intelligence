import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import type { Observation } from '@/types/analysis';

export interface ConclusionsViewProps {
  observations: Observation[];
  domains_identified?: string[];
}

/** All valid observation categories in display order (v2 first, then v1 legacy). */
const CATEGORY_ORDER: Observation['category'][] = [
  'purpose_mismatch',
  'misplaced_content',
  'title_mismatch',
  'sequence_issue',
  'duplication',
  'contradiction',
  // v1 legacy categories
  'coherence',
  'reordering',
  'orphan',
  'missing',
];

/** Color mappings for category badges. */
const CATEGORY_COLORS: Record<Observation['category'], string> = {
  purpose_mismatch: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  misplaced_content: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  title_mismatch: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  sequence_issue: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  duplication: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  contradiction: 'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300',
  // v1 legacy colors
  coherence: 'bg-slate-100 text-slate-800 dark:bg-slate-900/30 dark:text-slate-300',
  reordering: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  orphan: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  missing: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
};

/**
 * ConclusionsView — Displays structural observations grouped by domain (v2)
 * or by category (v1 fallback).
 *
 * When observations have `domain` set, they are grouped by domain with domain
 * labels as section headers. Within each domain group, observations are ordered
 * by category. Observations without a domain are grouped by category (v1 style).
 */
export function ConclusionsView({ observations, domains_identified }: ConclusionsViewProps) {
  const { t } = useTranslation();

  if (observations.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="conclusions-empty">
        {t('analysis.conclusions.empty')}
      </p>
    );
  }

  // Check if any observations have domain set (v2 style)
  const hasDomains = observations.some((o) => o.domain);

  if (hasDomains) {
    return (
      <section aria-label={t('analysis.conclusions.ariaLabel')} data-testid="conclusions-view">
        <DomainGroupedView
          observations={observations}
          domains_identified={domains_identified ?? []}
        />
      </section>
    );
  }

  // Fallback: group by category (v1 style)
  return (
    <section aria-label={t('analysis.conclusions.ariaLabel')} data-testid="conclusions-view">
      <CategoryGroupedView observations={observations} />
    </section>
  );
}

// --- Domain-Grouped View (v2) ---

interface DomainGroupedViewProps {
  observations: Observation[];
  domains_identified: string[];
}

function DomainGroupedView({ observations, domains_identified }: DomainGroupedViewProps) {
  const { t } = useTranslation();

  // Build domain order: identified domains first, then any remaining domains from observations
  const observedDomains = [...new Set(observations.filter((o) => o.domain).map((o) => o.domain!))];
  const domainOrder = [
    ...domains_identified,
    ...observedDomains.filter((d) => !domains_identified.includes(d)),
  ];

  // Group observations by domain
  const byDomain = new Map<string, Observation[]>();
  const noDomain: Observation[] = [];

  for (const obs of observations) {
    if (obs.domain) {
      const existing = byDomain.get(obs.domain) ?? [];
      existing.push(obs);
      byDomain.set(obs.domain, existing);
    } else {
      noDomain.push(obs);
    }
  }

  return (
    <div className="space-y-6">
      {domainOrder.map((domain) => {
        const items = byDomain.get(domain);
        if (!items || items.length === 0) return null;
        return (
          <DomainSection key={domain} domain={domain} observations={items} />
        );
      })}

      {/* Observations without domain — group by category */}
      {noDomain.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
            {t('analysis.conclusions.generalObservations')}
          </h3>
          <ul className="space-y-4" aria-label={t('analysis.conclusions.generalObservations')}>
            {noDomain.map((observation, index) => (
              <li key={`no-domain-${index}`}>
                <ObservationItem observation={observation} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// --- Domain Section ---

interface DomainSectionProps {
  domain: string;
  observations: Observation[];
}

function DomainSection({ domain, observations }: DomainSectionProps) {
  // Sort observations within domain by category order
  const sorted = [...observations].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
  );

  return (
    <div role="group" aria-labelledby={`domain-heading-${domain}`}>
      <h3
        id={`domain-heading-${domain}`}
        className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3"
      >
        {domain}
      </h3>
      <ul className="space-y-4" aria-label={domain}>
        {sorted.map((observation, index) => (
          <li key={`${domain}-${index}`}>
            <ObservationItem observation={observation} />
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Category-Grouped View (v1 fallback) ---

interface CategoryGroupedViewProps {
  observations: Observation[];
}

function CategoryGroupedView({ observations }: CategoryGroupedViewProps) {
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

  return (
    <div className="space-y-6">
      {categoryKeys.map((category) => (
        <CategoryGroup
          key={category}
          category={category}
          observations={grouped[category]!}
        />
      ))}
    </div>
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

  const categoryLabel = t(`analysis.conclusions.categories.${observation.category}`);
  const colorClass = CATEGORY_COLORS[observation.category] ?? '';

  return (
    <article className="rounded-md border p-4 space-y-3" data-testid="observation-item">
      {/* Category badge */}
      <div className="flex items-center gap-2">
        <Badge className={colorClass} aria-label={categoryLabel}>
          {categoryLabel}
        </Badge>
      </div>

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
