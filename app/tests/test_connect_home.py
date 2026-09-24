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


# ── snooze, leave, and coming back ───────────────────────────────────────────
# connect_optouts.paused_until has been in the schema and honoured by the
# eligibility query since the table existed, but nothing ever wrote one, so a
# snooze was a column with no feature attached. These assert the three states
# the query already distinguishes.


def _eligibility_sql():
    import inspect

    from src.modules.connect import db

    return inspect.getsource(db.optout_user_ids)


def test_a_permanent_opt_out_is_excluded():
    assert "mode = 'off'" in _eligibility_sql()


def test_a_snooze_is_excluded_only_until_its_date():
    sql = _eligibility_sql()
    assert "mode = 'paused'" in sql
    assert "paused_until >= CURRENT_DATE" in sql


def test_snooze_writes_the_date_the_query_reads():
    import inspect

    from src.modules.connect import db

    src = inspect.getsource(db.snooze)
    assert 'mode="paused"' in src
    assert "paused_until=until" in src


def test_personal_state_tells_the_three_apart():
    import inspect

    from src.modules.connect import db

    src = inspect.getsource(db.personal_state)
    for expected in ('"in"', '"out"', '"snoozed"'):
        assert expected in src


def test_a_forced_round_skips_only_the_cadence_check():
    """Everything after it must be unchanged, so a forced round is an ordinary
    round: same matching, same history, same idempotency guard."""
    import inspect

    from src.modules.connect import jobs

    src = inspect.getsource(jobs.run_round)
    assert "if not force and not is_round_due(" in src
    assert src.count("is_round_due(") == 1


def test_a_manual_round_does_not_move_the_next_scheduled_one():
    """A Monday programme tried by hand on a Thursday still runs that Monday."""
    prog = {
        "day_of_week": 0,
        "interval_weeks": 1,
        "last_round": THURSDAY,
        "last_scheduled_round": None,
    }
    assert upcoming_round_date(prog, THURSDAY) == date(2026, 9, 21)


def test_the_date_always_lands_on_the_programme_weekday():
    """Counting a week from a Thursday run used to name a Thursday, a day the
    Monday job never fires on."""
    prog = {
        "day_of_week": 0,
        "interval_weeks": 1,
        "last_round": date(2026, 9, 17),
        "last_scheduled_round": date(2026, 9, 17),
    }
    nxt = upcoming_round_date(prog, date(2026, 9, 24))
    assert nxt.weekday() == 0
    assert nxt == date(2026, 9, 28)


def test_a_pinned_date_holds_the_round_until_the_weekday_after_it():
    prog = {
        "day_of_week": 0,
        "interval_weeks": 1,
        "last_scheduled_round": date(2026, 9, 14),
        "next_round_date": date(2026, 10, 7),
    }
    assert upcoming_round_date(prog, THURSDAY) == date(2026, 10, 12)
