-- Add report_channel and report_time columns to standup_schedules.
-- These back the dashboard's "post a separate digest report" feature.
ALTER TABLE standup_schedules
    ADD COLUMN IF NOT EXISTS report_channel TEXT,
    ADD COLUMN IF NOT EXISTS report_time TEXT;
