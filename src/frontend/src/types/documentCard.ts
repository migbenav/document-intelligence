/**
 * TypeScript interfaces for the Document Card API responses.
 * Matches the backend Pydantic models (snake_case convention).
 */

export type DocumentClassification =
  | 'normative'
  | 'guide'
  | 'manual'
  | 'procedure'
  | 'technical'
  | 'narrative'
  | 'other';

export type OrganizationType =
  | 'numbered_articles'
  | 'headed_sections'
  | 'hierarchical_numbering'
  | 'free_form';

export interface DocumentCardStatistics {
  total_chunks: number;
  sections_detected: number;
  hierarchy_levels: number;
  has_existing_index: boolean;
}

export interface FileMetadata {
  size_bytes: number;
  format: string;
  language: string | null;
  last_modified: string | null;
}

export type DocumentCardStatus = 'completed' | 'failed_llm' | 'partial';

export interface DocumentCard {
  id: string;
  document_id: string;
  title: string;
  summary: string | null;
  classification: DocumentClassification | null;
  organization_type: OrganizationType;
  statistics: DocumentCardStatistics;
  file_metadata: FileMetadata;
  status: DocumentCardStatus;
  outdated: boolean;
  model_id: string | null;
  prompt_version: string | null;
  created_at: string;
  updated_at: string;
}
