"""Coffee chats on the Slack App Home, and the welcome when someone joins.

Both answer the same question — "what did I just sign up for, and when does it
happen" — which previously had no answer anywhere in Slack between rounds.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.modules.connect.rounds import cadence_phrase, upcoming_round_date

THURSDAY = date(2026, 9, 17)


# ── cadence_phrase ───────────────────────────────────────────────────────────


def test_weekly_reads_as_every_week():
    assert cadence_phrase(1) == "every week"


def test_fortnightly_counts_the_weeks():
    assert cadence_phrase(2) == "every 2 weeks"


def test_a_missing_cadence_is_treated_as_weekly():
    assert cadence_phrase(None) == "every week"
    assert cadence_phrase(0) == "every week"


def test_nonsense_does_not_raise_into_a_welcome_message():
    assert cadence_phrase("soon") == "every week"


# ── upcoming_round_date ──────────────────────────────────────────────────────


def test_a_new_programme_lands_on_its_own_weekday():
    """Joining on a Thursday must not promise a Monday chat today."""
    assert upcoming_round_date({"day_of_week": 0, "interval_weeks": 1}, THURSDAY) == date(2026, 9, 21)


def test_joining_on_the_day_itself_means_today():
    assert upcoming_round_date({"day_of_week": 3, "interval_weeks": 1}, THURSDAY) == THURSDAY


def test_a_running_programme_counts_from_its_last_round():
    prog = {"day_of_week": 0, "interval_weeks": 1, "last_round": date(2026, 9, 14)}
    assert upcoming_round_date(prog, THURSDAY) == date(2026, 9, 21)


def test_a_fortnightly_programme_waits_two_weeks():
    prog = {"day_of_week": 0, "interval_weeks": 2, "last_round": date(2026, 9, 14)}
    assert upcoming_round_date(prog, THURSDAY) == date(2026, 9, 28)


def test_an_overdue_programme_does_not_name_a_date_in_the_past():
    """A programme whose last round was long ago must not tell someone their
    next introduction already happened."""
    prog = {"day_of_week": 0, "interval_weeks": 1, "last_round": date(2026, 8, 3)}
    assert upcoming_round_date(prog, THURSDAY) >= THURSDAY


def test_a_datetime_last_round_is_accepted():
    """recent_rounds returns timestamps, not dates."""
    import datetime as dt

    prog = {"day_of_week": 0, "interval_weeks": 1, "last_round": dt.datetime(2026, 9, 14, 10, 0)}
    assert upcoming_round_date(prog, THURSDAY) == date(2026, 9, 21)


def test_a_missing_weekday_falls_back_to_today():
    assert upcoming_round_date({"interval_weeks": 1}, THURSDAY) == THURSDAY


def test_the_date_is_never_more_than_a_cadence_away():
    prog = {"day_of_week": 2, "interval_weeks": 1}
    assert upcoming_round_date(prog, THURSDAY) - THURSDAY <= timedelta(days=7)
