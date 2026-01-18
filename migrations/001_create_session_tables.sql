-- Migration: 001_create_session_tables
-- Description: Create business tables for multi-turn conversation support
-- Note: LangGraph checkpoint tables are auto-created by langgraph-checkpoint-postgres

-- Sessions table
CREATE TABLE IF NOT EXISTS easysql_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    db_name VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages table (tree structure for branching)
CREATE TABLE IF NOT EXISTS easysql_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES easysql_sessions(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES easysql_messages(id) ON DELETE SET NULL,
    
    role VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT,
    
    generated_sql TEXT,
    tables_used TEXT[],
    validation_passed BOOLEAN,
    
    is_branch_point BOOLEAN DEFAULT FALSE,
    checkpoint_id VARCHAR(100),
    token_count INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_easysql_messages_session ON easysql_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_easysql_messages_parent ON easysql_messages(parent_id);
CREATE INDEX IF NOT EXISTS idx_easysql_sessions_status ON easysql_sessions(status);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for sessions table
DROP TRIGGER IF EXISTS update_easysql_sessions_updated_at ON easysql_sessions;
CREATE TRIGGER update_easysql_sessions_updated_at
    BEFORE UPDATE ON easysql_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
