-- Multiple standup schedules per workspace
CREATE TABLE IF NOT EXISTS standup_schedules (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Daily Standup',
    channel_id TEXT,
    schedule_time TEXT NOT NULL DEFAULT '09:00',
    schedule_tz TEXT NOT NULL DEFAULT 'UTC',
    schedule_days TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri',
    questions JSONB NOT NULL DEFAULT '["What did you complete yesterday?","What are you working on today?","Any blockers?"]',
    participants TEXT[] DEFAULT ARRAY[]::TEXT[],
    reminder_minutes INTEGER DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schedules_team ON standup_schedules(team_id, active);
