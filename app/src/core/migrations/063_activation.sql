/* Activation week.

   install_source: where an install came from, from /install?ref=<source>, so
   the Monday report can count activated workspaces per source. Set once, on
   the first install, and copied into workspace_history.

   awaiting_invite_by: a standup created from the quick start for a channel
   the bot is not in yet. It stays inactive until someone invites the bot,
   then switches on and tells this user. NULL for every other standup. */
ALTER TABLE installations ADD COLUMN IF NOT EXISTS install_source TEXT;
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS awaiting_invite_by TEXT;
CREATE INDEX IF NOT EXISTS standup_schedules_awaiting_idx
    ON standup_schedules (team_id, channel_id) WHERE awaiting_invite_by IS NOT NULL;
