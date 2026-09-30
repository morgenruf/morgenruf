-- Who created each MCP key. A key made by an admin who has since left, or
-- been demoted, is refused at auth time. Existing keys have no creator and
-- keep working until someone revokes them.
ALTER TABLE mcp_api_keys ADD COLUMN IF NOT EXISTS created_by TEXT;
