-- The three engagement toggles the settings page offers.
--
-- Added with the settings page rather than after it: a control with no column
-- behind it saves nothing and reports success, which is the defect this
-- codebase spent a day removing from the standup settings.
--
-- Defaults match what every existing programme already does, so nothing
-- changes behaviour on upgrade: times and an icebreaker are what the message
-- has always carried, and in-channel stats have never been posted.
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS suggest_times BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS use_icebreaker BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS post_stats BOOLEAN NOT NULL DEFAULT FALSE;
