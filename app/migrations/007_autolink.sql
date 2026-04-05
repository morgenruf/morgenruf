ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS jira_base_url TEXT DEFAULT '';
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS github_repo TEXT DEFAULT '';
ALTER TABLE workspace_config ADD COLUMN IF NOT EXISTS linear_team TEXT DEFAULT '';
