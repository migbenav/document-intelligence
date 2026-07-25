export interface SourceRefResponse {
  document_id: string;
  chunk_id: string;
  page: number | null;
  section: string | null;
  evidence: string;
}

export interface RelationResponse {
  target_id: string;
  type: 'constrains' | 'participates_in' | 'depends_on' | 'contradicts';
  description: string | null;
}

export type KnowledgeElementType =
  | 'proposito'
  | 'concepto'
  | 'actor'
  | 'regla'
  | 'proceso'
  | 'restriccion';

export interface KnowledgeElementResponse {
  id: string;
  type: KnowledgeElementType;
  name: string;
  content: string;
  source_ref: SourceRefResponse;
  relations: RelationResponse[];
  verified: boolean;
}

export interface ExtractionMetadataResponse {
  prompt_version: string;
  model_id: string;
  temperature: number;
  element_count: number;
  relationship_count: number;
  verification_rate: number;
  extracted_at: string;
}

export interface KnowledgeModelResponse {
  document_id: string;
  document_type: string;
  elements: KnowledgeElementResponse[];
  extraction_metadata: ExtractionMetadataResponse;
}
