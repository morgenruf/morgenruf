-- "I need a new match", recorded rather than answered with a platitude.
--
-- There is no spare person in a round: everybody eligible is already matched.
-- So a request waits for a second one and the two requesters are introduced to
-- each other. That is honest and it works, where "sure, here is someone else"
-- would either hand out somebody already in a chat or quietly do nothing.
--
-- One open request per person per round. Asking twice is idempotent, and a
-- request is closed when it is paired so it cannot be reused next round.
CREATE TABLE IF NOT EXISTS connect_rematch_requests (
    id           SERIAL PRIMARY KEY,
    round_id     BIGINT NOT NULL REFERENCES connect_rounds(id) ON DELETE CASCADE,
    match_id     BIGINT REFERENCES connect_matches(id) ON DELETE SET NULL,
    team_id      TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    paired_with  TEXT,
    resolved_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT connect_rematch_unique UNIQUE (round_id, user_id)
);

CREATE INDEX IF NOT EXISTS connect_rematch_open_idx
    ON connect_rematch_requests (round_id) WHERE resolved_at IS NULL;
