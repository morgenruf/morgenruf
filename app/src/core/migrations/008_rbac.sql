-- Role-based access control
ALTER TABLE members ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin','member'));

-- Grant admin to whoever installed the workspace
UPDATE members m
SET role = 'admin'
FROM installations i
WHERE m.team_id = i.team_id
  AND m.user_id = i.installed_by_user_id;
