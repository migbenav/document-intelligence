/**
 * Backward compatibility tests for Analysis Quality v2 frontend components.
 *
 * Verifies that:
 * 1. Frontend components render v1 analysis results (without v2 optional fields) without errors
 * 2. Conditional rendering handles missing optional fields gracefully
 * 3. Both v1 and v2 results display correctly in the same UI
 *
 * Requirements: Design Decision 1 (backward compat), Property 4
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TranslationProvider } from '@/i18n';
import { IndexTreeView } from '@/components/analysis/IndexTreeView';
import { QuestionsCascadeView } from '@/components/analysis/QuestionsCascadeView';
import { ConclusionsView } from '@/components/analysis/ConclusionsView';
import { RelationsListView } from '@/components/analysis/RelationsListView';
import { AnalysisResultView } from '@/components/analysis/AnalysisResultView';
import type {
  StructureNode,
  AnsweredQuestion,
  Observation,
  SectionRelation,
  IndexResult,
  QuestionsResult,
  ConclusionsResult,
  RelationsResult,
} from '@/types/analysis';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider locale="en">{ui}</TranslationProvider>);
}

// --- V1 test data (without v2-only fields) ---

/** v1 StructureNode: no functional_group, no original_headings */
const v1Tree: StructureNode[] = [
  {
    id: 'n1',
    title: 'Capítulo 1 - Introducción',
    level: 1,
    role: 'describes',
    question_answered: 'What does the introduction cover?',
    source_ref: {
      chunk_ids: ['c1'],
      text_excerpt: 'Este documento describe...',
      section: 'Introducción',
    },
    children: [
      {
        id: 'n1-1',
        title: '1.1 Alcance',
        level: 2,
        role: 'defines',
        question_answered: null,
        source_ref: null,
        children: [],
      },
    ],
  },
  {
    id: 'n2',
    title: 'Capítulo 2 - Reglas',
    level: 1,
    role: 'regulates',
    question_answered: 'What rules are established?',
    source_ref: null,
    children: [],
  },
];

/** v1 Questions: no coherence_note */
const v1DocumentQuestions: AnsweredQuestion[] = [
  {
    question: '¿Cuál es el propósito del documento?',
    level: 'document',
    section_title: null,
    source_ref: {
      chunk_ids: ['c1'],
      text_excerpt: 'El propósito de este reglamento...',
      section: 'Introducción',
    },
  },
  {
    question: '¿Qué regula este documento?',
    level: 'document',
    section_title: null,
    source_ref: null,
  },
];

const v1SectionQuestions: AnsweredQuestion[] = [
  {
    question: '¿Quién aprueba los gastos?',
    level: 'section',
    section_title: 'Capítulo 3',
    source_ref: null,
  },
];

/** v1 Observations: v1 categories, no domain */
const v1Observations: Observation[] = [
  {
    category: 'coherence',
    description: 'The document lacks a clear structure.',
    suggestion: 'Reorganize chapters by theme.',
    section_ref: 'Capítulo 2',
    domain: null,
    source_ref: {
      chunk_ids: ['c5'],
      text_excerpt: 'Los artículos sobre estacionamiento...',
      section: 'Capítulo 2',
    },
  },
  {
    category: 'reordering',
    description: 'Chapter 5 should come before Chapter 3.',
    suggestion: 'Move Chapter 5 before Chapter 3.',
    section_ref: 'Capítulo 5',
    domain: null,
    source_ref: null,
  },
];

/** v1 Relations: legacy types (depends_on, complements, constrains), no domain */
const v1Relations: SectionRelation[] = [
  {
    source_section: 'Capítulo 1',
    target_section: 'Capítulo 3',
    type: 'depends_on',
    description: 'Chapter 3 uses definitions from Chapter 1.',
    source_ref: {
      chunk_ids: ['c3'],
      text_excerpt: 'Como se define en el Capítulo 1...',
      section: null,
    },
  },
  {
    source_section: 'Sección 2.1',
    target_section: 'Sección 2.3',
    type: 'complements',
    description: 'These sections complement each other.',
    source_ref: null,
  },
];

// --- Tests ---

describe('Backward Compatibility: IndexTreeView with v1 data', () => {
  it('renders v1 tree (no functional_group, no original_headings) without errors', () => {
    renderWithProviders(<IndexTreeView tree={v1Tree} />);
    expect(screen.getByRole('tree')).toBeInTheDocument();
    expect(screen.getByText('Capítulo 1 - Introducción')).toBeInTheDocument();
    expect(screen.getByText('Capítulo 2 - Reglas')).toBeInTheDocument();
  });

  it('does not render functional_group label when absent', () => {
    renderWithProviders(<IndexTreeView tree={v1Tree} />);
    expect(screen.queryByTestId('functional-group-n1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('functional-group-n2')).not.toBeInTheDocument();
  });

  it('does not render original_headings section when absent', () => {
    renderWithProviders(<IndexTreeView tree={v1Tree} />);
    // Expand the first node
    fireEvent.click(screen.getByLabelText('Capítulo 1 - Introducción'));
    expect(screen.queryByTestId('original-headings-n1')).not.toBeInTheDocument();
  });

  it('renders without documentPurpose prop (v1 has no document_purpose)', () => {
    renderWithProviders(<IndexTreeView tree={v1Tree} />);
    expect(screen.queryByTestId('index-tree-purpose')).not.toBeInTheDocument();
  });

  it('renders v1 role badges correctly', () => {
    renderWithProviders(<IndexTreeView tree={v1Tree} />);
    expect(screen.getByText('describes')).toBeInTheDocument();
    expect(screen.getByText('regulates')).toBeInTheDocument();
  });
});

describe('Backward Compatibility: QuestionsCascadeView with v1 data', () => {
  it('renders v1 questions (no coherence_note) without errors', () => {
    renderWithProviders(
      <QuestionsCascadeView
        documentQuestions={v1DocumentQuestions}
        sectionQuestions={v1SectionQuestions}
      />
    );
    expect(screen.getByTestId('questions-cascade-view')).toBeInTheDocument();
    expect(screen.getByText('¿Cuál es el propósito del documento?')).toBeInTheDocument();
  });

  it('does not render coherence note alert when absent', () => {
    renderWithProviders(
      <QuestionsCascadeView
        documentQuestions={v1DocumentQuestions}
        sectionQuestions={v1SectionQuestions}
        coherenceNote={null}
      />
    );
    expect(screen.queryByTestId('coherence-note-alert')).not.toBeInTheDocument();
  });

  it('does not render coherence note alert when undefined', () => {
    renderWithProviders(
      <QuestionsCascadeView
        documentQuestions={v1DocumentQuestions}
        sectionQuestions={v1SectionQuestions}
      />
    );
    expect(screen.queryByTestId('coherence-note-alert')).not.toBeInTheDocument();
  });

  it('renders section questions grouped by section_title', () => {
    renderWithProviders(
      <QuestionsCascadeView
        documentQuestions={v1DocumentQuestions}
        sectionQuestions={v1SectionQuestions}
      />
    );
    expect(screen.getByText('¿Quién aprueba los gastos?')).toBeInTheDocument();
  });
});

describe('Backward Compatibility: ConclusionsView with v1 data', () => {
  it('renders v1 observations (no domain, v1 categories) without errors', () => {
    renderWithProviders(<ConclusionsView observations={v1Observations} />);
    expect(screen.getByTestId('conclusions-view')).toBeInTheDocument();
  });

  it('falls back to category-grouped view when no observations have domain', () => {
    renderWithProviders(<ConclusionsView observations={v1Observations} />);
    // v1 data has no domain set, so it should use category-based grouping
    expect(screen.getByText('The document lacks a clear structure.')).toBeInTheDocument();
    expect(screen.getByText('Chapter 5 should come before Chapter 3.')).toBeInTheDocument();
  });

  it('handles missing domains_identified prop gracefully', () => {
    // When domains_identified is not provided (v1 data)
    renderWithProviders(<ConclusionsView observations={v1Observations} />);
    expect(screen.getByTestId('conclusions-view')).toBeInTheDocument();
  });

  it('renders v1 categories (coherence, reordering) with appropriate badges', () => {
    renderWithProviders(<ConclusionsView observations={v1Observations} />);
    // The component uses i18n keys for category labels
    const items = screen.getAllByTestId('observation-item');
    expect(items.length).toBe(2);
  });
});

describe('Backward Compatibility: RelationsListView with v1 data', () => {
  it('renders v1 relations (legacy types, no domain) without errors', () => {
    renderWithProviders(<RelationsListView relations={v1Relations} />);
    expect(screen.getByTestId('relations-list-view')).toBeInTheDocument();
  });

  it('groups v1 legacy types (depends_on, complements) correctly', () => {
    renderWithProviders(<RelationsListView relations={v1Relations} />);
    expect(screen.getByTestId('relation-group-depends_on')).toBeInTheDocument();
    expect(screen.getByTestId('relation-group-complements')).toBeInTheDocument();
  });

  it('displays relation descriptions for v1 data', () => {
    renderWithProviders(<RelationsListView relations={v1Relations} />);
    expect(screen.getByText('Chapter 3 uses definitions from Chapter 1.')).toBeInTheDocument();
    expect(screen.getByText('These sections complement each other.')).toBeInTheDocument();
  });

  it('does not render domain info when absent from v1 relations', () => {
    renderWithProviders(<RelationsListView relations={v1Relations} />);
    expect(screen.queryByTestId('relation-domain')).not.toBeInTheDocument();
  });
});

describe('Backward Compatibility: AnalysisResultView routing v1 data', () => {
  it('routes v1 build_index result correctly', () => {
    const v1IndexResult: IndexResult = { tree: v1Tree };
    renderWithProviders(
      <AnalysisResultView
        analysisType="build_index"
        result={v1IndexResult}
      />
    );
    expect(screen.getByRole('tree')).toBeInTheDocument();
  });

  it('routes v1 questions_answered result correctly', () => {
    const v1QuestionsResult: QuestionsResult = {
      document_questions: v1DocumentQuestions,
      section_questions: v1SectionQuestions,
      coherence_note: null,
    };
    renderWithProviders(
      <AnalysisResultView
        analysisType="questions_answered"
        result={v1QuestionsResult}
      />
    );
    expect(screen.getByTestId('questions-cascade-view')).toBeInTheDocument();
  });

  it('routes v1 conclusions result correctly', () => {
    const v1ConclusionsResult: ConclusionsResult = {
      observations: v1Observations,
      domains_identified: [],
    };
    renderWithProviders(
      <AnalysisResultView
        analysisType="conclusions"
        result={v1ConclusionsResult}
      />
    );
    expect(screen.getByTestId('conclusions-view')).toBeInTheDocument();
  });

  it('routes v1 section_relations result correctly', () => {
    const v1RelationsResult: RelationsResult = { relations: v1Relations };
    renderWithProviders(
      <AnalysisResultView
        analysisType="section_relations"
        result={v1RelationsResult}
      />
    );
    expect(screen.getByTestId('relations-list-view')).toBeInTheDocument();
  });

  it('does not show model badge when modelId is absent (v1 records)', () => {
    const v1IndexResult: IndexResult = { tree: v1Tree };
    renderWithProviders(
      <AnalysisResultView
        analysisType="build_index"
        result={v1IndexResult}
        modelId={null}
      />
    );
    expect(screen.queryByTestId('model-badge')).not.toBeInTheDocument();
  });

  it('renders null result gracefully', () => {
    const { container } = renderWithProviders(
      <AnalysisResultView
        analysisType="build_index"
        result={null}
      />
    );
    expect(container.querySelector('[data-testid="analysis-result-view"]')).not.toBeInTheDocument();
  });
});
