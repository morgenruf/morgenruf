"""The day 3 nudge and day 6 closing question must survive the scheduler.

They used to be one-off DateTrigger jobs on the in-memory scheduler, with ids
in the module namespace (connect:T1:nudge:42). Module job reconciliation runs
every two minutes and removes every namespaced job no module planned, and
Connect only planned its round jobs, so the follow-ups were deleted about two
minutes after they were queued and no round was ever nudged or closed. A
restart would have dropped them too.

They now live in connect_followups, and a sweep that Connect plans for each
workspace sends whatever is due.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from src.core.scheduler import sync_module_jobs

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def real_scheduler():
    s = BackgroundScheduler(timezone="UTC")
    s.start(paused=True)
    yield s
    s.shutdown(wait=False)


@pytest.fixture()
def connect_wiring(monkeypatch, real_scheduler):
    """One workspace with Connect active and one enabled weekly programme."""
    import src.core.db as db
    import src.core.modules as core_modules
    import src.core.scheduler as core_scheduler
    import src.modules as registry_mod
    import src.modules.connect.db as cdb
    from src.modules.connect import MODULE

    program = {
        "id": 7,
        "team_id": "T1",
        "enabled": True,
        "day_of_week": 0,
        "hour": 10,
        "minute": 0,
        "timezone": "UTC",
    }
    monkeypatch.setattr(db, "get_all_installations", lambda: [{"team_id": "T1", "bot_token": "xoxb-1"}])
    monkeypatch.setattr(db, "granted_scopes", lambda t: list(MODULE.required_scopes))
    monkeypatch.setattr(db, "module_settings", lambda t: {})
    monkeypatch.setattr(core_modules, "deploy_allowlist", lambda: None)
    monkeypatch.setattr(core_modules, "active_modules", lambda *a, **k: [MODULE])
    monkeypatch.setattr(registry_mod, "REGISTRY", (MODULE,), raising=False)
    monkeypatch.setattr(cdb, "active_programs", lambda: [program])
    monkeypatch.setattr(core_scheduler, "_scheduler", real_scheduler)
    return real_scheduler


def test_followups_survive_module_job_reconciliation(connect_wiring, monkeypatch):
    """Queue a round's follow-ups, reconcile as the two minute sync does, and
    check the round still has a way to be nudged and closed.

    Before the fix this failed with:
    reconciliation removed ['connect:T1:close:42', 'connect:T1:nudge:42']
    """
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    scheduler = connect_wiring
    queued = []
    monkeypatch.setattr(cdb, "queue_followups", lambda *a, **k: queued.append((a, k)))

    sync_module_jobs(scheduler)
    jobs._queue_followups(42, "T1")
    before = {j.id for j in scheduler.get_jobs()}

    sync_module_jobs(scheduler)
    after = {j.id for j in scheduler.get_jobs()}

    lost = sorted(before - after)
    assert lost == [], f"reconciliation removed {lost}"
    assert "connect:T1:followups" in after
    assert queued == [(("T1", jobs.NUDGE_AFTER_DAYS, jobs.CLOSE_AFTER_DAYS), {"round_id": 42})]


def test_nothing_is_left_on_the_in_memory_scheduler_per_round(connect_wiring, monkeypatch):
    """A restart loses whatever is only in memory, so a round adds no jobs."""
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    monkeypatch.setattr(cdb, "queue_followups", lambda *a, **k: 2)
    sync_module_jobs(connect_wiring)
    before = {j.id for j in connect_wiring.get_jobs()}
    jobs._queue_followups(42, "T1")
    assert {j.id for j in connect_wiring.get_jobs()} == before
    assert "DateTrigger" not in Path(jobs.__file__).read_text()


def test_the_sweep_is_planned_even_when_programmes_cannot_be_read(monkeypatch):
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    def boom():
        raise RuntimeError("pool exhausted")

    monkeypatch.setattr(cdb, "active_programs", boom)
    planned = jobs.plan_jobs({"team_id": "T1", "bot_token": "x"})
    assert [j.key for j in planned] == ["followups"]
    assert planned[0].func is jobs.send_due_followups
    assert planned[0].args == ("T1",)


def test_a_failed_queue_is_logged_not_raised(monkeypatch):
    """The round has already been delivered; the sweep backfills the rows."""
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(cdb, "queue_followups", boom)
    jobs._queue_followups(42, "T1")


class FakeStore:
    """Stands in for the follow-up rows, recording what the sweep does."""

    def __init__(self, rows):
        self.rows = rows
        self.finished: dict[tuple[int, str], str] = {}
        self.states: dict[int, str] = {}
        self.backfilled: list[str] = []

    def install(self, monkeypatch, jobs):
        import src.modules.connect.db as cdb

        monkeypatch.setattr(cdb, "queue_followups", lambda team, *a, **k: self.backfilled.append(team) or 0)
        monkeypatch.setattr(cdb, "claim_due_followups", lambda team, lease, limit=50: list(self.rows))
        monkeypatch.setattr(
            cdb, "finish_followup", lambda r, kind, outcome: self.finished.__setitem__((r, kind), outcome)
        )
        monkeypatch.setattr(cdb, "set_round_state", lambda r, state, *a: self.states.__setitem__(r, state))

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW.astimezone(tz) if tz else NOW

        monkeypatch.setattr(jobs, "datetime", FixedDatetime)


def row(round_id, kind, due_ago, attempts=1):
    return {"round_id": round_id, "kind": kind, "due_at": NOW - due_ago, "attempts": attempts, "team_id": "T1"}


@pytest.fixture
def sweep(monkeypatch):
    from src.modules.connect import jobs

    sent = []
    monkeypatch.setattr(jobs, "nudge_round", lambda r, tok, team: sent.append(("nudge", r, tok, team)) or True)
    monkeypatch.setattr(jobs, "close_round", lambda r, tok, team: sent.append(("close", r, tok, team)) or True)

    def run(rows):
        store = FakeStore(rows)
        store.install(monkeypatch, jobs)
        count = jobs.send_due_followups("T1")
        return store, sent, count

    return run


def test_due_followups_are_sent_and_marked_done(sweep):
    store, sent, count = sweep([row(1, "nudge", timedelta(minutes=3)), row(2, "close", timedelta(hours=5))])
    # An empty token makes _client read the installation's current one.
    assert sent == [("nudge", 1, "", "T1"), ("close", 2, "", "T1")]
    assert store.finished == {(1, "nudge"): "sent", (2, "close"): "sent"}
    assert count == 2


def test_every_sweep_backfills_open_rounds_first(sweep):
    store, _, _ = sweep([])
    assert store.backfilled == ["T1"]


def test_a_nudge_more_than_a_day_late_is_skipped(sweep):
    store, sent, _ = sweep([row(1, "nudge", timedelta(days=1, minutes=1))])
    assert sent == []
    assert store.finished == {(1, "nudge"): "skipped_stale"}
    assert store.states == {}


def test_a_stale_close_closes_the_round_without_messaging(sweep):
    """Rounds left open by the old in-memory jobs end up here after deploy."""
    store, sent, _ = sweep([row(1, "nudge", timedelta(days=27)), row(1, "close", timedelta(days=24))])
    assert sent == []
    assert store.finished == {(1, "nudge"): "skipped_stale", (1, "close"): "skipped_stale"}
    assert store.states == {1: "closed"}


def test_a_close_two_days_late_is_still_sent(sweep):
    """A few hours or days of downtime should not cost the round its question."""
    store, sent, _ = sweep([row(1, "close", timedelta(days=2))])
    assert sent == [("close", 1, "", "T1")]


def test_a_failure_is_left_claimed_for_a_retry(sweep, monkeypatch):
    from src.modules.connect import jobs

    def boom(*a):
        raise RuntimeError("slack down")

    monkeypatch.setattr(jobs, "nudge_round", boom)
    store, _, count = sweep([row(1, "nudge", timedelta(minutes=3), attempts=1)])
    assert store.finished == {}
    assert count == 0


def test_a_follow_up_that_keeps_failing_is_given_up_on(sweep, monkeypatch):
    from src.modules.connect import jobs

    def boom(*a):
        raise RuntimeError("slack down")

    monkeypatch.setattr(jobs, "close_round", boom)
    store, _, _ = sweep([row(1, "close", timedelta(minutes=3), attempts=jobs.FOLLOWUP_MAX_ATTEMPTS)])
    assert store.finished == {(1, "close"): "failed"}


def test_one_failure_does_not_stop_the_rest(sweep, monkeypatch):
    from src.modules.connect import jobs

    sent = []

    def nudge(r, tok, team):
        if r == 1:
            raise RuntimeError("slack down")
        sent.append(r)
        return True

    monkeypatch.setattr(jobs, "nudge_round", nudge)
    store, _, _ = sweep([row(1, "nudge", timedelta(minutes=3)), row(2, "nudge", timedelta(minutes=3))])
    assert sent == [2]
    assert store.finished == {(2, "nudge"): "sent"}


@pytest.fixture
def no_token(monkeypatch):
    """No usable Slack token, and a record of what the real senders touch."""
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    touched = []
    monkeypatch.setattr(jobs, "_client", lambda *a: None)
    monkeypatch.setattr(cdb, "matches_for_close", lambda r: touched.append(("close", r)) or [])
    monkeypatch.setattr(cdb, "matches_for_nudge", lambda r: touched.append(("nudge", r)) or [])
    return touched


@pytest.mark.parametrize("kind", ["nudge", "close"])
def test_without_a_token_the_follow_up_is_retried_not_marked_sent(no_token, monkeypatch, kind):
    """close_round used to return early here and the row was recorded as sent,
    leaving a round that never closed looking finished."""
    from src.modules.connect import jobs

    store = FakeStore([row(1, kind, timedelta(minutes=3), attempts=1)])
    store.install(monkeypatch, jobs)
    assert jobs.send_due_followups("T1") == 0
    assert store.finished == {}  # still claimed; retried after the lease
    assert store.states == {}  # and the round was not closed


@pytest.mark.parametrize("kind", ["nudge", "close"])
def test_without_a_token_it_ends_up_failed_not_sent(no_token, monkeypatch, kind):
    from src.modules.connect import jobs

    store = FakeStore([row(1, kind, timedelta(minutes=3), attempts=jobs.FOLLOWUP_MAX_ATTEMPTS)])
    store.install(monkeypatch, jobs)
    jobs.send_due_followups("T1")
    assert store.finished == {(1, kind): "failed"}


def test_close_round_reports_whether_it_closed(no_token, monkeypatch):
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    states = []
    monkeypatch.setattr(cdb, "set_round_state", lambda r, s, *a: states.append((r, s)))
    assert jobs.close_round(1, "", "T1") is False
    assert states == []

    monkeypatch.setattr(jobs, "_client", lambda *a: object())
    monkeypatch.setattr(jobs, "_post_round_stats", lambda *a: None)
    assert jobs.close_round(1, "", "T1") is True
    assert states == [(1, "closed")]


def test_nudge_round_reports_a_failed_post(monkeypatch):
    """A retry is safe: only matches still without nudged_at are reached."""
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    monkeypatch.setattr(jobs, "_client", lambda *a: object())
    monkeypatch.setattr(jobs.api, "throttle", lambda: None)
    monkeypatch.setattr(jobs.api, "has_replies", lambda c, ch: False)
    monkeypatch.setattr(cdb, "matches_for_nudge", lambda r: [{"id": 1, "mpim_channel_id": "G1"}])
    nudged = []
    monkeypatch.setattr(cdb, "mark_nudged", nudged.append)

    monkeypatch.setattr(jobs.api, "post", lambda *a: None)
    assert jobs.nudge_round(1, "", "T1") is True
    assert nudged == [1]

    def boom(*a):
        raise RuntimeError("slack down")

    monkeypatch.setattr(jobs.api, "post", boom)
    assert jobs.nudge_round(1, "", "T1") is False


def test_a_claim_failure_sends_nothing(monkeypatch):
    import src.modules.connect.db as cdb
    from src.modules.connect import jobs

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(cdb, "queue_followups", boom)
    monkeypatch.setattr(cdb, "claim_due_followups", boom)
    assert jobs.send_due_followups("T1") == 0


def test_the_claim_is_atomic_across_pods():
    """Two pods sweep at once; the SQL must hand each row to only one of them.

    Checked against a real Postgres while writing this; pinned here so the
    claim cannot quietly lose its locking.
    """
    import inspect

    import src.modules.connect.db as cdb

    src = inspect.getsource(cdb.claim_due_followups)
    assert "FOR UPDATE SKIP LOCKED" in src
    assert "done_at IS NULL" in src
    assert "claimed_at IS NULL OR claimed_at <" in src
