-- Which proposed times each person said would work.
--
-- Donut drops two people into a DM and leaves them to negotiate, which is
-- where most introductions die: both are willing, neither wants to be the one
-- to pick. A tap per acceptable slot lets the bot settle it the moment
-- everybody has accepted the same one, with no calendar access involved.
--
-- One row per (match, person, slot): a person can accept several times, which
-- is the whole point. Accepting the same slot twice is idempotent.
CREATE TABLE IF NOT EXISTS connect_slot_votes (
    id          SERIAL PRIMARY KEY,
    match_id    BIGINT NOT NULL REFERENCES connect_matches(id) ON DELETE CASCADE,
    team_id     TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    slot_utc    TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT connect_slot_votes_unique UNIQUE (match_id, user_id, slot_utc)
);

CREATE INDEX IF NOT EXISTS connect_slot_votes_match_idx
    ON connect_slot_votes (match_id, slot_utc);

-- The settled time, once everyone in the match has accepted the same slot.
-- On the match rather than in a separate table because it is one value and it
-- is what every reader of a match wants next.
ALTER TABLE connect_matches
    ADD COLUMN IF NOT EXISTS agreed_slot_utc TIMESTAMPTZ;
