-- Migration: 001_create_documents
-- Description: Create documents and document_chunks tables for the ingestion layer

-- Stores metadata and IR for active sessions
CREATE TABLE documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename TEXT NOT NULL,
    format TEXT NOT NULL,  -- 'markdown' | 'plain_text' | 'pdf'
    size_bytes INTEGER NOT NULL,
    language TEXT NOT NULL DEFAULT 'unknown',  -- 'es' | 'en' | 'unknown'
    upload_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    warnings JSONB DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'processing',  -- 'processing' | 'ready' | 'failed'
    error_message TEXT,
    expires_at TIMESTAMPTZ NOT NULL,  -- session expiry for cleanup
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stores extracted chunks for a document
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL,
    text TEXT NOT NULL,
    structural_context JSONB NOT NULL,  -- {"page": 2} or {"section": "## Heading"}
    "order" INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_id)
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
