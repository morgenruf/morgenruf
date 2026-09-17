-- Kudos token defaults to the Morgenruf icon.
--
-- Workspaces import the icon as a Slack custom emoji named :morgenruf: from
-- the kudos settings page. Existing rows are left alone on purpose: a
-- workspace that has not imported it yet would start posting the literal text
-- ":morgenruf:" into Slack, so they keep whatever they are using until an
-- admin changes it themselves.
ALTER TABLE kudos_config ALTER COLUMN emoji SET DEFAULT ':morgenruf:';
