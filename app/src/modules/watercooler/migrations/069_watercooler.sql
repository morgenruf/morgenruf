-- Watercooler: a conversation question posted to a channel on a schedule.
--
-- Additive only. The built-in questions live in code (bank.py); the database
-- holds each workspace's channels, its own questions, the built-ins it hid,
-- and what was posted where, which drives rotation and the counts.

CREATE TABLE IF NOT EXISTS watercooler_channels (
    team_id       TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    channel_id    TEXT NOT NULL,
    days          TEXT NOT NULL DEFAULT 'mon,wed,fri',
    post_time     TEXT NOT NULL DEFAULT '10:00'
                  CHECK (post_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
    timezone      TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'both' CHECK (source IN ('builtin', 'custom', 'both')),
    categories    TEXT NOT NULL DEFAULT 'light,work,remote,this_or_that',
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    -- Why the job stopped posting on its own, e.g. not_in_channel. Cleared on resume.
    paused_reason TEXT,
    created_by    TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, channel_id)
);

CREATE TABLE IF NOT EXISTS watercooler_questions (
    id          BIGSERIAL PRIMARY KEY,
    team_id     TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    text        TEXT NOT NULL CHECK (char_length(text) BETWEEN 5 AND 300),
    archived    BOOLEAN NOT NULL DEFAULT FALSE,
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_watercooler_questions_team ON watercooler_questions (team_id);

-- Built-in questions a workspace chose not to see. Hiding is per workspace.
CREATE TABLE IF NOT EXISTS watercooler_hidden (
    team_id      TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    question_key TEXT NOT NULL,
    PRIMARY KEY (team_id, question_key)
);

-- One row per channel per local day. Inserted before the message is sent, so
-- a restart, a second pod or "Post one now" can never post twice that day.
CREATE TABLE IF NOT EXISTS watercooler_posts (
    team_id      TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    channel_id   TEXT NOT NULL,
    posted_on    DATE NOT NULL,
    question_ref TEXT NOT NULL,
    ts           TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, channel_id, posted_on)
);
CREATE INDEX IF NOT EXISTS idx_watercooler_posts_created ON watercooler_posts (created_at);

-- Counts only, like the other history columns.
ALTER TABLE workspace_history ADD COLUMN IF NOT EXISTS watercooler_posts INTEGER NOT NULL DEFAULT 0;
