/* Anonymous pulse. Answers carry no user id and no timestamp; who answered is
   kept apart in pulse_respondents (no values), only to stop double answers and
   to remind people who have not answered. Results are shown only for rounds
   with at least five respondents.

   Additive only. gen_random_uuid() is built in from Postgres 13. */
CREATE TABLE IF NOT EXISTS pulse_programs (
    team_id        TEXT PRIMARY KEY REFERENCES installations(team_id) ON DELETE CASCADE,
    enabled        BOOLEAN NOT NULL DEFAULT FALSE,
    day_of_week    SMALLINT NOT NULL DEFAULT 4,
    hour           SMALLINT NOT NULL DEFAULT 14,
    minute         SMALLINT NOT NULL DEFAULT 0,
    timezone       TEXT NOT NULL DEFAULT 'UTC',
    audience_channel_id TEXT,
    updated_by     TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS pulse_rounds (
    id           BIGSERIAL PRIMARY KEY,
    team_id      TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    sent_on      DATE NOT NULL,
    includes_enps BOOLEAN NOT NULL DEFAULT FALSE,
    invited      INTEGER NOT NULL DEFAULT 0,
    reminded_at  TIMESTAMPTZ,
    closes_at    TIMESTAMPTZ NOT NULL,
    UNIQUE (team_id, sent_on)
);
CREATE TABLE IF NOT EXISTS pulse_respondents (
    round_id     BIGINT NOT NULL REFERENCES pulse_rounds(id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL,
    question_key TEXT NOT NULL,
    PRIMARY KEY (round_id, user_id, question_key)
);
CREATE TABLE IF NOT EXISTS pulse_invites (
    round_id     BIGINT NOT NULL REFERENCES pulse_rounds(id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL,
    PRIMARY KEY (round_id, user_id)
);
CREATE TABLE IF NOT EXISTS pulse_answers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id     BIGINT NOT NULL REFERENCES pulse_rounds(id) ON DELETE CASCADE,
    question_key TEXT NOT NULL,
    value        SMALLINT NOT NULL
);
CREATE INDEX IF NOT EXISTS pulse_answers_round_idx ON pulse_answers (round_id, question_key);
