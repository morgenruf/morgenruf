-- Track which platform each member uses
ALTER TABLE members ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'slack';
ALTER TABLE installations ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'slack';
