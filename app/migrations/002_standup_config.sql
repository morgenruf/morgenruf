-- Additional workspace_config columns and away/skip tracking

ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS standup_name TEXT DEFAULT 'Team Standup';
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS reminder_minutes INTEGER DEFAULT 60;
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS report_destination TEXT DEFAULT 'channel';
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS group_by TEXT DEFAULT 'member';
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS sync_with_channel BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS user_away (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    away_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, user_id, away_date)
);

CREATE TABLE IF NOT EXISTS user_skip (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    skip_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, user_id, skip_date)
);
