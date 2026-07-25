-- Migration: 003_add_quality_analysis
-- Description: Add quality analysis columns to analysis_sessions table
-- Requirements: 6.1, 6.5 — Quality analysis session management with state tracking and JSONB persistence

ALTER TABLE analysis_sessions
    ADD COLUMN quality_analysis JSONB DEFAULT NULL,
    ADD COLUMN quality_status TEXT DEFAULT NULL,
    ADD COLUMN quality_error_message TEXT DEFAULT NULL,
    ADD COLUMN quality_started_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN quality_completed_at TIMESTAMPTZ DEFAULT NULL;

-- quality_status values: NULL (not started), 'analyzing', 'completed', 'failed'
-- quality_analysis contains the full QualityAnalysisResult serialized as JSONB

COMMENT ON COLUMN analysis_sessions.quality_analysis IS
    'Full quality analysis results (inconsistencies, missing_elements, suggestions, metadata)';
COMMENT ON COLUMN analysis_sessions.quality_status IS
    'Quality analysis state: NULL (not started) | analyzing | completed | failed';
COMMENT ON COLUMN analysis_sessions.quality_error_message IS
    'Error message when quality analysis fails (max 1000 characters)';
COMMENT ON COLUMN analysis_sessions.quality_started_at IS
    'Timestamp when quality analysis was initiated';
COMMENT ON COLUMN analysis_sessions.quality_completed_at IS
    'Timestamp when quality analysis completed or failed';
