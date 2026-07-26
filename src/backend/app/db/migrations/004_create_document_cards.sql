-- Migration: 004_create_document_cards
-- Description: Create document_cards table for base analysis feature (C2)
-- Requirements: Req 4 (criterion 1) — Document card persistence with JSONB fields

CREATE TABLE document_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) UNIQUE,
    title TEXT NOT NULL,
    summary TEXT,
    classification TEXT,
    organization_type TEXT NOT NULL,
    statistics JSONB NOT NULL,
    file_metadata JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'partial',
    outdated BOOLEAN NOT NULL DEFAULT false,
    model_id TEXT,
    prompt_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_document_cards_document_id ON document_cards(document_id);
