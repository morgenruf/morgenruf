-- Retire installations whose Slack app has been uninstalled.
--
-- Nothing ever recorded that an installation had gone away, so every scheduler
-- pass kept registering jobs for it and the member sync kept calling users.list
-- with a token Slack had already invalidated. On this deployment 10 of 17
-- installations answer account_inactive or invalid_auth and had been retried
-- every six hours indefinitely.
--
-- Rows are kept rather than deleted. Standup history references the team, and
-- a workspace that reinstalls should come back rather than start over.

ALTER TABLE installations
  ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS deactivated_reason TEXT;

CREATE INDEX IF NOT EXISTS installations_active_idx ON installations(active);
