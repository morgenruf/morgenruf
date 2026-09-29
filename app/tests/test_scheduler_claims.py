"""Each cron firing runs on one pod only.

During a rollout the old and new pods both run their in-memory scheduler, so a
standup due in that window used to go out twice. ClaimingExecutor claims
(job id, run time) in scheduler_runs first; the pod that loses skips it.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

for _name in ("pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

_had_scheduler = "scheduler" in sys.modules
import src.core.scheduler as sched_mod  # noqa: E402

if _had_scheduler:
    sched_mod = importlib.reload(sched_mod)

from apscheduler.triggers.cron import CronTrigger  # noqa: E402
from apscheduler.triggers.interval import IntervalTrigger  # noqa: E402

RUN_AT = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


def _job(trigger, job_id="schedule_T1_1"):
    job = MagicMock()
    job.id = job_id
    job.trigger = trigger
    job.max_instances = 1
    return job


def _executor():
    executor = sched_mod.ClaimingExecutor()
    executor._do_submit_job = MagicMock()
    executor._lock = MagicMock()
    executor._instances = {"schedule_T1_1": 0}
    return executor


def _db(claimed=True, error=None):
    db = MagicMock()
    if error:
        db.claim_scheduler_run.side_effect = error
    else:
        db.claim_scheduler_run.return_value = claimed
    return patch.dict(sys.modules, {"src.core.db": db}), db


def test_cron_firing_runs_when_this_pod_claims_it():
    executor = _executor()
    ctx, db = _db(claimed=True)
    with ctx, patch("src.core.db", db, create=True):
        executor.submit_job(_job(CronTrigger(hour=9, timezone="UTC")), [RUN_AT])
    db.claim_scheduler_run.assert_called_once_with("schedule_T1_1", RUN_AT)
    executor._do_submit_job.assert_called_once()


def test_cron_firing_is_skipped_when_another_pod_claimed_it():
    executor = _executor()
    ctx, db = _db(claimed=False)
    with ctx, patch("src.core.db", db, create=True):
        executor.submit_job(_job(CronTrigger(hour=9, timezone="UTC")), [RUN_AT])
    executor._do_submit_job.assert_not_called()


def test_interval_jobs_are_never_claimed():
    """The reconcile loops must run on every pod."""
    executor = _executor()
    ctx, db = _db(claimed=False)
    with ctx, patch("src.core.db", db, create=True):
        executor.submit_job(_job(IntervalTrigger(minutes=5)), [RUN_AT])
    db.claim_scheduler_run.assert_not_called()
    executor._do_submit_job.assert_called_once()


def test_a_failed_claim_still_runs_the_job():
    executor = _executor()
    ctx, db = _db(error=Exception("db down"))
    with ctx, patch("src.core.db", db, create=True):
        executor.submit_job(_job(CronTrigger(hour=9, timezone="UTC")), [RUN_AT])
    executor._do_submit_job.assert_called_once()


def test_build_scheduler_uses_the_claiming_executor():
    db = MagicMock()
    db.get_all_active_schedules.return_value = []
    with patch.dict(sys.modules, {"src.core.db": db}), patch("src.core.db", db, create=True):
        scheduler = sched_mod.build_scheduler([])
    assert isinstance(scheduler._executors["default"], sched_mod.ClaimingExecutor)
    assert scheduler.get_job("scheduler_run_purge") is not None


# ── Misfire grace ───────────────────────────────────────────────────────────
#
# APScheduler drops a firing that starts more than misfire_grace_time late, and
# its default is one second. The claim above is a database round trip on the
# scheduler thread, so the second of two jobs due at the same minute started
# about 1.2 seconds late and was dropped ("Run time of job ... was missed by
# 0:00:01.2"). A standup report was lost this way on 2026-09-29.


def _started_scheduler():
    db = MagicMock()
    db.get_all_active_schedules.return_value = []
    with patch.dict(sys.modules, {"src.core.db": db}), patch("src.core.db", db, create=True):
        scheduler = sched_mod.build_scheduler([("T1", "xoxb-1", {"schedule_time": "09:00", "channel_id": "C1"})])
    # Job defaults are applied when a pending job is really added, which is on start.
    scheduler.start(paused=True)
    return scheduler


def test_every_job_gets_a_five_minute_grace_and_coalesces():
    scheduler = _started_scheduler()
    try:
        jobs = scheduler.get_jobs()
        assert any(j.id == "standup_T1" for j in jobs)
        for job in jobs:
            assert job.misfire_grace_time == sched_mod.MISFIRE_GRACE_SECS == 300, job.id
            assert job.coalesce is True, job.id
    finally:
        scheduler.shutdown(wait=False)


def test_module_jobs_added_later_get_the_same_grace():
    """reconcile_jobs passes no misfire settings, so it inherits the defaults."""
    scheduler = _started_scheduler()
    try:
        spec = sched_mod.JobSpec(key="round:1", trigger=CronTrigger(hour=9, timezone="UTC"), func=print)
        sched_mod.reconcile_jobs(scheduler, {"connect:T1:round:1": spec})
        job = scheduler.get_job("connect:T1:round:1")
        assert job.misfire_grace_time == 300
        assert job.coalesce is True
    finally:
        scheduler.shutdown(wait=False)


def test_a_firing_two_seconds_late_still_runs():
    from datetime import timedelta

    from apscheduler.executors.base import run_job

    ran = []
    scheduler = _started_scheduler()
    try:
        job = scheduler.add_job(ran.append, CronTrigger(hour=9, timezone="UTC"), args=("sent",), id="report_T9")
        late = datetime.now(timezone.utc) - timedelta(seconds=2)
        run_job(job, "default", [late], "test")
    finally:
        scheduler.shutdown(wait=False)
    assert ran == ["sent"]
