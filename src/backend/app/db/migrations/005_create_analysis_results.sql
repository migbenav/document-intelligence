-- Migration: 005_create_analysis_results
-- Description: Create analysis_results table for on-demand analysis feature (C3)
-- Requirements: Req 6 (criteria 3, 5, 6) — Persistence, idempotency, and outdated marking

CREATE TABLE analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id),
    analysis_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    result JSONB,
    model_id TEXT,
    prompt_version TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, analysis_type)
);

CREATE INDEX idx_analysis_results_document_id ON analysis_results(document_id);
