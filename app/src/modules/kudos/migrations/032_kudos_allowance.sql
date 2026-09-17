-- Kudos becomes a daily allowance with a workspace-chosen token.
--
-- Unlimited praise is worth little; a small daily budget is what makes people
-- spend it deliberately. Additive only: existing kudos rows keep working and
-- a workspace with no config row gets the defaults.

CREATE TABLE IF NOT EXISTS kudos_config (
    team_id TEXT PRIMARY KEY REFERENCES installations(team_id) ON DELETE CASCADE,
    -- The token a workspace gives. Defaults to a maple leaf: Morgenruf is
    -- built in Toronto, and it should not read as a clone of anyone's taco.
    emoji TEXT NOT NULL DEFAULT '🍁',
    -- What each person may give per day. 0 turns giving off without
    -- uninstalling the module.
    daily_allowance INT NOT NULL DEFAULT 5,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT kudos_allowance_sane CHECK (daily_allowance >= 0 AND daily_allowance <= 50)
);

-- Record the token each kudos was given with, so changing the workspace token
-- later does not rewrite what people already sent.
ALTER TABLE kudos ADD COLUMN IF NOT EXISTS emoji TEXT;

-- The allowance check counts a giver's kudos within their local day, so this
-- is the index it needs.
CREATE INDEX IF NOT EXISTS idx_kudos_from_created ON kudos(team_id, from_user, created_at DESC);
