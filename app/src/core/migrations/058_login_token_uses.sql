-- Dashboard login tokens travel in the URL after OAuth, so access logs record
-- them. Each token carries a nonce, and the first use inserts it here; any
-- later use of the same token is refused. Rows are purged after an hour,
-- well past the token's five minute life.
CREATE TABLE IF NOT EXISTS login_token_uses (
    nonce TEXT PRIMARY KEY,
    used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_token_uses_used_at ON login_token_uses (used_at);
