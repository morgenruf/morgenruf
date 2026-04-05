ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS feed_token TEXT;
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS feed_public BOOLEAN DEFAULT FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS workspace_config_feed_token_idx ON workspace_config(feed_token) WHERE feed_token IS NOT NULL;
