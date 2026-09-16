-- Recompute has_blockers for standups already stored.
--
-- has_blockers was set with:
--   answer.strip().lower() not in ('none','no','nope','-','n/a','')
-- applied to whatever landed in the third answer slot, whatever the schedule
-- actually asked there.
--
-- Two consequences on real data. Schedules whose third question is not about
-- blockers, for example "Availability in Hours", had answers like "4:30 Hrs"
-- counted as blockers. And the list above misses most of the ways people write
-- "nothing": across 589 flagged rows the commonest values were Na, ., n,
-- "• None", na, NA, 0. The bullet case is self inflicted, since the bot asks
-- for bullet points and the check never stripped the leading marker.
--
-- This pass only ever clears a flag, never sets one. A row that reads as a real
-- blocker keeps it. Anything ambiguous is left alone rather than guessed at.

-- 1. Strip list markers and punctuation from the edges, collapse whitespace,
--    lowercase. Mirrors blockers.normalise.
CREATE OR REPLACE FUNCTION morgenruf_normalise_answer(txt TEXT) RETURNS TEXT AS $$
  SELECT btrim(
    regexp_replace(
      lower(
        btrim(
          regexp_replace(
            regexp_replace(
              regexp_replace(coalesce(txt, ''), ':[a-z0-9_+-]+:', ' ', 'g'),  -- emoji shortcodes
              '[\r\n]+', ' ', 'g'
            ),
            '\s+', ' ', 'g'
          ),
          E' \t-–—*•·>.,:;!'
        )
      ),
      '\s*(for|as of|right)?\s*(now|today|yet|currently|atm|at the moment|so far|this week)\s*$', ''
    ),
    E' \t-–—*•·>.,:;!'
  );
$$ LANGUAGE SQL IMMUTABLE;

-- 2. Clear the flag where the answer says "nothing".
UPDATE standups
SET has_blockers = FALSE
WHERE has_blockers
  AND morgenruf_normalise_answer(blockers) IN (
    '', 'n', 'na', 'no', 'nope', 'none', 'nil', 'nothing', 'nothing today',
    'no blocker', 'no blockers', 'none today', 'not blocked', 'nothing blocking',
    'all good', 'all clear', 'clear', 'good', 'fine', 'ok', 'okay', 'nada',
    'zero', 'x', 'tbd'
  );

-- 3. Clear the flag where the answer is only a quantity. These come from
--    schedules asking about availability rather than blockers.
UPDATE standups
SET has_blockers = FALSE
WHERE has_blockers
  AND morgenruf_normalise_answer(blockers) ~ '^[0-9\s.:,/hms+-]*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)?$';

-- 4. Clear the flag for standups belonging to a schedule that does not ask
--    about blockers at all. Matched through participants, because standups
--    carry no schedule id. Only applied where every active schedule the person
--    belongs to asks something other than blockers, so someone in both kinds of
--    standup keeps their flags.
UPDATE standups s
SET has_blockers = FALSE
WHERE s.has_blockers
  AND EXISTS (
    SELECT 1 FROM standup_schedules sc
    WHERE sc.team_id = s.team_id AND sc.active AND s.user_id = ANY(sc.participants)
  )
  AND NOT EXISTS (
    SELECT 1 FROM standup_schedules sc
    WHERE sc.team_id = s.team_id AND sc.active AND s.user_id = ANY(sc.participants)
      AND lower(coalesce(sc.questions->>2, '')) ~ 'block|impediment|stuck'
  );

DROP FUNCTION IF EXISTS morgenruf_normalise_answer(TEXT);
