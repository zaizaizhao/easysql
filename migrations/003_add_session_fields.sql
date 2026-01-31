-- Migration: 003_add_session_fields
-- Description: Add session persistence fields for multi-turn state

ALTER TABLE easysql_sessions
ADD COLUMN IF NOT EXISTS raw_query TEXT;

ALTER TABLE easysql_sessions
ADD COLUMN IF NOT EXISTS generated_sql TEXT;

ALTER TABLE easysql_sessions
ADD COLUMN IF NOT EXISTS validation_passed BOOLEAN;

ALTER TABLE easysql_sessions
ADD COLUMN IF NOT EXISTS state JSONB;

ALTER TABLE easysql_sessions
ADD COLUMN IF NOT EXISTS turns JSONB;

ALTER TABLE easysql_sessions
ADD COLUMN IF NOT EXISTS title TEXT;

CREATE INDEX IF NOT EXISTS idx_easysql_sessions_updated_at
ON easysql_sessions(updated_at DESC);
