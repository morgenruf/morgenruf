"""What the Today view counts as asked, answered and still outstanding.

Reference clock for the whole file: Monday 2026-09-14 20:00 UTC, which is
already Tuesday 2026-09-15 in Asia/Kolkata. Every timezone case below turns on
that gap, because a workspace running a standup in one zone and a dashboard
read in another is the case that silently reports the wrong day.
"""

from __future__ import annotations

import datetime as dt

from src.modules.insights.today import (
    awaiting,
    blocked_from,
    expected_today,
    fires_today,
    next_chat_date,
)

NOW = dt.datetime(2026, 9, 14, 20, 0, tzinfo=dt.timezone.utc)  # Monday


def schedule(**kwargs):
    base = {
        "id": 1,
        "schedule_tz": "UTC",
        "schedule_days": "mon,tue,wed,thu,fri",
        "participants": ["U1", "U2"],
        "active": True,
    }
    base.update(kwargs)
    return base


# -- fires_today -------------------------------------------------------------


def test_a_weekday_schedule_fires_on_a_monday():
    assert fires_today(schedule(), NOW) is True


def test_a_schedule_that_does_not_run_today_is_skipped():
    assert fires_today(schedule(schedule_days="tue,thu"), NOW) is False


def test_an_inactive_schedule_never_fires():
    assert fires_today(schedule(active=False), NOW) is False


def test_the_day_is_decided_in_the_schedules_own_timezone():
    """20:00 UTC Monday is already Tuesday in Kolkata, so a Tuesday standup ran."""
    assert fires_today(schedule(schedule_days="tue", schedule_tz="Asia/Kolkata"), NOW) is True
    assert fires_today(schedule(schedule_days="mon", schedule_tz="Asia/Kolkata"), NOW) is False


def test_an_unknown_timezone_falls_back_to_utc_instead_of_raising():
    assert fires_today(schedule(schedule_tz="Mars/Olympus"), NOW) is True


# -- expected_today ----------------------------------------------------------


def test_participants_of_a_schedule_running_today_are_expected():
    assert expected_today([schedule()], {"U1", "U2"}, NOW) == ["U1", "U2"]


def test_people_on_vacation_or_deactivated_are_not_expected():
    """Eligibility arrives as a set from roster, so absence from it is the filter."""
    assert expected_today([schedule()], {"U1"}, NOW) == ["U1"]


def test_someone_in_two_schedules_is_expected_once():
    schedules = [schedule(id=1), schedule(id=2, participants=["U2", "U3"])]
    assert expected_today(schedules, {"U1", "U2", "U3"}, NOW) == ["U1", "U2", "U3"]


def test_a_schedule_not_running_today_contributes_nobody():
    schedules = [schedule(schedule_days="sat,sun", participants=["U9"])]
    assert expected_today(schedules, {"U9"}, NOW) == []


def test_a_schedule_with_no_participants_is_harmless():
    assert expected_today([schedule(participants=None)], {"U1"}, NOW) == []


def test_no_schedules_means_nobody_is_expected():
    assert expected_today([], {"U1"}, NOW) == []


# -- awaiting ----------------------------------------------------------------


def test_awaiting_is_the_expected_who_have_not_answered():
    assert awaiting(["U1", "U2", "U3"], {"U2"}) == ["U1", "U3"]


def test_awaiting_keeps_the_expected_order():
    assert awaiting(["U3", "U1", "U2"], set()) == ["U3", "U1", "U2"]


def test_someone_who_answered_without_being_expected_changes_nothing():
    assert awaiting(["U1"], {"U1", "U7"}) == []


# -- blocked_from ------------------------------------------------------------


def test_only_responses_flagged_as_blocked_are_returned():
    rows = [
        {"user_id": "U1", "real_name": "Ada", "blockers": "waiting on infra", "has_blockers": True},
        {"user_id": "U2", "real_name": "Bob", "blockers": "none", "has_blockers": False},
    ]
    assert [r["user_id"] for r in blocked_from(rows)] == ["U1"]


def test_the_blocker_text_comes_through():
    rows = [{"user_id": "U1", "real_name": "Ada", "blockers": "waiting on infra", "has_blockers": True}]
    assert blocked_from(rows)[0]["blockers"] == "waiting on infra"


def test_a_missing_flag_is_not_a_blocker():
    assert blocked_from([{"user_id": "U1", "blockers": "something"}]) == []


# -- next_chat_date ----------------------------------------------------------

TODAY = dt.date(2026, 9, 14)


def test_no_programme_means_no_date():
    assert next_chat_date(None, TODAY) is None


def test_a_round_already_on_the_books_wins():
    program = {
        "next_scheduled": dt.datetime(2026, 9, 21, 10, 0, tzinfo=dt.timezone.utc),
        "last_round": dt.datetime(2026, 9, 7, 10, 0, tzinfo=dt.timezone.utc),
        "interval_weeks": 1,
    }
    assert next_chat_date(program, TODAY) == dt.date(2026, 9, 21)


def test_without_a_scheduled_round_the_cadence_decides():
    program = {
        "next_scheduled": None,
        "last_round": dt.datetime(2026, 9, 7, 10, 0, tzinfo=dt.timezone.utc),
        "interval_weeks": 2,
    }
    assert next_chat_date(program, TODAY) == dt.date(2026, 9, 21)


def test_a_programme_that_never_ran_is_due_now():
    assert next_chat_date({"next_scheduled": None, "last_round": None}, TODAY) == TODAY


def test_a_missing_cadence_is_treated_as_weekly():
    program = {"last_round": dt.date(2026, 9, 7), "interval_weeks": None}
    assert next_chat_date(program, TODAY) == dt.date(2026, 9, 14)


# ── next_chat_date and the programme's own weekday ───────────────────────────
# A programme that had never run reported its next round as "today", whatever
# day it was. The Today page told a Thursday that a Monday coffee chat was
# about to happen.


def test_a_programme_that_has_never_run_lands_on_its_own_weekday():
    thursday = dt.date(2026, 9, 17)
    monday_programme = {"day_of_week": 0, "interval_weeks": 1}
    assert next_chat_date(monday_programme, thursday) == dt.date(2026, 9, 21)


def test_today_counts_when_it_is_the_programme_day():
    thursday = dt.date(2026, 9, 17)
    assert next_chat_date({"day_of_week": 3, "interval_weeks": 1}, thursday) == thursday


def test_tomorrow_when_the_programme_runs_tomorrow():
    thursday = dt.date(2026, 9, 17)
    assert next_chat_date({"day_of_week": 4, "interval_weeks": 1}, thursday) == dt.date(2026, 9, 18)


def test_a_missing_weekday_falls_back_to_today_rather_than_guessing():
    thursday = dt.date(2026, 9, 17)
    assert next_chat_date({"interval_weeks": 1}, thursday) == thursday
    assert next_chat_date({"day_of_week": None}, thursday) == thursday


def test_a_nonsense_weekday_is_ignored():
    thursday = dt.date(2026, 9, 17)
    assert next_chat_date({"day_of_week": 99}, thursday) == thursday
    assert next_chat_date({"day_of_week": "monday"}, thursday) == thursday


def test_a_programme_with_history_still_counts_from_the_last_round():
    """Unchanged: the cadence from the last round, so it cannot disagree with
    connect's own scheduler."""
    thursday = dt.date(2026, 9, 17)
    prog = {"day_of_week": 0, "interval_weeks": 1, "last_round": dt.date(2026, 9, 14)}
    assert next_chat_date(prog, thursday) == dt.date(2026, 9, 21)


def test_a_biweekly_programme_with_history_waits_two_weeks():
    prog = {"day_of_week": 0, "interval_weeks": 2, "last_round": dt.date(2026, 9, 14)}
    assert next_chat_date(prog, dt.date(2026, 9, 17)) == dt.date(2026, 9, 28)
