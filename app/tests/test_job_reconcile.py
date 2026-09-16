"""Namespaced job ids and reconcile-by-diff."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.scheduler import job_id, reconcile_jobs


def fake_scheduler(existing_ids):
    s = MagicMock()
    s.get_jobs.return_value = [MagicMock(id=i) for i in existing_ids]
    return s


def desired(ids):
    return {i: MagicMock() for i in ids}


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
