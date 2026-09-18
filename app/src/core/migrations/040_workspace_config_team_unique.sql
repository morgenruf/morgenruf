-- workspace_config.team_id needs a unique constraint.
--
-- upsert_workspace_config has always written with ON CONFLICT (team_id), and
-- the table only ever had a primary key on the serial id. Postgres answers
-- that with "there is no unique or exclusion constraint matching the ON
-- CONFLICT specification" and raises, so every workspace-level setting was
-- unwritable: the AI provider and summary toggle, the Jira / GitHub / Linear
-- autolinks, the manager digest, the edit window and the public feed token.
--
-- The table has always been one row per workspace in every reader
-- (get_workspace_config does WHERE team_id = %s and takes one row), so the
-- constraint matches the intent rather than changing it.

-- Any duplicates predate the constraint and were never reachable: the reader
-- returned an arbitrary one. Keep the most recently updated row per workspace.
DELETE FROM workspace_config wc
USING workspace_config keep
WHERE wc.team_id = keep.team_id
  AND wc.id <> keep.id
  AND (
    keep.updated_at > wc.updated_at
    OR (keep.updated_at = wc.updated_at AND keep.id > wc.id)
  );

-- Postgres has no ADD CONSTRAINT IF NOT EXISTS, and the rest of these
-- migrations are written to survive a re-run.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'workspace_config'::regclass
          AND conname = 'workspace_config_team_id_key'
    ) THEN
        ALTER TABLE workspace_config
            ADD CONSTRAINT workspace_config_team_id_key UNIQUE (team_id);
    END IF;
END $$;
