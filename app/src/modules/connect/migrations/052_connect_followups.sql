-- The day 3 nudge and the day 6 "did you meet?" question, kept in the database.
--
-- They used to be one-off jobs on the in-memory scheduler. Module job
-- reconciliation removed them about two minutes after they were queued (it
-- drops every namespaced job no module planned), and a pod restart would have
-- dropped them anyway, so no round was ever nudged or closed. A periodic sweep
-- now sends whatever is due here.
--
-- One row per round and kind. claimed_at is a lease: a pod takes due rows with
-- FOR UPDATE SKIP LOCKED and stamps claimed_at, so a second pod skips them,
-- and a pod that dies mid-send lets another retry once the lease runs out.
-- done_at is set once the row is finished, whether it was sent, skipped as
-- too late to be useful, or given up on after repeated failures (outcome).
--
-- No backfill here: the sweep creates missing rows for every open round of
-- its workspace on each pass, so rounds left open before this release recover
-- on the first sweep after deploy, and a round whose rows failed to insert
-- recovers the same way.

CREATE TABLE IF NOT EXISTS connect_followups (
    round_id INT NOT NULL REFERENCES connect_rounds(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('nudge', 'close')),
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    due_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0,
    done_at TIMESTAMPTZ,
    outcome TEXT,                            -- sent | skipped_stale | failed
    PRIMARY KEY (round_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_connect_followups_due
    ON connect_followups (team_id, due_at)
    WHERE done_at IS NULL;
