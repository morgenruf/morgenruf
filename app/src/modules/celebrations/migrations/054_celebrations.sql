-- Celebrations: birthdays and work anniversaries posted to a channel.
--
-- Additive only. The dates themselves live in member_profiles (core, 051);
-- the working week and holidays in the core workspace calendar (053). This
-- module owns only its settings and a record of what it posted.

CREATE TABLE IF NOT EXISTS celebration_settings (
    team_id       TEXT PRIMARY KEY REFERENCES installations(team_id) ON DELETE CASCADE,
    -- Both required before anything is posted; the job does nothing until
    -- they are set.
    channel_id    TEXT,
    -- Its own setting, not standup's: the people who run celebrations and the
    -- people who run standups are often different, and a company celebrates
    -- on one clock even when its standup teams span several.
    timezone      TEXT,
    post_time     TEXT NOT NULL DEFAULT '09:00'
                  CHECK (post_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
    birthdays     BOOLEAN NOT NULL DEFAULT TRUE,
    anniversaries BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by    TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One row per message: a kind of celebration on one date. The row is claimed
-- (inserted) before the message is sent, so a restart or a second pod finds
-- it and does not post again. `ts` is filled in once Slack accepts the post.
CREATE TABLE IF NOT EXISTS celebration_posts (
    team_id          TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    kind             TEXT NOT NULL CHECK (kind IN ('birthday', 'anniversary')),
    celebration_date DATE NOT NULL,
    posted_on        DATE NOT NULL,
    channel_id       TEXT NOT NULL,
    user_ids         TEXT[] NOT NULL,
    ts               TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, kind, celebration_date)
);

CREATE INDEX IF NOT EXISTS idx_celebration_posts_created ON celebration_posts (created_at);
