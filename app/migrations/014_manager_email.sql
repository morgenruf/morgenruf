ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS manager_email TEXT;
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS manager_digest_enabled BOOLEAN DEFAULT FALSE;
