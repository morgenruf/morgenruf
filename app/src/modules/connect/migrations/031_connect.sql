-- Connect: random coffee chats.
--
-- Additive only. New tables with a foreign key to installations, so uninstall
-- cleans up through the existing ON DELETE CASCADE and rollback stays a plain
-- image revert.

CREATE TABLE IF NOT EXISTS connect_programs (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT 'Coffee chats',
    interval_weeks INT NOT NULL DEFAULT 1,
    day_of_week INT NOT NULL DEFAULT 1,      -- 0 = Monday
    hour INT NOT NULL DEFAULT 10,
    minute INT NOT NULL DEFAULT 0,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (team_id, channel_id)
);

CREATE TABLE IF NOT EXISTS connect_rounds (
    id SERIAL PRIMARY KEY,
    program_id INT NOT NULL REFERENCES connect_programs(id) ON DELETE CASCADE,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    scheduled_for TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',   -- pending | matched | delivered | closed
    member_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    -- Idempotency guard. Duplicate job fires and scheduler restarts are a
    -- known failure mode here, so double-matching is impossible in the
    -- database rather than in application logic.
    UNIQUE (program_id, scheduled_for)
);

CREATE TABLE IF NOT EXISTS connect_matches (
    id SERIAL PRIMARY KEY,
    round_id INT NOT NULL REFERENCES connect_rounds(id) ON DELETE CASCADE,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    member_ids TEXT[] NOT NULL,              -- length 2, or 3 for the odd-count trio
    mpim_channel_id TEXT,
    delivered_at TIMESTAMPTZ,
    nudged_at TIMESTAMPTZ,
    met BOOLEAN
);

CREATE TABLE IF NOT EXISTS connect_pair_history (
    program_id INT NOT NULL REFERENCES connect_programs(id) ON DELETE CASCADE,
    member_a TEXT NOT NULL,                  -- normalised so member_a < member_b
    member_b TEXT NOT NULL,
    times_paired INT NOT NULL DEFAULT 0,
    last_round_id INT,
    PRIMARY KEY (program_id, member_a, member_b)
);

CREATE TABLE IF NOT EXISTS connect_optouts (
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    program_id INT NOT NULL REFERENCES connect_programs(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'off',        -- off | paused
    paused_until DATE,
    PRIMARY KEY (team_id, program_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_connect_rounds_program ON connect_rounds(program_id, scheduled_for DESC);
CREATE INDEX IF NOT EXISTS idx_connect_matches_round ON connect_matches(round_id);
