"""Pulse jobs: planned only for a programme that is on, kept on a failed read."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from src.modules.pulse import jobs


@pytest.fixture
def pdb(monkeypatch):
    import src.modules.pulse.db as real

    fake = MagicMock()
    monkeypatch.setattr(real, "get_program", fake.get_program)
    monkeypatch.setattr(real, "unscrubbed_count", fake.unscrubbed_count)
    fake.unscrubbed_count.return_value = 0
    return fake


PROGRAM = {"enabled": True, "day_of_week": 4, "hour": 14, "minute": 30, "timezone": "Asia/Calcutta"}


def test_a_programme_that_is_off_plans_nothing(pdb):
    pdb.get_program.return_value = {**PROGRAM, "enabled": False}
    assert jobs.plan_jobs({"team_id": "T1", "bot_token": "x"}) == []


def test_a_programme_that_is_off_still_closes_its_last_round(pdb):
    pdb.get_program.return_value = {**PROGRAM, "enabled": False}
    pdb.unscrubbed_count.return_value = 1
    (job,) = jobs.plan_jobs({"team_id": "T1", "bot_token": "x"})
    assert job.key == "tick" and job.func is jobs.tick


def test_a_database_error_raises_so_the_live_jobs_are_kept(pdb):
    pdb.get_program.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        jobs.plan_jobs({"team_id": "T1", "bot_token": "x"})


def test_on_it_plans_the_weekly_round_and_an_hourly_tick(pdb):
    pdb.get_program.return_value = dict(PROGRAM)
    round_job, tick_job = jobs.plan_jobs({"team_id": "T1", "bot_token": "xoxb-secret"})
    assert round_job.key == "round:4:14:30:Asia/Kolkata"
    assert isinstance(round_job.trigger, CronTrigger)
    assert str(round_job.trigger.timezone) == "Asia/Kolkata"
    assert round_job.func is jobs.send_round and round_job.args == ("T1",)
    assert tick_job.key == "tick" and isinstance(tick_job.trigger, IntervalTrigger)
    assert tick_job.trigger.interval.total_seconds() == 3600
    assert tick_job.func is jobs.tick and tick_job.args == ("T1",)


def test_an_unusable_timezone_plans_nothing(pdb):
    pdb.get_program.return_value = {**PROGRAM, "timezone": "Mars/Base"}
    assert jobs.plan_jobs({"team_id": "T1", "bot_token": "x"}) == []


def test_the_module_plans_with_it():
    from src.modules.pulse import MODULE

    assert MODULE.plan_jobs is jobs.plan_jobs


def test_tick_closes_due_rounds_even_with_the_module_off(monkeypatch):
    import src.modules.pulse.db as real

    closed = []
    monkeypatch.setattr(real, "close_due_rounds", lambda team_id: closed.append(team_id) or [])
    monkeypatch.setattr(real, "rounds_to_remind", lambda team_id: [])
    monkeypatch.setattr(jobs, "_active", lambda team_id: False)
    jobs.tick("T1")
    assert closed == ["T1"]


def test_a_failed_close_does_not_stop_the_reminders(monkeypatch):
    import src.modules.pulse.db as real

    def boom(team_id):
        raise RuntimeError("db down")

    asked = []
    monkeypatch.setattr(real, "close_due_rounds", boom)
    monkeypatch.setattr(real, "rounds_to_remind", lambda team_id: asked.append(team_id) or [])
    monkeypatch.setattr(jobs, "_active", lambda team_id: True)
    jobs.tick("T1")
    assert asked == ["T1"]
