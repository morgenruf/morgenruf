"""The core workspace calendar: working days, holidays, and the day-finding helpers.

Celebrations moves a day off to the working day before it; Onboarding
buddies will move to the one after. Both read this, so its rules are tested
on their own.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
import src.core.db as real_db
from src.core import workspace_calendar as wc
from src.core.workspace_calendar import Calendar, CalendarError

MON_FRI = Calendar()
# 2026: 24 December is a Thursday, 25 a Friday, 26 and 27 the weekend.
CHRISTMAS = Calendar(holidays={date(2026, 12, 24): "Christmas Eve", date(2026, 12, 25): "Christmas Day"})
SUN_THU = Calendar(working_days=wc.parse_working_days("sun,mon,tue,wed,thu"))


class TestWorkingDays:
    def test_monday_to_friday_is_the_default(self):
        assert wc.parse_working_days(wc.DEFAULT_WORKING_DAYS) == frozenset(range(5))
        assert MON_FRI.is_working_day(date(2026, 9, 25))  # Friday
        assert not MON_FRI.is_working_day(date(2026, 9, 26))  # Saturday

    def test_a_listed_holiday_is_not_a_working_day(self):
        assert not CHRISTMAS.is_working_day(date(2026, 12, 25))
        assert CHRISTMAS.is_working_day(date(2026, 12, 23))

    def test_sunday_to_thursday(self):
        assert SUN_THU.is_working_day(date(2026, 9, 27))  # Sunday
        assert not SUN_THU.is_working_day(date(2026, 9, 25))  # Friday
        assert not SUN_THU.is_working_day(date(2026, 9, 26))  # Saturday

    def test_parsing_is_strict(self):
        with pytest.raises(CalendarError):
            wc.parse_working_days("mon,funday")
        with pytest.raises(CalendarError):
            wc.parse_working_days("")
        with pytest.raises(CalendarError):
            wc.parse_working_days([])

    def test_lists_and_full_names_are_accepted(self):
        assert wc.parse_working_days(["Monday", "tue"]) == frozenset({0, 1})

    def test_stored_in_week_order(self):
        assert wc.format_working_days({4, 0, 6}) == "mon,fri,sun"

    def test_a_bad_stored_value_falls_back_to_the_default(self):
        assert wc.working_day_keys("nonsense") == ["mon", "tue", "wed", "thu", "fri"]
        assert wc.from_rows("nonsense", []).working_days == frozenset(range(5))


class TestFindingDays:
    def test_previous_working_day_skips_the_weekend(self):
        assert MON_FRI.previous_working_day(date(2026, 9, 28)) == date(2026, 9, 25)

    def test_next_working_day_skips_the_weekend(self):
        assert MON_FRI.next_working_day(date(2026, 9, 25)) == date(2026, 9, 28)

    def test_both_skip_holidays(self):
        assert CHRISTMAS.previous_working_day(date(2026, 12, 28)) == date(2026, 12, 23)
        assert CHRISTMAS.next_working_day(date(2026, 12, 23)) == date(2026, 12, 28)

    def test_days_off_after_friday_are_the_weekend(self):
        assert MON_FRI.days_off_after(date(2026, 9, 25)) == [date(2026, 9, 26), date(2026, 9, 27)]

    def test_no_days_off_mid_week(self):
        assert MON_FRI.days_off_after(date(2026, 9, 23)) == []

    def test_a_calendar_with_no_working_day_finds_none(self):
        cal = Calendar(working_days=frozenset())
        assert cal.previous_working_day(date(2026, 9, 25)) is None
        assert cal.next_working_day(date(2026, 9, 25)) is None
        assert cal.days_off_after(date(2026, 9, 25)) == []

    def test_database_backed_helpers_read_the_workspace(self, monkeypatch):
        monkeypatch.setattr(real_db, "get_working_days", lambda team: "sun,mon,tue,wed,thu")
        monkeypatch.setattr(real_db, "list_holidays", lambda team: [{"date": date(2026, 9, 29), "name": "Day off"}])
        assert wc.is_working_day("T1", date(2026, 9, 27))
        assert not wc.is_working_day("T1", date(2026, 9, 29))
        assert wc.previous_working_day("T1", date(2026, 9, 30)) == date(2026, 9, 28)
        assert wc.next_working_day("T1", date(2026, 9, 28)) == date(2026, 9, 30)


class TestHolidayCsv:
    TODAY = date(2026, 9, 27)

    def test_rows_with_and_without_a_header(self):
        rows = wc.read_holiday_csv("date,name\n2026-12-25,Christmas Day\n2027-01-01, New Year \n", self.TODAY)
        assert [(r["date"], r["name"], r["status"]) for r in rows] == [
            (date(2026, 12, 25), "Christmas Day", "ready"),
            (date(2027, 1, 1), "New Year", "ready"),
        ]
        assert wc.read_holiday_csv("2026-12-25,Christmas\n", self.TODAY)[0]["status"] == "ready"

    def test_bad_rows_are_marked_not_dropped(self):
        rows = wc.read_holiday_csv(
            "2026-02-30,Nope\n25.12.2026,Wrong format\n2026-12-25,\n2026-12-26,Boxing Day\n2026-12-26,Again\n",
            self.TODAY,
        )
        assert [r["status"] for r in rows] == ["invalid", "invalid", "invalid", "ready", "invalid"]
        assert "already in the file" in rows[-1]["error"]

    def test_more_than_a_year_ago_is_refused(self):
        old = (self.TODAY - timedelta(days=400)).isoformat()
        assert wc.read_holiday_csv(f"{old},Old\n", self.TODAY)[0]["status"] == "invalid"

    def test_an_empty_file_is_an_error(self):
        with pytest.raises(CalendarError):
            wc.read_holiday_csv("date,name\n", self.TODAY)

    def test_names_are_capped(self):
        with pytest.raises(CalendarError):
            wc.clean_holiday_name("x" * 81)


@pytest.fixture
def cursor(monkeypatch):
    calls = []
    cur = MagicMock()
    cur.__enter__.return_value = cur
    cur.execute.side_effect = lambda sql, params=(): calls.append((" ".join(sql.split()), tuple(params)))
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    cur.rowcount = 2
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(real_db, "db_conn", fake_conn)
    cur.calls = calls
    return cur


class TestStorage:
    def test_working_days_default_when_unset(self, cursor):
        assert real_db.get_working_days("T1") == "mon,tue,wed,thu,fri"

    def test_setting_working_days_touches_only_that_column(self, cursor):
        real_db.set_working_days("T1", "sun,mon,tue,wed,thu")
        sql, params = cursor.calls[0]
        assert "ON CONFLICT (team_id) DO UPDATE SET working_days = EXCLUDED.working_days" in sql
        assert "schedule" not in sql
        assert params == ("T1", "sun,mon,tue,wed,thu")

    def test_adding_a_holiday_renames_an_existing_date(self, cursor):
        assert real_db.upsert_holidays("T1", [{"date": date(2026, 12, 25), "name": "Christmas"}]) == 1
        assert "ON CONFLICT (team_id, date) DO UPDATE SET name" in cursor.calls[0][0]

    def test_purge_deletes_only_old_holidays(self, cursor):
        assert real_db.purge_old_holidays(365) == 2
        sql, params = cursor.calls[0]
        assert sql == "DELETE FROM workspace_holidays WHERE date < CURRENT_DATE - %s"
        assert params == (365,)

    def test_the_purge_runs_nightly(self):
        import src.core.scheduler as scheduler

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.core.db.get_all_active_schedules", lambda: [])
            built = scheduler.build_scheduler([])
        assert built.get_job("holiday_purge") is not None


class TestMigration:
    def test_additive_and_cascading(self):
        from pathlib import Path

        sql = (Path(real_db.__file__).parent / "migrations" / "053_workspace_calendar.sql").read_text()
        assert "ADD COLUMN IF NOT EXISTS working_days" in sql
        assert "DEFAULT 'mon,tue,wed,thu,fri'" in sql
        assert "REFERENCES installations(team_id) ON DELETE CASCADE" in sql
        assert "PRIMARY KEY (team_id, date)" in sql
        assert "DROP" not in sql.upper()
