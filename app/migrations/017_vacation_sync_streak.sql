-- Add on_vacation column to members (used by vacation toggle but never migrated)
ALTER TABLE members ADD COLUMN IF NOT EXISTS on_vacation BOOLEAN DEFAULT FALSE;

-- Add sync_with_channel flag to standup_schedules
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS sync_with_channel BOOLEAN DEFAULT FALSE;

-- Add group_by to standup_schedules (channel vs thread, member vs question)
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS group_by TEXT DEFAULT 'member';

-- Add post_to_thread to standup_schedules (if not already present)
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS post_to_thread BOOLEAN DEFAULT FALSE;

-- Add notify_on_report to standup_schedules
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS notify_on_report BOOLEAN DEFAULT TRUE;

-- Add weekend_reminder to standup_schedules
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS weekend_reminder BOOLEAN DEFAULT FALSE;
