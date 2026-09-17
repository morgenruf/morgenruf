CREATE TABLE IF NOT EXISTS workflow_rules (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL,
    name TEXT NOT NULL,
    trigger TEXT NOT NULL,   -- 'blocker_detected' | 'low_participation' | 'standup_complete'
    condition_value TEXT,    -- e.g. participation threshold "50"
    action TEXT NOT NULL,    -- 'post_to_channel' | 'send_dm' | 'fire_webhook'
    action_target TEXT NOT NULL,  -- channel_id, user_id, or webhook URL
    action_message TEXT,     -- optional custom message template
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS workflow_rules_team_idx ON workflow_rules(team_id);
