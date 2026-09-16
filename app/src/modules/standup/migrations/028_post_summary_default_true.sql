-- Migration 021 defaulted post_summary to FALSE so teams that did not want a
-- channel roll-up would not get one. It also promised a dashboard control to
-- turn it back on, and that control was never built, so the daily summary
-- became unreachable in every install: every schedule had it off and nothing
-- in the Slack modal or the dashboard could change it (#117).
--
-- The control now exists in both places, so the column default goes back to
-- TRUE and a new standup posts its summary unless the creator unticks the box.
ALTER TABLE standup_schedules ALTER COLUMN post_summary SET DEFAULT TRUE;

-- Deliberately no backfill. Existing schedules keep the value they have. Some
-- of them were set to FALSE by 021 rather than by their owner, but flipping
-- them on here would start posting to live channels with no warning, which is
-- the owner's call to make from the new toggle.
