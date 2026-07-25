-- Migration: 002_create_analysis_sessions
-- Description: Create analysis_sessions table for Knowledge Model extraction pipeline
-- Requirements: 8.1, 8.2, 8.5 — Analysis session management with state tracking and JSONB persistence

CREATE TABLE analysis_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE REFERENCES documents(document_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'inferring_type',
    -- Status values: inferring_type | awaiting_confirmation | extracting | verifying | completed | failed
    suggested_type TEXT,
    suggested_type_justification TEXT,
    confirmed_type TEXT,
    knowledge_model JSONB,
    extraction_metadata JSONB,
    error_message TEXT,
    prompt_version TEXT,
    model_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The UNIQUE constraint on document_id enforces one analysis per document (Req 9.7)
