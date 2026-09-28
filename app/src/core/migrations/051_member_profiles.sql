-- What a person says about themselves, kept apart from the Slack roster.
--
-- `members` mirrors Slack and the member sync owns it, so anything typed into
-- it would be overwritten on the next pass. A separate table means the sync
-- can never touch what a person or an admin entered here.
--
-- Birthdays are day and month only. No message needs an age, and not storing
-- the year removes the sensitive part. start_date keeps its year because
-- anniversaries count years.
--
-- left_at is set when the sync marks someone inactive and cleared when they
-- come back. A nightly job deletes rows that have been gone for 30 days.
CREATE TABLE IF NOT EXISTS member_profiles (
    team_id       TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    birth_month   SMALLINT CHECK (birth_month BETWEEN 1 AND 12),
    birth_day     SMALLINT CHECK (birth_day BETWEEN 1 AND 31),
    start_date    DATE,
    role          TEXT CHECK (char_length(role) <= 80),
    location      TEXT CHECK (char_length(location) <= 80),
    ask_me_about  TEXT CHECK (char_length(ask_me_about) <= 200),
    celebrate     BOOLEAN NOT NULL DEFAULT TRUE,
    nudged_at     TIMESTAMPTZ,
    left_at       TIMESTAMPTZ,
    updated_by    TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id),
    CHECK ((birth_month IS NULL) = (birth_day IS NULL))
);

-- The purge only ever looks at rows with left_at set, which is a handful.
CREATE INDEX IF NOT EXISTS member_profiles_left_at_idx
    ON member_profiles (left_at) WHERE left_at IS NOT NULL;
