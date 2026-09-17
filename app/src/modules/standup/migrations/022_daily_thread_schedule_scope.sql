-- Scope daily_standup_threads by schedule as well as channel. Workspaces
-- running multiple standups on the same channel (e.g. Morning + Evening)
-- were sharing one daily thread because the key was only
-- (team_id, channel_id, thread_date). Each schedule should have its own
-- thread parent.
ALTER TABLE daily_standup_threads
    ADD COLUMN IF NOT EXISTS schedule_id BIGINT NOT NULL DEFAULT 0;

ALTER TABLE daily_standup_threads DROP CONSTRAINT IF EXISTS daily_standup_threads_pkey;
ALTER TABLE daily_standup_threads
    ADD PRIMARY KEY (team_id, channel_id, thread_date, schedule_id);
