-- One row per cron firing that a pod has claimed. Every pod runs its own
-- in-memory scheduler, and during a rollout the old and new pods overlap, so
-- both used to fire the same standup, report or reminder. The executor inserts
-- (job_id, run_at) before running a cron job, and only the pod whose insert
-- lands runs it. Rows older than a week are deleted nightly.
CREATE TABLE IF NOT EXISTS scheduler_runs (
    job_id TEXT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, run_at)
);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_claimed_at ON scheduler_runs (claimed_at);
