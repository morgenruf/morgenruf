-- Consent to receive product updates, with proof of when and how it was given.
--
-- The welcome email is transactional: somebody installed the app a minute
-- earlier. A message about a new feature is not, and Canadian anti-spam law
-- wants express consent plus a record of it. Slack's marketplace guidelines
-- ask for the same thing in different words: "request explicit email consent".
--
-- So this table is the proof, not a marketing tool: who said yes, when, from
-- where, and when they changed their mind. The CRM copy is downstream of it
-- and can be rebuilt from here.
CREATE TABLE IF NOT EXISTS email_consents (
    email       TEXT PRIMARY KEY,
    team_id     TEXT,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source      TEXT NOT NULL DEFAULT 'welcome-email',
    ip          TEXT,
    revoked_at  TIMESTAMPTZ,
    synced_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS email_consents_live_idx
    ON email_consents (granted_at) WHERE revoked_at IS NULL;
