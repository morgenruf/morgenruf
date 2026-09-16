-- Per-workspace module toggles.
--
-- Absence of a row means "use the module's own default_enabled", so this
-- table only ever records an explicit admin choice. New table, so nothing
-- existing is touched and rollback stays a plain image revert.
CREATE TABLE IF NOT EXISTS workspace_modules (
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    module TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (team_id, module)
);

CREATE INDEX IF NOT EXISTS idx_workspace_modules_team ON workspace_modules(team_id);
