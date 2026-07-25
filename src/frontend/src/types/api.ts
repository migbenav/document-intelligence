export interface UploadResponse {
  document_id: string;
  status: 'processing' | 'ready' | 'failed';
  filename: string;
  format: string;
  language: string | null;
  chunk_count: number | null;
  warnings: string[];
  error_message: string | null;
}

export interface StatusResponse {
  document_id: string;
  status: 'processing' | 'ready' | 'failed';
  filename: string;
  format: string;
  language: string | null;
  chunk_count: number | null;
  warnings: string[];
  error_message: string | null;
}

export interface ApiErrorResponse {
  error: string;
  message: string;
  supported_formats?: string[];
  max_size_bytes?: number;
  required_encoding?: string;
}
