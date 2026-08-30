-- Record which standup a submission belongs to.
--
-- standups stores team_id, user_id and standup_date, but not which schedule
-- asked. With several standups a day for the same person, that made two things
-- guesses rather than facts:
--
--   participation had to match submissions to expected occurrences per
--   (member, day) by count, handing them out in schedule_time order, so a
--   person who filed one of their two standups was credited to whichever came
--   first rather than the one they actually answered
--
--   blocker detection had to infer the questions from participant overlap,
--   because the questions live on the schedule
--
-- Nullable, because existing rows cannot be attributed after the fact. Older
-- rows keep the current behaviour; anything written from now on is exact.
-- ON DELETE SET NULL rather than CASCADE: deleting a schedule must not delete
-- the standup history people wrote.

ALTER TABLE standups
  ADD COLUMN IF NOT EXISTS schedule_id INTEGER
    REFERENCES standup_schedules(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_standups_schedule
  ON standups(team_id, schedule_id, standup_date);
