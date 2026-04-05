-- Kudos / peer recognition
CREATE TABLE IF NOT EXISTS kudos (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    from_user TEXT NOT NULL,
    to_user TEXT NOT NULL,
    message TEXT NOT NULL,
    channel_id TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kudos_team ON kudos(team_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kudos_to ON kudos(team_id, to_user);
