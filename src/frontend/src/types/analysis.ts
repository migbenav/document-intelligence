/**
 * TypeScript interfaces for the On-Demand Analysis API responses.
 * Matches the backend Pydantic models (snake_case convention).
 */

/** The four available on-demand analysis types. */
export type AnalysisType =
  | 'build_index'
  | 'section_relations'
  | 'questions_answered'
  | 'conclusions';

/** Lifecycle status of an individual analysis. */
export type AnalysisStatus =
  | 'not_started'
  | 'in_progress'
  | 'completed'
  | 'outdated'
  | 'failed';

/** A reference back to source chunks that support a result element. */
export interface SourceRef {
  chunk_ids: string[];
  text_excerpt: string;
  section: string | null;
}

/** A node in the hierarchical structure tree (Build Index result). */
export interface StructureNode {
  id: string;
  title: string;
  level: number;
  role: string | null;
  functional_group?: string | null;
  original_headings?: string[];
  question_answered: string | null;
  source_ref: SourceRef | null;
  children: StructureNode[];
}

/** A relationship between two document sections. */
export interface SectionRelation {
  source_section: string;
  target_section: string;
  type:
    | 'enables'
    | 'restricts'
    | 'requires'
    | 'implements'
    | 'contradicts'
    // Legacy v1 types kept for backward compatibility
    | 'constrains'
    | 'depends_on'
    | 'complements';
  description: string;
  domain?: string | null;
  source_ref: SourceRef | null;
}

/** A question that the document (or a section) answers. */
export interface AnsweredQuestion {
  question: string;
  level: 'document' | 'section';
  section_title: string | null;
  source_ref: SourceRef | null;
}

/** A structural observation from the Conclusions analysis. */
export interface Observation {
  category:
    | 'purpose_mismatch'
    | 'misplaced_content'
    | 'title_mismatch'
    | 'sequence_issue'
    | 'duplication'
    | 'contradiction'
    // v1 categories kept for backward compat
    | 'coherence'
    | 'reordering'
    | 'orphan'
    | 'missing';
  description: string;
  suggestion: string;
  section_ref: string | null;
  domain: string | null;
  source_ref: SourceRef | null;
}

/** Status summary returned by GET /analyses (one entry per analysis type). */
export interface AnalysisStatusSummary {
  build_index: { status: AnalysisStatus; updated_at: string | null };
  section_relations: { status: AnalysisStatus; updated_at: string | null };
  questions_answered: { status: AnalysisStatus; updated_at: string | null };
  conclusions: { status: AnalysisStatus; updated_at: string | null };
}

// --- Result interfaces per analysis type ---

/** Result payload for the Build Index analysis. */
export interface IndexResult {
  tree: StructureNode[];
  document_purpose?: string | null;
}

/** Result payload for the Section Relations analysis. */
export interface RelationsResult {
  relations: SectionRelation[];
}

/** Result payload for the Questions Answered analysis. */
export interface QuestionsResult {
  document_questions: AnsweredQuestion[];
  section_questions: AnsweredQuestion[];
  coherence_note: string | null;
}

/** Result payload for the Conclusions & Recommendations analysis. */
export interface ConclusionsResult {
  observations: Observation[];
  domains_identified: string[];
}

/** A persisted analysis record as returned by the API. */
export interface AnalysisRecord {
  analysis_type: AnalysisType;
  status: AnalysisStatus;
  result: IndexResult | RelationsResult | QuestionsResult | ConclusionsResult | null;
  model_id: string | null;
  requested_model: string | null;
  fallback_used: boolean;
  prompt_version: string | null;
  created_at: string;
  updated_at: string;
}
