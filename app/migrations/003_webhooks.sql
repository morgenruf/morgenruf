-- Outbound webhook registrations per workspace
CREATE TABLE webhooks (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    webhook_url TEXT NOT NULL,
    secret TEXT,
    events TEXT[] DEFAULT ARRAY['standup.completed'],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_webhooks_team ON webhooks(team_id);
