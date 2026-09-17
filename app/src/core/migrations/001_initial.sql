-- Slack OAuth installations (one per workspace)
CREATE TABLE installations (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL UNIQUE,
    team_name TEXT NOT NULL,
    bot_token TEXT NOT NULL,
    bot_user_id TEXT NOT NULL,
    app_id TEXT NOT NULL,
    installed_by_user_id TEXT,
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-workspace config (schedule, channel)
CREATE TABLE workspace_config (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    channel_id TEXT,
    schedule_time TEXT DEFAULT '09:00',
    schedule_tz TEXT DEFAULT 'UTC',
    schedule_days TEXT DEFAULT 'mon,tue,wed,thu,fri',
    questions JSONB DEFAULT '["What did you complete yesterday?","What are you working on today?","Any blockers?"]',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Team members per workspace
CREATE TABLE members (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    real_name TEXT,
    email TEXT,
    tz TEXT DEFAULT 'UTC',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, user_id)
);

-- Standup responses
CREATE TABLE standups (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    standup_date DATE NOT NULL DEFAULT CURRENT_DATE,
    yesterday TEXT,
    today TEXT,
    blockers TEXT,
    has_blockers BOOLEAN DEFAULT FALSE,
    submitted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_standups_team_date ON standups(team_id, standup_date);
CREATE INDEX idx_standups_user ON standups(team_id, user_id, standup_date);
