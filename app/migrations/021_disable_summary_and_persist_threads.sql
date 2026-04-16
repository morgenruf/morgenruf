-- Default the end-of-day summary to OFF. Workspaces that want it enable
-- it explicitly from the dashboard; the previous TRUE default meant every
-- schedule was posting a channel-level summary that many teams didn't want.
ALTER TABLE standup_schedules ALTER COLUMN post_summary SET DEFAULT FALSE;
UPDATE standup_schedules SET post_summary = FALSE WHERE post_summary IS NOT FALSE;

-- Persist the daily thread parent ts so the end-of-day summary can reliably
-- post under the same thread as the individual submissions — even if the pod
-- restarts between the first DM and the summary job, or the job runs in a
-- different process than the Bolt handler.
CREATE TABLE IF NOT EXISTS daily_standup_threads (
    team_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    thread_date DATE NOT NULL,
    parent_ts TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (team_id, channel_id, thread_date)
);
