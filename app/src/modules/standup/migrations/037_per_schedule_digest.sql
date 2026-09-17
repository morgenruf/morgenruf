-- A digest per standup, not one per workspace.
--
-- The workspace-level manager digest sends every standup in the workspace to a
-- single address. A workspace running ten standups across six teams cannot use
-- it: each lead would receive the other five teams' answers, and only one
-- address can be configured at all.
--
-- These are per schedule, so each team's lead gets their own team and nothing
-- else. The workspace-level setting keeps working for anyone using it.
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS digest_email TEXT;
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS digest_enabled BOOLEAN NOT NULL DEFAULT FALSE;
