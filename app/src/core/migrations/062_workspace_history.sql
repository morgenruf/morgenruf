/*
What a workspace did with Morgenruf, kept after its data is deleted.

The listing and the privacy page promise that removing the app deletes the
workspace's data. Workspaces that Slack reports as account_inactive or
invalid_auth were only marked inactive, so their members, answers and kudos
stayed. Purging them is right, but it would also delete the only record of
how far each workspace got before it left.

One row per workspace, counts and dates only. No user IDs, no names, no
email addresses, no message text: nothing here identifies a person, so it
can outlive the purge. A nightly job keeps it current for every
installation, and the purge refreshes it one last time before deleting.
install_source is for a future ?ref= on the install link.
*/
CREATE TABLE IF NOT EXISTS workspace_history (
    team_id          TEXT PRIMARY KEY,
    team_name        TEXT,
    installed_at     TIMESTAMPTZ,
    removed_at       TIMESTAMPTZ,
    removal_reason   TEXT,
    install_source   TEXT,
    members_count    INTEGER NOT NULL DEFAULT 0,
    standups_created INTEGER NOT NULL DEFAULT 0,
    standup_answers  INTEGER NOT NULL DEFAULT 0,
    first_answer_at  TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ,
    kudos_count      INTEGER NOT NULL DEFAULT 0,
    coffee_rounds    INTEGER NOT NULL DEFAULT 0,
    modules_used     TEXT[] NOT NULL DEFAULT '{}',
    days_installed   INTEGER NOT NULL DEFAULT 0,
    purged_at        TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

/*
Set when a workspace's data has been deleted and only the bare row is left,
so the sweep never purges the same workspace twice and a reinstall can tell
it is starting over.
*/
ALTER TABLE installations ADD COLUMN IF NOT EXISTS purged_at TIMESTAMPTZ;
