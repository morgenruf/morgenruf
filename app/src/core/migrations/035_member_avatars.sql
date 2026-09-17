-- Slack profile picture and handle for each member.
--
-- Both nullable, so this is a metadata-only change on an existing table and
-- costs no rewrite. They fill in on the next roster sync; until then the
-- dashboard falls back to initials, which is what it drew before.
ALTER TABLE members ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS display_name TEXT;
