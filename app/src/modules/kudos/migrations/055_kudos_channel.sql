-- Kudos gets a channel of its own.
--
-- The kudos card went to workspace_config.channel_id, a legacy workspace-level
-- column that nothing in the dashboard or the API sets. For most workspaces
-- that meant no channel post at all. The recipient is now told by DM on every
-- kudos, and this is the optional channel the card is also shared in.
--
-- NULL or empty means no kudos channel: the card falls back to the legacy
-- column when that is set, and otherwise only the DMs go out. Additive only.

ALTER TABLE kudos_config ADD COLUMN IF NOT EXISTS channel_id TEXT;
