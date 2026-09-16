CREATE TABLE IF NOT EXISTS mcp_api_keys (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,  -- SHA-256 of the actual key
    key_prefix TEXT NOT NULL,       -- first 8 chars for display (e.g. "mrn_a1b2")
    name TEXT DEFAULT 'Default',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS mcp_api_keys_team_idx ON mcp_api_keys(team_id);
CREATE INDEX IF NOT EXISTS mcp_api_keys_hash_idx ON mcp_api_keys(key_hash);
