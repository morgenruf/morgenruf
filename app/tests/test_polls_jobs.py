"""Polls close on their own when their time is up."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from apscheduler.triggers.interval import IntervalTrigger
from src.modules.polls import jobs

POLL = {
    "id": 4,
    "team_id": "T1",
    "created_by": "U1",
    "channel_id": "C1",
    "message_ts": "1.000",
    "question": "Q",
    "options": ["a", "b"],
    "anonymous": True,
    "multiple": False,
    "hide_results": True,
    "closes_at": None,
    "closed_at": None,
}


@pytest.fixture
def pdb(monkeypatch):
    import src.core.analytics as analytics
    import src.modules.polls.db as real

    fake = MagicMock()
    for name in ("open_poll_count", "due_polls", "close_poll", "get_poll", "tally", "voters"):
        monkeypatch.setattr(real, name, getattr(fake, name))
    fake.due_polls.return_value = [dict(POLL)]
    fake.get_poll.return_value = {**POLL, "closed_at": "now", "salt": None}
    fake.tally.return_value = [1, 2]
    monkeypatch.setattr(
        real, "redraw", lambda poll_id, draw: draw(fake.get_poll.return_value, fake.tally.return_value, None) or True
    )
    monkeypatch.setattr(analytics, "capture", MagicMock())
    return fake


@pytest.fixture
def client(monkeypatch):
    c = MagicMock()
    monkeypatch.setattr(jobs, "bot_client", lambda team_id: c)
    return c


def test_no_open_polls_no_job(pdb):
    pdb.open_poll_count.return_value = 0
    assert jobs.plan_jobs({"team_id": "T1", "bot_token": "x"}) == []


def test_open_polls_get_a_minutely_sweep_with_no_token_in_its_args(pdb):
    pdb.open_poll_count.return_value = 2
    (job,) = jobs.plan_jobs({"team_id": "T1", "bot_token": "xoxb-secret"})
    assert job.key == "close"
    assert isinstance(job.trigger, IntervalTrigger) and job.trigger.interval.total_seconds() == 60
    assert job.func is jobs.close_due_polls and job.args == ("T1",)


def test_a_database_error_raises_so_the_live_job_is_kept(pdb):
    pdb.open_poll_count.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        jobs.plan_jobs({"team_id": "T1", "bot_token": "x"})


def test_a_due_poll_is_closed_and_redrawn_once(pdb, client):
    pdb.close_poll.side_effect = [True, False]
    assert jobs.close_due_polls("T1") == 1
    assert jobs.close_due_polls("T1") == 0
    assert client.chat_update.call_count == 1
    kwargs = client.chat_update.call_args.kwargs
    assert kwargs["channel"] == "C1" and kwargs["ts"] == "1.000"
    assert "▓" in str(kwargs["blocks"])


def test_a_slack_error_does_not_reopen(pdb, client):
    pdb.close_poll.return_value = True
    client.chat_update.side_effect = RuntimeError("channel_not_found")
    assert jobs.close_due_polls("T1") == 1
    pdb.close_poll.assert_called_once_with(4)


def test_no_token_still_closes_in_the_database(pdb, monkeypatch):
    monkeypatch.setattr(jobs, "bot_client", lambda team_id: None)
    pdb.close_poll.return_value = True
    assert jobs.close_due_polls("T1") == 1


def test_the_module_plans_with_it():
    from src.modules.polls import MODULE

    assert MODULE.plan_jobs is jobs.plan_jobs
