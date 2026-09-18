-- Per-person Zoom authorisation, so a coffee chat can carry a real meeting.
--
-- One row per (workspace, person). The link belongs to the individual, not the
-- workspace: it is their Zoom account that hosts the meeting, and revoking it
-- must not affect anyone else.
--
-- Zoom rotates the refresh token on every refresh: the response carries a new
-- one and the old is dead immediately. So refresh_token is rewritten on every
-- refresh, and a failure to persist it breaks the link permanently. The 90 day
-- idle expiry is recorded too, so the UI can say "reconnect" rather than
-- failing silently when somebody comes back after a quiet quarter.
CREATE TABLE IF NOT EXISTS connect_zoom_links (
    id                 SERIAL PRIMARY KEY,
    team_id            TEXT NOT NULL,
    user_id            TEXT NOT NULL,
    zoom_user_id       TEXT,
    zoom_email         TEXT,
    access_token       TEXT NOT NULL,
    refresh_token      TEXT NOT NULL,
    access_expires_at  TIMESTAMPTZ NOT NULL,
    refresh_expires_at TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT connect_zoom_links_unique UNIQUE (team_id, user_id)
);

CREATE INDEX IF NOT EXISTS connect_zoom_links_team_idx
    ON connect_zoom_links (team_id) WHERE revoked_at IS NULL;

-- The meeting created for an agreed slot, so a second delivery or a retry does
-- not create a second meeting on somebody's Zoom account.
ALTER TABLE connect_matches
    ADD COLUMN IF NOT EXISTS zoom_join_url TEXT;
ALTER TABLE connect_matches
    ADD COLUMN IF NOT EXISTS zoom_meeting_id TEXT;
