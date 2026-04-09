ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS prepopulate_answers BOOLEAN DEFAULT FALSE;
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS allow_edit_after_report BOOLEAN DEFAULT FALSE;
