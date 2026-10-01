/* Polls. Votes on anonymous polls are keyed by HMAC(salt, user_id); the salt
   is cleared when the poll closes, so closed anonymous votes cannot be tied
   to anyone. Named polls store the user id so names can be shown.

   Additive only. */
CREATE TABLE IF NOT EXISTS polls (
    id            BIGSERIAL PRIMARY KEY,
    team_id       TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    created_by    TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    message_ts    TEXT,
    question      TEXT NOT NULL,
    options       JSONB NOT NULL,
    anonymous     BOOLEAN NOT NULL DEFAULT FALSE,
    multiple      BOOLEAN NOT NULL DEFAULT FALSE,
    hide_results  BOOLEAN NOT NULL DEFAULT FALSE,
    salt          BYTEA,
    closes_at     TIMESTAMPTZ,
    closed_at     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS polls_team_open_idx ON polls (team_id) WHERE closed_at IS NULL;

/* One row per person per option they picked. voter_key is the user id on a
   named poll and the HMAC on an anonymous one. */
CREATE TABLE IF NOT EXISTS poll_votes (
    poll_id     BIGINT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    option_idx  SMALLINT NOT NULL,
    voter_key   TEXT NOT NULL,
    PRIMARY KEY (poll_id, option_idx, voter_key)
);
