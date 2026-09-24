"""run_round decides whether today is a round day before touching Slack.

These stop at create_round, which is where the cadence decision shows: a round
that is not due never gets that far.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

MONDAY = datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)  # 10:00 in Toronto


@pytest.fixture
def jobs():
    # Imported here, not at module level: jobs pulls in the scheduler and the
    # database layer, and importing those during collection defeats the module
    # stubs other test files install.
    import src.modules.connect.jobs as jobs

    return jobs


@pytest.fixture
def run(monkeypatch, jobs):
    import src.modules.connect.db as cdb

    created: list[dict] = []

    def setup(program: dict, now: datetime = MONDAY):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz) if tz else now

        monkeypatch.setattr(jobs, "datetime", FixedDatetime)
        base = {
            "id": 1,
            "team_id": "T1",
            "channel_id": "C1",
            "enabled": True,
            "interval_weeks": 1,
            "day_of_week": 0,
            "timezone": "America/Toronto",
            "next_round_date": None,
            "last_round": None,
            "last_scheduled_round": None,
        }
        monkeypatch.setattr(cdb, "get_program", lambda _id: {**base, **program})
        monkeypatch.setattr(cdb, "optout_user_ids", lambda *_: set())
        monkeypatch.setattr(jobs, "_client", lambda *_: object())
        monkeypatch.setattr(jobs.api, "channel_member_ids", lambda *_: ["U1", "U2", "U3"])

        import src.core.roster as roster

        monkeypatch.setattr(
            roster, "eligible_members", lambda _t: [type("M", (), {"user_id": u})() for u in ("U1", "U2", "U3")]
        )

        def create_round(program_id, team_id, scheduled_for, manual=False):
            created.append({"program_id": program_id, "manual": manual})
            return None  # stop here: "a round already exists"

        monkeypatch.setattr(cdb, "create_round", create_round)
        return created

    return setup


def test_a_manual_thursday_round_does_not_cancel_the_next_monday(run, jobs):
    """The Sep 2026 regression: a Thursday "Run now" made Monday "not due"."""
    created = run({"last_round": date(2026, 9, 17), "last_scheduled_round": None})
    jobs.run_round(1)
    assert created == [{"program_id": 1, "manual": False}]


def test_a_scheduled_round_last_week_makes_this_monday_due(run, jobs):
    created = run({"last_round": date(2026, 9, 14), "last_scheduled_round": date(2026, 9, 14)})
    jobs.run_round(1)
    assert created == [{"program_id": 1, "manual": False}]


def test_a_fortnightly_programme_still_skips_the_off_week(run, jobs):
    created = run({"interval_weeks": 2, "last_round": date(2026, 9, 14), "last_scheduled_round": date(2026, 9, 14)})
    jobs.run_round(1)
    assert created == []


def test_run_now_is_recorded_as_manual(run, jobs):
    created = run({"last_scheduled_round": date(2026, 9, 21)})
    jobs.run_round(1, force=True)
    assert created == [{"program_id": 1, "manual": True}]


def test_today_is_the_programme_day_not_the_server_day(run, jobs):
    """23:30 Sunday in Toronto is already Monday in UTC. The weekly round ran
    on the Monday before, so Toronto's Sunday is six days on and not due."""
    late_sunday = datetime(2026, 9, 21, 3, 30, tzinfo=timezone.utc)
    created = run({"last_scheduled_round": date(2026, 9, 14)}, now=late_sunday)
    jobs.run_round(1)
    assert created == []
