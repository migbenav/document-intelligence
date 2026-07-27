import { useState, useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { AnsweredQuestion, SourceRef } from '@/types/analysis';

export interface QuestionsCascadeViewProps {
  documentQuestions: AnsweredQuestion[];
  sectionQuestions: AnsweredQuestion[];
}

/**
 * QuestionsCascadeView displays a cascade of questions the document answers.
 *
 * - Document-level questions are displayed prominently at the top (larger text, distinct styling).
 * - Section-level questions are grouped under their parent section title.
 * - Each question is expandable/collapsible to reveal source_ref details.
 */
export function QuestionsCascadeView({
  documentQuestions,
  sectionQuestions,
}: QuestionsCascadeViewProps) {
  // Group section questions by section_title
  const sectionGroups = groupBySectionTitle(sectionQuestions);

  return (
    <div className="space-y-6" data-testid="questions-cascade-view">
      {/* Document-level questions */}
      {documentQuestions.length > 0 && (
        <section aria-labelledby="document-questions-heading">
          <h2
            id="document-questions-heading"
            className="text-lg font-semibold mb-3"
          >
            Document Questions
          </h2>
          <div className="space-y-2">
            {documentQuestions.map((q, idx) => (
              <QuestionItem
                key={`doc-${idx}`}
                question={q}
                variant="document"
              />
            ))}
          </div>
        </section>
      )}

      {/* Section-level questions grouped by section_title */}
      {sectionGroups.length > 0 && (
        <section aria-labelledby="section-questions-heading">
          <h2
            id="section-questions-heading"
            className="text-lg font-semibold mb-3"
          >
            Section Questions
          </h2>
          <div className="space-y-4">
            {sectionGroups.map(([sectionTitle, questions]) => (
              <SectionGroup
                key={sectionTitle}
                sectionTitle={sectionTitle}
                questions={questions}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// --- Internal components ---

interface SectionGroupProps {
  sectionTitle: string;
  questions: AnsweredQuestion[];
}

function SectionGroup({ sectionTitle, questions }: SectionGroupProps) {
  return (
    <div data-testid={`section-group-${sectionTitle}`}>
      <h3 className="text-sm font-medium text-muted-foreground mb-2">
        {sectionTitle}
      </h3>
      <div className="space-y-2 pl-3 border-l-2 border-muted">
        {questions.map((q, idx) => (
          <QuestionItem
            key={`section-${sectionTitle}-${idx}`}
            question={q}
            variant="section"
          />
        ))}
      </div>
    </div>
  );
}

interface QuestionItemProps {
  question: AnsweredQuestion;
  variant: 'document' | 'section';
}

function QuestionItem({ question, variant }: QuestionItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasSourceRef = question.source_ref !== null;

  const handleToggle = useCallback(() => {
    if (hasSourceRef) {
      setIsExpanded((prev) => !prev);
    }
  }, [hasSourceRef]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.key === 'Enter' || e.key === ' ') && hasSourceRef) {
        e.preventDefault();
        setIsExpanded((prev) => !prev);
      }
    },
    [hasSourceRef],
  );

  const isDocument = variant === 'document';

  return (
    <Card
      className={cn(
        isDocument && 'border-primary/20 bg-primary/5',
      )}
      data-testid="question-item"
    >
      <CardContent className="p-3">
        <div
          role={hasSourceRef ? 'button' : undefined}
          tabIndex={hasSourceRef ? 0 : undefined}
          onClick={handleToggle}
          onKeyDown={handleKeyDown}
          aria-expanded={hasSourceRef ? isExpanded : undefined}
          className={cn(
            'flex items-start gap-2',
            hasSourceRef && 'cursor-pointer',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 rounded-sm',
          )}
          data-testid="question-toggle"
        >
          {/* Expand/collapse indicator */}
          {hasSourceRef && (
            <span
              className="mt-0.5 text-muted-foreground shrink-0"
              aria-hidden="true"
            >
              {isExpanded ? (
                <ChevronDownIcon />
              ) : (
                <ChevronRightIcon />
              )}
            </span>
          )}

          <span
            className={cn(
              'flex-1',
              isDocument ? 'text-base font-medium' : 'text-sm',
            )}
          >
            {question.question}
          </span>

          {!hasSourceRef && (
            <Badge
              variant="outline"
              className="shrink-0 text-xs"
              data-testid="unverified-badge"
            >
              Unverified
            </Badge>
          )}
        </div>

        {/* Source reference details (expanded state) */}
        {isExpanded && hasSourceRef && (
          <SourceRefDetails sourceRef={question.source_ref!} />
        )}
      </CardContent>
    </Card>
  );
}

interface SourceRefDetailsProps {
  sourceRef: SourceRef;
}

function SourceRefDetails({ sourceRef }: SourceRefDetailsProps) {
  return (
    <div
      className="mt-2 ml-6 rounded-md bg-muted/50 p-3 text-sm"
      data-testid="source-ref-details"
    >
      <p className="text-foreground italic">&ldquo;{sourceRef.text_excerpt}&rdquo;</p>
      {sourceRef.section && (
        <p className="mt-1 text-xs text-muted-foreground">
          Section: {sourceRef.section}
        </p>
      )}
    </div>
  );
}

// --- Utility ---

function groupBySectionTitle(
  questions: AnsweredQuestion[],
): [string, AnsweredQuestion[]][] {
  const groups = new Map<string, AnsweredQuestion[]>();

  for (const q of questions) {
    const key = q.section_title ?? 'Other';
    const existing = groups.get(key);
    if (existing) {
      existing.push(q);
    } else {
      groups.set(key, [q]);
    }
  }

  return Array.from(groups.entries());
}

// --- Icons ---

function ChevronRightIcon() {
  return (
    <svg
      className="h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={2}
      stroke="currentColor"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg
      className="h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={2}
      stroke="currentColor"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}
