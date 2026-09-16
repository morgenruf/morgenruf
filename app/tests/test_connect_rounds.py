"""Deciding when a coffee chat round is due.

APScheduler's cron cannot express "every two weeks" cleanly, so the job fires
weekly and this decides whether today is actually a round day.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.modules.connect.rounds import is_round_due, next_round_date


def d(m, day):
    return date(2026, m, day)


def dt(m, day, hh=10):
    return datetime(2026, m, day, hh, 0, tzinfo=timezone.utc)


# ── is_round_due ─────────────────────────────────────────────────────────────

def test_a_weekly_programme_with_no_history_is_due():
    assert is_round_due(interval_weeks=1, last_round=None, today=d(9, 16)) is True


def test_a_weekly_programme_is_due_seven_days_later():
    assert is_round_due(interval_weeks=1, last_round=d(9, 9), today=d(9, 16)) is True


def test_a_weekly_programme_is_not_due_the_next_day():
    assert is_round_due(interval_weeks=1, last_round=d(9, 15), today=d(9, 16)) is False


def test_a_biweekly_programme_is_not_due_after_one_week():
    assert is_round_due(interval_weeks=2, last_round=d(9, 9), today=d(9, 16)) is False


def test_a_biweekly_programme_is_due_after_two_weeks():
    assert is_round_due(interval_weeks=2, last_round=d(9, 2), today=d(9, 16)) is True


def test_a_round_is_never_run_twice_on_the_same_day():
    assert is_round_due(interval_weeks=1, last_round=d(9, 16), today=d(9, 16)) is False


def test_a_missed_week_still_runs_rather_than_skipping():
    """If the bot was down, the round starts late instead of being lost."""
    assert is_round_due(interval_weeks=1, last_round=d(9, 1), today=d(9, 16)) is True


def test_a_biweekly_programme_overdue_by_a_month_runs():
    assert is_round_due(interval_weeks=2, last_round=d(8, 1), today=d(9, 16)) is True


# ── next_round_date ──────────────────────────────────────────────────────────

def test_next_round_is_one_interval_on():
    assert next_round_date(interval_weeks=1, last_round=d(9, 16)) == d(9, 23)
    assert next_round_date(interval_weeks=2, last_round=d(9, 16)) == d(9, 30)


def test_next_round_without_history_is_unknown():
    assert next_round_date(interval_weeks=1, last_round=None) is None
