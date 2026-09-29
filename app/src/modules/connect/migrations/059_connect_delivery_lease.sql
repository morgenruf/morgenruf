-- Delivering a round sends one group DM per match, about two minutes for a
-- 200 person channel. A pod killed partway (a rollout) left the rest unsent
-- for good: nothing called delivery again. The follow-up sweep now resumes
-- such rounds, and this lease stops two pods from delivering one round at the
-- same time. The delivering pod renews it after every match.
ALTER TABLE connect_rounds ADD COLUMN IF NOT EXISTS delivery_claimed_at TIMESTAMPTZ;
