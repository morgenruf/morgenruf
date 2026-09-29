"""Scheduled Connect rounds that used to be lost without a trace.

Two ways, both seen in production:

- The job carried the bot token it was planned with. Tokens rotate every 12
  hours and reconciliation never updated a live job's args, so a week later
  the round read the channel with an expired token and was skipped with only a
  warning.
- The weekly cron firing is the only thing that starts a round. A pod down at
  that minute, or a firing dropped as a misfire, cost the whole week.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

# Monday 28 September 2026, 10:30 in Toronto.
MONDAY_1030_TORONTO = datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
def jobs():
    # Imported here, not at module level: jobs pulls in the scheduler and the
    # database layer, and importing those during collection defeats the module
    # stubs other test files install.
    import src.modules.connect.jobs as jobs

    return jobs


def programme(**overrides) -> dict:
    return {
        "id": 1,
        "team_id": "T1",
        "channel_id": "C1",
        "enabled": True,
        "interval_weeks": 1,
        "day_of_week": 0,
        "hour": 10,
        "minute": 0,
        "timezone": "America/Toronto",
        "next_round_date": None,
        "last_scheduled_round": date(2026, 9, 21),
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        **overrides,
    }


# ── The token is read when the job runs ─────────────────────────────────────


def test_round_jobs_do_not_carry_a_bot_token(jobs, monkeypatch):
    import src.modules.connect.db as cdb

    monkeypatch.setattr(cdb, "active_programs", lambda: [programme(id=7, day_of_week=2, hour=9, minute=15)])
    planned = {j.key: j for j in jobs.plan_jobs({"team_id": "T1", "bot_token": "xoxe-rotates-in-12h"})}
    assert planned["round:7"].args == (7,)
    assert all("xoxe" not in str(j.args) for j in planned.values())


def test_the_client_uses_the_installations_current_token(jobs, monkeypatch):
    """A job planned before this change still passes its old token; it loses."""
    import src.core.db as db

    monkeypatch.setattr(db, "get_installation", lambda team: {"team_id": team, "bot_token": "xoxe-current"})
    assert jobs._client("xoxe-expired", "T1").token == "xoxe-current"
    assert jobs._client("", "T1").token == "xoxe-current"


def test_the_passed_token_is_the_fallback_when_the_database_is_down(jobs, monkeypatch):
    import src.core.db as db

    def boom(team):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "get_installation", boom)
    assert jobs._client("xoxe-passed", "T1").token == "xoxe-passed"
    assert jobs._client("", "T1") is None


def test_an_expiring_token_is_refreshed_before_use(jobs, monkeypatch):
    import src.core.db as db
    import src.core.scheduler as core_scheduler

    monkeypatch.setattr(db, "get_installation", lambda team: {"bot_token": "xoxe-old"})
    monkeypatch.setattr(core_scheduler, "_refresh_bot_token_if_needed", lambda team, inst: "xoxe-refreshed")
    assert jobs._client("", "T1").token == "xoxe-refreshed"


def test_kudos_jobs_do_not_carry_a_bot_token(monkeypatch):
    import src.core.db as db
    from src.modules.kudos import jobs as kjobs

    [job] = kjobs.plan_jobs({"team_id": "T1", "bot_token": "xoxe-rotates-in-12h"})
    assert job.args == ("T1",)
    monkeypatch.setattr(db, "get_installation", lambda team: {"bot_token": "xoxe-current"})
    assert kjobs._client("xoxe-expired", "T1").token == "xoxe-current"


# ── A missed round is started later the same day ────────────────────────────


def test_the_catch_up_is_planned_for_a_workspace_with_programmes(jobs, monkeypatch):
    import src.modules.connect.db as cdb
    from apscheduler.triggers.interval import IntervalTrigger

    monkeypatch.setattr(cdb, "active_programs", lambda: [programme()])
    planned = {j.key: j for j in jobs.plan_jobs({"team_id": "T1"})}
    assert planned["catchup"].func is jobs.start_missed_rounds
    assert planned["catchup"].args == ("T1",)
    assert isinstance(planned["catchup"].trigger, IntervalTrigger)


def test_no_catch_up_without_a_programme(jobs, monkeypatch):
    import src.modules.connect.db as cdb

    monkeypatch.setattr(cdb, "active_programs", lambda: [programme(team_id="T2")])
    assert [j.key for j in jobs.plan_jobs({"team_id": "T1"})] == ["followups"]


@pytest.mark.parametrize(
    "now, overrides, missed",
    [
        # Due, and half an hour past its time: the firing was lost.
        (MONDAY_1030_TORONTO, {}, True),
        # Inside the margin left for the cron firing itself.
        (datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc), {}, False),
        # Before the programme's time.
        (datetime(2026, 9, 28, 13, 30, tzinfo=timezone.utc), {}, False),
        # Tuesday: never on a day the programme does not run on.
        (datetime(2026, 9, 29, 14, 30, tzinfo=timezone.utc), {}, False),
        # 02:00 Tuesday in UTC is still Monday evening in Toronto.
        (datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc), {}, True),
        # 20:00 Monday in UTC is already Tuesday in Tokyo.
        (datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc), {"timezone": "Asia/Tokyo"}, False),
        # This week's round already ran.
        (MONDAY_1030_TORONTO, {"last_scheduled_round": date(2026, 9, 28)}, False),
        # A fortnightly programme in its off week.
        (MONDAY_1030_TORONTO, {"interval_weeks": 2}, False),
        # A round held back by a pinned date.
        (MONDAY_1030_TORONTO, {"next_round_date": date(2026, 10, 5)}, False),
        # Never run, created last week: due.
        (MONDAY_1030_TORONTO, {"last_scheduled_round": None}, True),
        # Never run, created after today's time: first round is next Monday.
        (
            datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc),
            {"last_scheduled_round": None, "created_at": datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)},
            False,
        ),
        # A broken timezone never matches rather than guessing.
        (MONDAY_1030_TORONTO, {"timezone": "Mars/Olympus"}, False),
    ],
    ids=[
        "missed",
        "inside-margin",
        "before-time",
        "wrong-weekday",
        "local-day-not-utc-day",
        "local-day-ahead-of-utc",
        "already-ran",
        "off-week",
        "pinned-later",
        "never-run",
        "created-after-time",
        "bad-timezone",
    ],
)
def test_when_a_round_counts_as_missed(jobs, now, overrides, missed):
    assert jobs._round_missed_today(programme(**overrides), now) is missed


@pytest.fixture
def catch_up(monkeypatch, jobs):
    import src.modules.connect.db as cdb

    started: list[tuple] = []

    def setup(programmes, now=MONDAY_1030_TORONTO, run_round=None):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz) if tz else now

        monkeypatch.setattr(jobs, "datetime", FixedDatetime)
        monkeypatch.setattr(cdb, "get_programs", lambda team: [p for p in programmes if p["team_id"] == team])
        monkeypatch.setattr(jobs, "run_round", run_round or (lambda *a, **k: started.append((a, k))))
        return started

    return setup


def test_a_missed_round_is_started(catch_up, jobs):
    started = catch_up([programme()])
    assert jobs.start_missed_rounds("T1") == 1
    # Not forced: run_round checks the cadence again, and create_round's
    # same-day guard stops a second round if one did start.
    assert started == [((1,), {})]


def test_disabled_and_other_workspace_programmes_are_left_alone(catch_up, jobs):
    started = catch_up([programme(id=1, enabled=False), programme(id=2, team_id="T2"), programme(id=3)])
    jobs.start_missed_rounds("T1")
    assert started == [((3,), {})]


def test_one_failing_programme_does_not_stop_the_rest(catch_up, jobs):
    started = []

    def run_round(program_id, *a, **k):
        if program_id == 1:
            raise RuntimeError("slack down")
        started.append(program_id)

    catch_up([programme(id=1), programme(id=2)], run_round=run_round)
    jobs.start_missed_rounds("T1")
    assert started == [2]


def test_unreadable_programmes_start_nothing(jobs, monkeypatch):
    import src.modules.connect.db as cdb

    def boom(team):
        raise RuntimeError("pool exhausted")

    monkeypatch.setattr(cdb, "get_programs", boom)
    assert jobs.start_missed_rounds("T1") == 0
