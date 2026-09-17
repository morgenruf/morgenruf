-- include_guests went in with the settings page and nothing ever read it.
--
-- Honouring it needs to know which members are Slack guests, and the roster
-- does not record is_restricted or is_ultra_restricted, so implementing it is
-- a roster change rather than a settings one. A column with no feature behind
-- it is the thing this module keeps having removed, so it goes until the
-- feature that needs it arrives.
ALTER TABLE connect_programs DROP COLUMN IF EXISTS include_guests;
