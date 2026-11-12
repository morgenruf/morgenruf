/* Which "What's new" items a person has dismissed on their Home tab.

   The items themselves live in code (src/core/whats_new.py); this only
   remembers who pressed "Got it" on which one. */
CREATE TABLE IF NOT EXISTS whats_new_seen (
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id, item_id)
);
