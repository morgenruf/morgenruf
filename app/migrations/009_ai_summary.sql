ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS ai_summary_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS ai_provider TEXT DEFAULT 'openai';
