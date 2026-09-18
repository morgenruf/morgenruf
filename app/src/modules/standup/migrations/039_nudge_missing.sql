-- A private nudge for people who have not filed yet.
--
-- Off by default. A reminder nobody asked for is an interruption, and a
-- workspace should choose to send one rather than discover it was sent.
--
-- Deliberately per schedule rather than per workspace: a team running a morning
-- and an evening standup usually wants this on one of them, not both.
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS nudge_missing BOOLEAN NOT NULL DEFAULT FALSE;
-- Minutes before the report posts. The window closing is the moment a nudge is
-- still worth acting on; the next morning it is only a telling-off.
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS nudge_minutes_before INT NOT NULL DEFAULT 20;
