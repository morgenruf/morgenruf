-- Per-feature administrators.
--
-- Roles were workspace-wide and binary: an admin changed everything, a member
-- changed nothing. A team lead who should own the standups had to be given
-- the keys to billing-adjacent settings, webhooks and API keys as well, so in
-- practice nobody was promoted and one person did everything.
--
-- A grant is one row per (workspace, person, feature). A workspace admin still
-- implies every feature, so this only ever widens access and no existing
-- permission changes.
CREATE TABLE IF NOT EXISTS module_admins (
    id         SERIAL PRIMARY KEY,
    team_id    TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    module     TEXT NOT NULL,
    granted_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT module_admins_unique UNIQUE (team_id, user_id, module)
);

CREATE INDEX IF NOT EXISTS module_admins_lookup_idx
    ON module_admins (team_id, user_id);
