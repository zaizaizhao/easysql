-- Migration: 004_add_message_thread_fields
-- Description: Add thread/branch fields to messages for isolation

ALTER TABLE easysql_messages
ADD COLUMN IF NOT EXISTS thread_id TEXT;

ALTER TABLE easysql_messages
ADD COLUMN IF NOT EXISTS branch_id UUID;

ALTER TABLE easysql_messages
ADD COLUMN IF NOT EXISTS root_message_id UUID;

CREATE INDEX IF NOT EXISTS idx_easysql_messages_thread
ON easysql_messages(thread_id);

CREATE INDEX IF NOT EXISTS idx_easysql_messages_root
ON easysql_messages(root_message_id);
