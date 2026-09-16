ALTER TABLE installations ADD COLUMN IF NOT EXISTS bot_refresh_token TEXT;
ALTER TABLE installations ADD COLUMN IF NOT EXISTS bot_token_expires_at TIMESTAMPTZ;
