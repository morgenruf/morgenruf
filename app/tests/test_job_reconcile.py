"""Namespaced job ids and reconcile-by-diff."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from src.core.scheduler import JobSpec, job_id, reconcile_jobs

TRIGGER = CronTrigger(day_of_week=0, hour=10, minute=0, timezone="UTC")


def fake_scheduler(existing_ids):
    s = MagicMock()
    s.get_jobs.return_value = [MagicMock(id=i, trigger=TRIGGER, args=(1,)) for i in existing_ids]
    return s


def desired(ids):
    return {i: JobSpec(key=i, trigger=TRIGGER, func=print, args=(1,)) for i in ids}


def test_job_id_is_namespaced_by_module_and_team():
    assert job_id("connect", "T1", "round") == "connect:T1:round"


def test_adds_missing_jobs():
    s = fake_scheduler([])
    added, removed = reconcile_jobs(s, desired(["connect:T1:round"]))
    assert added == ["connect:T1:round"]
    assert removed == []


def test_removes_jobs_that_are_no_longer_desired():
    s = fake_scheduler(["connect:T1:round"])
    added, removed = reconcile_jobs(s, desired([]))
    assert added == []
    assert removed == ["connect:T1:round"]
    s.remove_job.assert_called_once_with("connect:T1:round")


def test_leaves_unchanged_jobs_alone():
    s = fake_scheduler(["connect:T1:round"])
    added, removed = reconcile_jobs(s, desired(["connect:T1:round"]))
    assert (added, removed) == ([], [])
    s.remove_job.assert_not_called()
    s.add_job.assert_not_called()


def test_disabling_a_module_removes_only_its_jobs():
    s = fake_scheduler(["connect:T1:round", "standup:T1:daily"])
    added, removed = reconcile_jobs(s, desired(["standup:T1:daily"]))
    assert removed == ["connect:T1:round"]


def test_jobs_outside_the_namespace_are_never_removed():
    """Legacy standup job ids predate namespacing and must survive.

    Removing them would stop standups in production.
    """
    s = fake_scheduler(["legacy-workspace-T1", "connect:T1:round"])
    added, removed = reconcile_jobs(s, desired(["connect:T1:round"]))
    assert removed == []


def test_real_standup_job_ids_are_not_touched():
    """Guards against the namespace check being loosened later.

    These are the id shapes build_scheduler actually creates today.
    """
    live = [
        "member_sync",
        "schedule_sync",
        "token_maintenance",
        "digest_T01ABC",
        "manager_digest_T01ABC",
        "reminder_T01ABC",
        "reminder_schedule_T01ABC_7",
        "report_T01ABC",
        "report_schedule_T01ABC_7",
        "standup_T01ABC",
        "weekend_reminder_schedule_T01ABC_7",
    ]
    s = fake_scheduler(live)
    added, removed = reconcile_jobs(s, desired([]))
    assert removed == []


# ── A changed job is replaced ───────────────────────────────────────────────
#
# The job id of a Connect round is the programme id, so moving a programme to
# another day, hour or timezone kept the id. Reconciliation only added and
# removed by id, and the old trigger went on firing at the old time.


@pytest.fixture()
def real_scheduler():
    s = BackgroundScheduler(timezone="UTC")
    s.start(paused=True)
    yield s
    s.shutdown(wait=False)


def _round(trigger, args=(7,)):
    return {"connect:T1:round:7": JobSpec(key="round:7", trigger=trigger, func=print, args=args)}


def _fields(job) -> dict:
    return {f.name: str(f) for f in job.trigger.fields}


@pytest.mark.parametrize(
    "moved",
    [
        CronTrigger(day_of_week=2, hour=10, minute=0, timezone="UTC"),
        CronTrigger(day_of_week=0, hour=14, minute=0, timezone="UTC"),
        CronTrigger(day_of_week=0, hour=10, minute=30, timezone="UTC"),
        CronTrigger(day_of_week=0, hour=10, minute=0, timezone="America/Toronto"),
    ],
    ids=["day", "hour", "minute", "timezone"],
)
def test_a_moved_programme_fires_at_its_new_time(real_scheduler, moved):
    reconcile_jobs(real_scheduler, _round(TRIGGER))
    added, removed = reconcile_jobs(real_scheduler, _round(moved))
    assert (added, removed) == ([], [])
    job = real_scheduler.get_job("connect:T1:round:7")
    assert _fields(job) == {f.name: str(f) for f in moved.fields}
    assert str(job.trigger.timezone) == str(moved.timezone)


def test_changed_args_replace_the_job(real_scheduler):
    """How the stale bot token was dropped from Connect jobs already live."""
    reconcile_jobs(real_scheduler, _round(TRIGGER, args=(7, "xoxe-old")))
    reconcile_jobs(real_scheduler, _round(TRIGGER, args=(7,)))
    assert real_scheduler.get_job("connect:T1:round:7").args == (7,)


def test_an_unchanged_job_keeps_its_next_run_time(real_scheduler):
    """Replacing every job on every two minute pass would keep resetting them."""
    from datetime import datetime, timedelta, timezone

    reconcile_jobs(real_scheduler, _round(TRIGGER))
    pinned = datetime.now(timezone.utc) + timedelta(minutes=3)
    real_scheduler.modify_job("connect:T1:round:7", next_run_time=pinned)

    # A fresh but identical spec, as plan_jobs builds on every pass.
    reconcile_jobs(real_scheduler, _round(CronTrigger(day_of_week=0, hour=10, minute=0, timezone="UTC")))
    assert real_scheduler.get_job("connect:T1:round:7").next_run_time == pinned


def test_replacements_are_logged(real_scheduler, caplog):
    import logging

    reconcile_jobs(real_scheduler, _round(TRIGGER))
    with caplog.at_level(logging.INFO, logger="src.core.scheduler"):
        reconcile_jobs(real_scheduler, _round(CronTrigger(day_of_week=3, hour=10, minute=0, timezone="UTC")))
    assert "module jobs replaced after a trigger or args change: 1" in caplog.text
