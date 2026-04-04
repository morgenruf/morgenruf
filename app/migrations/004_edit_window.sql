-- Add edit window to workspace config
-- 0 = editable until report time, 4 = 4-hour window, NULL = no limit
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS edit_window_hours INTEGER DEFAULT 4;
