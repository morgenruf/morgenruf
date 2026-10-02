-- Per-standup managers: a person who may change one standup without
-- administering every standup in the workspace.
--
-- Additive only. A row is removed with its standup, and with the workspace.

CREATE TABLE IF NOT EXISTS standup_managers (
    schedule_id INTEGER NOT NULL REFERENCES standup_schedules(id) ON DELETE CASCADE,
    team_id     TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    added_by    TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (schedule_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_standup_managers_user ON standup_managers (team_id, user_id);
