-- Clear has_blockers for answers meaning "not applicable".
--
-- 024 recomputed the flag against a list of ways people write "nothing", but
-- that list carried "na" and not "n/a". blockers.reports_a_blocker splits an
-- answer into words on whitespace, commas and slashes before deciding, so
-- "n/a" became {"n", "a"}; "n" is a no-word, "a" is not, and the answer came
-- back as a blocker.
--
-- 024 happened to clear the plain "N/A" rows through a different rule, so the
-- ones left are the bulleted forms and the doubled-letter typo. Every standup
-- written since then has been flagged wrongly, which is the part that matters:
-- this migration cleans up the rows, and the phrase list in blockers.py stops
-- it recurring.
--
-- Like 024, this only ever clears a flag and never sets one.

CREATE OR REPLACE FUNCTION morgenruf_normalise_answer(txt TEXT) RETURNS TEXT AS $$
  SELECT btrim(
    regexp_replace(
      lower(
        btrim(
          regexp_replace(
            regexp_replace(
              regexp_replace(coalesce(txt, ''), ':[a-z0-9_+-]+:', ' ', 'g'),
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

UPDATE standups
SET has_blockers = FALSE
WHERE has_blockers
  AND morgenruf_normalise_answer(blockers) IN ('n/a', 'n.a', 'n\a', 'nn');

DROP FUNCTION IF EXISTS morgenruf_normalise_answer(TEXT);
