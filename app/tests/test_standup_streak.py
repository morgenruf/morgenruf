"""The App Home streak counts answered scheduled days in a row.

The old SQL grouped by `standup_date - ROW_NUMBER() OVER (ORDER BY standup_date
DESC)`, which gives consecutive days different groups, so every streak was 1.
These tests pin the counting against hand-picked calendars.

Reference week (2026-09): Mon 21, Tue 22, Wed 23, Thu 24, Fri 25, Sat 26,
Sun 27, Mon 28, Tue 29.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import src.core.db as db

MON_FRI = {0, 1, 2, 3, 4}


def d(day: int) -> date:
    return date(2026, 9, day)


class TestStreakFromDates:
    def test_consecutive_days_all_count(self):
        dates = [d(22), d(23), d(24), d(25)]
        assert db.streak_from_dates(dates, MON_FRI, today=d(25)) == 4

    def test_weekend_between_answers_does_not_break_it(self):
        dates = [d(24), d(25), d(28), d(29)]
        assert db.streak_from_dates(dates, MON_FRI, today=d(29)) == 4

    def test_unanswered_today_does_not_break_it_yet(self):
        dates = [d(24), d(25), d(28)]
        assert db.streak_from_dates(dates, MON_FRI, today=d(29)) == 3

    def test_missing_the_previous_scheduled_day_resets_to_zero(self):
        # Last answer Thursday, nothing on Friday or Monday, today is Tuesday.
        dates = [d(23), d(24)]
        assert db.streak_from_dates(dates, MON_FRI, today=d(29)) == 0

    def test_a_gap_stops_the_count(self):
        dates = [d(21), d(22), d(24), d(25)]
        assert db.streak_from_dates(dates, MON_FRI, today=d(25)) == 2

    def test_only_the_members_schedule_days_count(self):
        # A Monday, Wednesday, Friday standup: Tuesday and Thursday are not gaps.
        dates = [d(21), d(23), d(25), d(28)]
        assert db.streak_from_dates(dates, {0, 2, 4}, today=d(28)) == 4

    def test_holidays_are_skipped_not_missed(self):
        # Friday 25 is a company holiday.
        dates = [d(23), d(24), d(28)]
        assert db.streak_from_dates(dates, MON_FRI, today=d(28), holidays=[d(25)]) == 3

    def test_no_answers_is_zero(self):
        assert db.streak_from_dates([], MON_FRI, today=d(28)) == 0

    def test_accepts_iso_strings(self):
        assert db.streak_from_dates(["2026-09-28", "2026-09-25"], MON_FRI, today=d(28)) == 2


class TestGetStandupStreak:
    def test_reads_the_members_schedule_and_the_holidays(self):
        rows = [(d(23),), (d(24),), (d(28),)]
        schedules = [
            {"active": True, "participants": ["U1"], "schedule_days": "mon,tue,wed,thu,fri", "schedule_tz": "UTC"},
            # Not this member's standup, so its Saturday does not count.
            {"active": True, "participants": ["U2"], "schedule_days": "sat", "schedule_tz": "UTC"},
        ]

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a):
                pass

            def fetchall(self):
                return rows

        class Conn:
            def cursor(self, *a, **k):
                return Cursor()

        from contextlib import contextmanager

        @contextmanager
        def fake_conn():
            yield Conn()

        with (
            patch.object(db, "db_conn", fake_conn),
            patch.object(db, "get_standup_schedules", return_value=schedules),
            patch.object(db, "list_holidays", return_value=[{"date": d(25), "name": "Founders day"}]),
            patch.object(db, "local_today", return_value=d(28)),
        ):
            assert db.get_standup_streak("T1", "U1") == 3
