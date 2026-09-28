"""The member profile: one validated write path, no birth year, and removal on leave.

Birthdays and start dates are personal data. The rules this file holds the
code to: day and month only, no year stored from any source, the Slack sync
never touches a profile, and a profile does not outlive its owner leaving the
workspace by more than 30 days.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
import src.core.db as real_db
import src.core.scheduler as scheduler
from src.core import profile
from src.core.api_schemas import MemberProfile


class FakeCursor:
    """Records every statement, answers fetchone/rowcount from a script."""

    def __init__(self, fetchone=None, rowcount=1):
        self.calls: list[tuple[str, tuple]] = []
        self._fetchone = list(fetchone or [])
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), tuple(params)))

    def fetchone(self):
        return self._fetchone.pop(0) if self._fetchone else None


@pytest.fixture
def cursor(monkeypatch):
    cur = FakeCursor()
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(real_db, "db_conn", fake_conn)
    return cur


# ── Validation ──────────────────────────────────────────────────────────────


class TestValidation:
    def load(self, **fields):
        return real_db.validate_member_profile(fields)

    def test_29_february_is_a_birthday(self):
        assert self.load(birth_month=2, birth_day=29) == {"birth_month": 2, "birth_day": 29}

    def test_30_february_is_not(self):
        with pytest.raises(real_db.ProfileValidationError) as exc:
            self.load(birth_month=2, birth_day=30)
        assert "birth_day" in exc.value.messages

    def test_31_april_is_not(self):
        with pytest.raises(real_db.ProfileValidationError):
            self.load(birth_month=4, birth_day=31)

    def test_half_a_birthday_is_refused(self):
        with pytest.raises(real_db.ProfileValidationError):
            self.load(birth_month=3, birth_day=None)
        with pytest.raises(real_db.ProfileValidationError):
            self.load(birth_month=3)

    def test_both_cleared_is_fine(self):
        assert self.load(birth_month=None, birth_day=None) == {"birth_month": None, "birth_day": None}

    @pytest.mark.parametrize("month", [0, 13])
    def test_month_out_of_range(self, month):
        with pytest.raises(real_db.ProfileValidationError):
            self.load(birth_month=month, birth_day=1)

    def test_a_birth_year_is_dropped_never_stored(self):
        clean = self.load(birth_month=7, birth_day=4, birth_year=1990, birthday="1990-07-04")
        assert clean == {"birth_month": 7, "birth_day": 4}
        assert 1990 not in clean.values()

    @pytest.mark.parametrize("field,limit", [("role", 80), ("location", 80), ("ask_me_about", 200)])
    def test_text_caps(self, field, limit):
        assert self.load(**{field: "x" * limit})[field] == "x" * limit
        with pytest.raises(real_db.ProfileValidationError) as exc:
            self.load(**{field: "x" * (limit + 1)})
        assert field in exc.value.messages

    def test_blank_text_clears_rather_than_storing_empty(self):
        assert self.load(role="   ", location="  Berlin ") == {"role": None, "location": "Berlin"}

    def test_start_date_keeps_its_year(self):
        assert self.load(start_date="2019-06-03") == {"start_date": date(2019, 6, 3)}

    def test_start_date_a_few_months_ahead_is_allowed(self):
        ahead = date.today() + timedelta(days=90)
        assert self.load(start_date=ahead.isoformat())["start_date"] == ahead

    @pytest.mark.parametrize("value", ["1850-01-01", (date.today() + timedelta(days=800)).isoformat(), "yesterday"])
    def test_implausible_start_dates(self, value):
        with pytest.raises(real_db.ProfileValidationError):
            self.load(start_date=value)

    def test_the_schema_the_dashboard_uses_is_the_same_one(self):
        # One validation for every entry point: the route and the db load the
        # same class, so neither can accept what the other refuses.
        with pytest.raises(Exception):
            MemberProfile().load({"birth_month": 2, "birth_day": 30})


# ── The single write path ───────────────────────────────────────────────────


class TestUpsert:
    def test_writes_only_the_fields_given_and_records_who(self, cursor):
        cursor._fetchone = [{"user_id": "U1", "role": "Eng"}]
        real_db.upsert_member_profile("T1", "U1", {"role": "Eng"}, updated_by="U1")
        sql, params = cursor.calls[0]
        assert sql.startswith("INSERT INTO member_profiles (team_id, user_id, role, updated_by, updated_at)")
        assert "role = EXCLUDED.role" in sql
        assert "location" not in sql and "birth_month" not in sql
        assert params == ("T1", "U1", "Eng", "U1")

    def test_updated_by_is_required(self, cursor):
        with pytest.raises(real_db.ProfileValidationError):
            real_db.upsert_member_profile("T1", "U1", {"role": "Eng"}, updated_by="")
        assert cursor.calls == []

    def test_invalid_input_never_reaches_the_database(self, cursor):
        with pytest.raises(real_db.ProfileValidationError):
            real_db.upsert_member_profile("T1", "U1", {"birth_month": 2, "birth_day": 30}, updated_by="U1")
        assert cursor.calls == []

    def test_no_year_reaches_the_database(self, cursor):
        cursor._fetchone = [{}]
        real_db.upsert_member_profile(
            "T1", "U1", {"birth_month": 7, "birth_day": 4, "birth_year": 1990}, updated_by="U_ADMIN"
        )
        sql, params = cursor.calls[0]
        assert "year" not in sql
        assert 1990 not in params and "1990" not in str(params)


# ── Leaving, returning and the purge ────────────────────────────────────────


class TestLeaving:
    def test_deactivating_stamps_left_at_in_the_same_transaction(self, cursor):
        cursor.rowcount = 2
        assert real_db.set_members_active("T1", ["U1", "U2"], False) == 2
        members_sql, profile_sql = cursor.calls
        assert members_sql[0].startswith("UPDATE members SET active")
        assert "SET left_at = NOW()" in profile_sql[0] and "left_at IS NULL" in profile_sql[0]
        assert profile_sql[1] == ("T1", ["U1", "U2"])

    def test_reactivating_clears_left_at(self, cursor):
        real_db.set_members_active("T1", ["U1"], True)
        _, profile_sql = cursor.calls
        assert "SET left_at = NULL" in profile_sql[0]

    def test_nobody_to_change_touches_nothing(self, cursor):
        assert real_db.set_members_active("T1", [], False) == 0
        assert cursor.calls == []

    def test_profiles_without_a_members_row_follow_the_directory(self, cursor):
        real_db.sync_profile_departures("T1", {"U2", "U1"})
        left, back = cursor.calls
        assert "SET left_at = NOW()" in left[0] and "NOT (user_id = ANY(%s))" in left[0]
        assert "SET left_at = NULL" in back[0]
        assert left[1] == ("T1", ["U1", "U2"])

    def test_an_empty_directory_marks_nobody_as_left(self, cursor):
        # A failed users.list must never read as "everyone left".
        assert real_db.sync_profile_departures("T1", []) == (0, 0)
        assert cursor.calls == []


class TestPurge:
    def test_deletes_only_after_thirty_days_and_only_the_inactive(self, cursor):
        cursor._fetchone = [(True,)]
        cursor.rowcount = 3
        assert real_db.purge_departed_profiles() == 3
        lock, clear, delete = cursor.calls
        assert "pg_try_advisory_xact_lock" in lock[0]
        assert "SET left_at = NULL" in clear[0] and "m.active = TRUE" in clear[0]
        assert delete[0].startswith("DELETE FROM member_profiles")
        assert "make_interval(days => %s)" in delete[0]
        assert "NOT EXISTS" in delete[0] and "m.active = TRUE" in delete[0]
        assert delete[1] == (30,)

    def test_another_pod_holding_the_lock_means_this_one_does_nothing(self, cursor):
        cursor._fetchone = [(False,)]
        assert real_db.purge_departed_profiles() == 0
        assert len(cursor.calls) == 1

    def test_the_scheduler_runs_it_nightly(self):
        with patch.dict(sys.modules, {"src.core.db": MagicMock()}):
            built = scheduler.build_scheduler([])
        job = built.get_job("profile_purge")
        assert job is not None
        assert ":" not in job.id, "a namespaced id would be removed by module job reconciliation"

    def test_a_failing_purge_does_not_raise_into_the_scheduler(self, monkeypatch):
        fake = MagicMock()
        fake.purge_departed_profiles.side_effect = RuntimeError("db down")
        monkeypatch.setitem(sys.modules, "src.core.db", fake)
        monkeypatch.setattr(importlib.import_module("src.core"), "db", fake)
        scheduler._purge_departed_profiles()


# ── The Slack sync never writes a profile ───────────────────────────────────


def _user(uid):
    return {"id": uid, "name": uid.lower(), "real_name": uid, "deleted": False, "is_bot": False, "tz": "UTC"}


class TestSyncNeverOverwritesAProfile:
    @pytest.fixture
    def db(self, monkeypatch):
        fake = MagicMock()
        fake.get_all_installations.return_value = [{"team_id": "T1", "bot_token": "xoxb-test"}]
        fake.get_all_active_schedules.return_value = []
        fake.get_all_members.return_value = [
            {"user_id": "U1", "active": True, "real_name": "Stays"},
            {"user_id": "U2", "active": True, "real_name": "Leaves"},
            {"user_id": "U3", "active": False, "real_name": "Returns"},
        ]
        fake.set_members_active.return_value = 1
        fake.remove_participants_everywhere.return_value = 0
        fake.sync_profile_departures.return_value = (0, 0)
        monkeypatch.setitem(sys.modules, "src.core.db", fake)
        monkeypatch.setattr(importlib.import_module("src.core"), "db", fake)
        return fake

    def _run(self, directory):
        with (
            patch.object(scheduler, "_rate_limited_client", return_value=MagicMock()),
            patch.object(scheduler, "fetch_workspace_directory", return_value=(directory, None)),
            patch.object(scheduler, "fetch_human_users", return_value={}),
            patch.object(scheduler.time, "sleep"),
        ):
            scheduler.sync_members_from_slack()

    def test_only_left_at_moves(self, db):
        self._run({"U1": _user("U1"), "U3": _user("U3")})
        db.upsert_member_profile.assert_not_called()
        db.set_members_active.assert_any_call("T1", ["U2"], False)
        db.set_members_active.assert_any_call("T1", ["U3"], True)
        db.sync_profile_departures.assert_called_once_with("T1", {"U1", "U3"})

    def test_a_failed_directory_marks_nobody(self, db):
        with (
            patch.object(scheduler, "_rate_limited_client", return_value=MagicMock()),
            patch.object(scheduler, "fetch_workspace_directory", return_value=(None, "ratelimited")),
            patch.object(scheduler.time, "sleep"),
        ):
            scheduler.sync_members_from_slack()
        db.sync_profile_departures.assert_not_called()
        db.set_members_active.assert_not_called()

    def test_a_profile_failure_does_not_stop_the_member_sync(self, db):
        db.sync_profile_departures.side_effect = RuntimeError("no table yet")
        self._run({"U1": _user("U1"), "U3": _user("U3")})
        db.remove_participants_everywhere.assert_called()


# ── CSV import ──────────────────────────────────────────────────────────────


class TestBirthdayParsing:
    def test_month_day(self):
        assert profile.parse_birthday("03-14") == (3, 14)

    def test_a_full_date_loses_its_year(self):
        assert profile.parse_birthday("1990-07-04") == (7, 4)

    def test_29_february_both_ways(self):
        assert profile.parse_birthday("02-29") == (2, 29)
        assert profile.parse_birthday("1992-02-29") == (2, 29)

    @pytest.mark.parametrize("value", ["1991-02-29", "02-30", "13-01", "14/03", "March 14", ""])
    def test_refused(self, value):
        with pytest.raises(ValueError):
            profile.parse_birthday(value)


class TestReadImport:
    def test_reads_the_documented_format(self):
        rows = profile.read_import("email,birthday,start_date\nPriya@Example.test,1990-03-14,2023-03-01\n")
        assert rows == [
            {
                "line": 2,
                "email": "priya@example.test",
                "birth_month": 3,
                "birth_day": 14,
                "start_date": date(2023, 3, 1),
                "error": None,
            }
        ]

    def test_no_year_survives_parsing(self):
        rows = profile.read_import("email,birthday\na@x.test,1987-11-05\n")
        assert "1987" not in repr(rows)

    def test_columns_in_any_order_with_extras_and_a_bom(self):
        rows = profile.read_import("﻿Start_Date,Name,Email\n2020-01-06,Tom,t@x.test\n")
        assert rows[0]["start_date"] == date(2020, 1, 6) and rows[0]["birth_month"] is None

    def test_row_errors_are_per_row(self):
        rows = profile.read_import(
            "email,birthday,start_date\n"
            "a@x.test,02-30,\n"
            "not-an-email,03-01,\n"
            "b@x.test,,\n"
            "c@x.test,04-01,\n"
            "C@x.test,05-01,\n"
        )
        errors = [r["error"] for r in rows]
        assert "not a real date" in errors[0]
        assert "email" in errors[1]
        assert "Neither" in errors[2]
        assert errors[3] is None
        assert "line 6" not in errors[4] and "line 5" in errors[4]

    @pytest.mark.parametrize("text", ["", "name,birthday\nx,03-01\n", "email\na@x.test\n"])
    def test_unreadable_files(self, text):
        with pytest.raises(profile.ImportFormatError):
            profile.read_import(text)

    def test_row_limit(self, monkeypatch):
        monkeypatch.setattr(profile, "MAX_IMPORT_ROWS", 2)
        with pytest.raises(profile.ImportFormatError):
            profile.read_import("email,birthday\na@x.test,01-01\nb@x.test,01-01\nc@x.test,01-01\n")


class TestPlanImport:
    MEMBERS = [
        {"user_id": "U1", "email": "one@x.test"},
        {"user_id": "U2", "email": "two@x.test"},
        {"user_id": "U3", "email": "three@x.test"},
        {"user_id": "U4", "email": "four@x.test"},
    ]

    def rows(self):
        return profile.read_import(
            "email,birthday,start_date\n"
            "one@x.test,03-14,\n"
            "two@x.test,1990-07-04,\n"
            "three@x.test,,2020-01-06\n"
            "four@x.test,12-01,\n"
            "nobody@x.test,01-01,\n"
        )

    def existing(self):
        return {
            # set by the member themselves
            "U2": {"user_id": "U2", "birth_month": 8, "birth_day": 1, "updated_by": "U2"},
            # set by an admin earlier
            "U3": {"user_id": "U3", "start_date": date(2019, 1, 1), "updated_by": "U_ADMIN"},
            # already holds exactly this
            "U4": {"user_id": "U4", "birth_month": 12, "birth_day": 1, "updated_by": "U_ADMIN"},
        }

    def statuses(self, overwrite):
        return {
            r["email"]: r["status"] for r in profile.plan_import(self.rows(), self.MEMBERS, self.existing(), overwrite)
        }

    def test_what_happens_to_each_row(self):
        assert self.statuses(overwrite=False) == {
            "one@x.test": "ready",
            "two@x.test": "kept",
            "three@x.test": "ready",
            "four@x.test": "unchanged",
            "nobody@x.test": "unmatched",
        }

    def test_overwrite_replaces_what_the_member_set(self):
        assert self.statuses(overwrite=True)["two@x.test"] == "ready"

    def test_an_import_writes_only_the_dates_it_carries(self):
        planned = profile.plan_import(self.rows(), self.MEMBERS, {}, False)
        assert profile.import_fields(planned[0]) == {"birth_month": 3, "birth_day": 14}
        assert profile.import_fields(planned[2]) == {"start_date": "2020-01-06"}

    def test_the_summary_counts(self):
        planned = profile.plan_import(self.rows(), self.MEMBERS, self.existing(), False)
        summary = profile.summarise_import(planned, preview=True, overwrite=False, written=0)
        assert (summary["ready"], summary["kept"], summary["unchanged"], summary["unmatched"]) == (2, 1, 1, 1)
        assert summary["rows_read"] == 5 and summary["written"] == 0
