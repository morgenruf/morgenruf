-- Add post_summary flag to standup_schedules.
-- When FALSE, the end-of-day summary is skipped entirely.
-- Default TRUE to preserve existing behavior for current workspaces.
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS post_summary BOOLEAN DEFAULT TRUE;
