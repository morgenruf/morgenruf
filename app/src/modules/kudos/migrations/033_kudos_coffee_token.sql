-- The token becomes a coffee cup.
--
-- The logo already has the rooster holding a mug, Coffee chats is a feature,
-- and Morgenruf means morning call. One motif rather than two. The maple leaf
-- was a second, unrelated Canadian reference.
--
-- 032 is left alone because it has already been applied. Only workspaces still
-- on the old default move; anyone who picked their own token keeps it.
ALTER TABLE kudos_config ALTER COLUMN emoji SET DEFAULT '☕';
UPDATE kudos_config SET emoji = '☕' WHERE emoji = '🍁';
