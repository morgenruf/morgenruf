-- Meeting options for a coffee chat programme.
--
-- match_working_hours is off by default and must stay that way: a team spread
-- across Toronto and Kolkata shares no hours at all in a 09:00-17:00 day, so
-- switching this on for everyone would quietly stop matching them entirely.
-- It is useful, but only where a workspace knows it applies.
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS match_working_hours BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS meeting_minutes INT NOT NULL DEFAULT 30;
-- A room the whole programme shares, pasted once. Not an integration: no OAuth,
-- no per-meeting link, just somewhere to meet that beats "find a time".
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS meeting_link TEXT;
