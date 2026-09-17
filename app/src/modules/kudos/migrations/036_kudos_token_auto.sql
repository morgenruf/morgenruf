-- The kudos token goes back to a plain emoji by default.
--
-- 034 made :morgenruf: the default, which is only correct once a workspace has
-- imported the icon as a custom emoji. Until then Slack renders the literal
-- text ":morgenruf:" in every kudos message, and a brand new workspace has no
-- way to know that before it happens.
--
-- The default is the maple leaf again, and token_auto records whether we
-- may upgrade it on the workspace's behalf once the custom emoji shows up.
-- An admin who sets the token themselves turns that off, so their choice is
-- never overwritten.
ALTER TABLE kudos_config ALTER COLUMN emoji SET DEFAULT '🍁';
ALTER TABLE kudos_config ADD COLUMN IF NOT EXISTS token_auto BOOLEAN NOT NULL DEFAULT TRUE;

-- Workspaces stranded on the 034 default, which renders as literal text unless
-- they happened to have imported the emoji already.
UPDATE kudos_config SET emoji = '🍁' WHERE emoji = ':morgenruf:';

-- A row that already holds something we never set is an admin's own choice, and
-- adding the column with DEFAULT TRUE would have quietly put those under
-- automatic management and overwritten them on the next sync.
UPDATE kudos_config SET token_auto = FALSE
WHERE emoji IS NOT NULL AND emoji NOT IN ('🍁', '☕', ':morgenruf:');
