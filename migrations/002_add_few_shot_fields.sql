-- Migration: 002_add_few_shot_fields
-- Description: Add few-shot related fields to messages and create few-shot metadata table

-- Add is_few_shot flag to messages table
ALTER TABLE easysql_messages 
ADD COLUMN IF NOT EXISTS is_few_shot BOOLEAN DEFAULT FALSE;

-- Add user_answer for clarification responses
ALTER TABLE easysql_messages 
ADD COLUMN IF NOT EXISTS user_answer TEXT;

-- Add clarification_questions as JSON array
ALTER TABLE easysql_messages 
ADD COLUMN IF NOT EXISTS clarification_questions JSONB;

-- Create index for few-shot queries
CREATE INDEX IF NOT EXISTS idx_easysql_messages_few_shot 
ON easysql_messages(is_few_shot) WHERE is_few_shot = TRUE;

-- Few-shot examples metadata (links to messages, stored in Milvus for vectors)
CREATE TABLE IF NOT EXISTS easysql_few_shot_meta (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID REFERENCES easysql_messages(id) ON DELETE CASCADE,
    db_name VARCHAR(100) NOT NULL,
    question TEXT NOT NULL,
    sql TEXT NOT NULL,
    tables_used TEXT[],
    explanation TEXT,
    milvus_id VARCHAR(256),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_easysql_few_shot_db ON easysql_few_shot_meta(db_name);
CREATE INDEX IF NOT EXISTS idx_easysql_few_shot_milvus ON easysql_few_shot_meta(milvus_id);
