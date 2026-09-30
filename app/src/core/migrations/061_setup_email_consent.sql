-- Consent to be emailed at the installer's Slack address, one row per workspace.
--
-- Slack's marketplace guidelines: an app reading addresses through
-- users:read.email must get explicit consent before contacting anybody. The
-- welcome email used to go out as soon as OAuth finished. Now nothing goes to a
-- Slack-sourced address until the installer presses "Email me setup tips" in
-- the install DM or on the App Home.
--
-- The row is the proof: who pressed it and when. Withdrawing sets revoked_at
-- rather than deleting, so the history survives until the workspace does.
CREATE TABLE IF NOT EXISTS setup_email_consents (
    team_id    TEXT PRIMARY KEY REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);
