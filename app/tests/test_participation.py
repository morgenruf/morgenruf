"""Tests for the participation / completion-rate model (issue #74).

Every expected value in this file is worked out by hand in the docstring or a
comment above the assertion, so the test pins the arithmetic a human did rather
than whatever the implementation happens to produce.

Reference clock for the whole file: Friday 2026-03-13 12:00 UTC.
A 7 day window ending that day covers:

    Sat 03-07, Sun 03-08, Mon 03-09, Tue 03-10, Wed 03-11, Thu 03-12, Fri 03-13

so a mon-fri schedule has 5 occurrence days in it and a mon/wed/fri schedule
has 3 (03-09, 03-11, 03-13).
"""

from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Stub psycopg2 before importing the real db module, and discard any MagicMock
# another test module left under "db", so we import the real thing.
_pool_mod_mock = MagicMock()
_pool_mod_mock.ThreadedConnectionPool.return_value = None  # skip pool init at import time
sys.modules["psycopg2"] = MagicMock()
sys.modules["psycopg2.extras"] = MagicMock()
sys.modules["psycopg2.pool"] = _pool_mod_mock
sys.modules.pop("db", None)

import db as _db_real  # noqa: E402

importlib.reload(_db_real)  # re-run the module body now the psycopg2 stubs are in place
db = _db_real


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 3, 13, 12, 0, tzinfo=UTC)  # Friday

MON = "2026-03-09"
TUE = "2026-03-10"
WED = "2026-03-11"
THU = "2026-03-12"
FRI = "2026-03-13"
WORKING_DAYS = [MON, TUE, WED, THU, FRI]


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def _schedule(sched_id, name, participants, days="mon,tue,wed,thu,fri", tz="UTC", time_="09:00", active=True):
    return {
        "id": sched_id,
        "name": name,
        "schedule_time": time_,
        "schedule_tz": tz,
        "schedule_days": days,
        "participants": list(participants),
        "active": active,
    }


def _member(user_id, real_name=None, active=True, on_vacation=False):
    return {
        "user_id": user_id,
        "real_name": real_name or user_id,
        "active": active,
        "on_vacation": on_vacation,
    }


def _submission(user_id, day, has_blockers=False, hour=9):
    d = dt.date.fromisoformat(day)
    return {
        "user_id": user_id,
        "standup_date": d,
        "has_blockers": has_blockers,
        "submitted_at": dt.datetime(d.year, d.month, d.day, hour, tzinfo=UTC),
    }


def _by_user(result):
    return {row["user_id"]: row for row in result["members"]}


def _by_schedule(result):
    return {row["schedule_id"]: row for row in result["schedules"]}


# ---------------------------------------------------------------------------
# The main worked example
#
# Schedules (all UTC):
#   S1 "Morning" 09:00 mon-fri      participants U1 U2 U3 U5
#   S2 "Evening" 17:00 mon-fri      participants U1
#   S3 "Tri"     10:00 mon,wed,fri  participants U4
#
# Members: U1..U6 active. U5 is on vacation. U6 is in no schedule.
#
# Denominator, by hand:
#   S1: 5 days x 3 countable participants (U5 is on leave)  = 15
#   S2: 5 days x 1                                          =  5
#   S3: 3 days x 1                                          =  3
#                                                     total = 23
#
# Submissions:
#   U1: 2 on Mon, 1 on Tue, 2 on Wed, 0 on Thu, 1 on Fri    =  6
#   U2: 1 on each working day                               =  5
#   U3: none                                                =  0
#   U4: Mon and Fri                                         =  2
#   U6: 3 ad-hoc standups (not enrolled anywhere)           =  3
#                                                     total = 16
#
# Numerator, matched per (member, day) because a standup row carries no
# schedule id: min(submissions that day, occurrences that day).
#   U1: min(2,2)+min(1,2)+min(2,2)+min(0,2)+min(1,2) = 2+1+2+0+1 = 6 of 10
#   U2: 5 of 5
#   U3: 0 of 5
#   U4: 2 of 3
#                                                     total = 13 of 23
#   13/23 = 56.52% -> 57%
# ---------------------------------------------------------------------------


def _workspace():
    schedules = [
        _schedule(1, "Morning", ["U1", "U2", "U3", "U5"], time_="09:00"),
        _schedule(2, "Evening", ["U1"], time_="17:00"),
        _schedule(3, "Tri", ["U4"], days="mon,wed,fri", time_="10:00"),
    ]
    members = [
        _member("U1", "Ada"),
        _member("U2", "Bo"),
        _member("U3", "Cy"),
        _member("U4", "Dee"),
        _member("U5", "Eve", on_vacation=True),
        _member("U6", "Fin"),
    ]
    submissions = [
        _submission("U1", MON, hour=9),
        _submission("U1", MON, hour=17),
        _submission("U1", TUE, hour=9),
        _submission("U1", WED, hour=9),
        _submission("U1", WED, hour=17),
        _submission("U1", FRI, hour=9),
        *[_submission("U2", d) for d in WORKING_DAYS],
        _submission("U4", MON),
        _submission("U4", FRI, has_blockers=True),
        _submission("U6", MON),
        _submission("U6", WED),
        _submission("U6", FRI),
    ]
    return schedules, members, submissions


def _result(days=7):
    schedules, members, submissions = _workspace()
    return db.compute_participation(schedules, members, submissions, days=days, now=NOW)


# ---------------------------------------------------------------------------
# schedule_days parsing
# ---------------------------------------------------------------------------


class TestParseScheduleDays:
    def test_comma_list(self):
        assert db.parse_schedule_days("mon,wed,fri") == {0, 2, 4}

    def test_range(self):
        assert db.parse_schedule_days("mon-fri") == {0, 1, 2, 3, 4}

    def test_wrapping_range(self):
        assert db.parse_schedule_days("fri-mon") == {4, 5, 6, 0}

    def test_star_is_every_day(self):
        assert db.parse_schedule_days("*") == {0, 1, 2, 3, 4, 5, 6}

    def test_numeric_tokens(self):
        assert db.parse_schedule_days("0,6") == {0, 6}

    def test_blank_falls_back_to_the_working_week(self):
        assert db.parse_schedule_days("") == {0, 1, 2, 3, 4}
        assert db.parse_schedule_days(None) == {0, 1, 2, 3, 4}


# ---------------------------------------------------------------------------
# The denominator
# ---------------------------------------------------------------------------


class TestExpectedOccurrences:
    def test_person_in_two_schedules_is_expected_twice_a_day(self):
        """U1 is in Morning and Evening, both mon-fri: 2 x 5 = 10 expected, not 5."""
        rows = _by_user(_result())
        assert rows["U1"]["expected"] == 10
        assert rows["U1"]["completed"] == 6
        assert rows["U1"]["completion_rate"] == 60  # 6/10

    def test_three_day_a_week_schedule_expects_three_days_not_five(self):
        """S3 runs mon/wed/fri, so U4 is expected 3 times, and 2 of 3 is 67 percent."""
        result = _result()
        assert _by_schedule(result)[3]["occurrence_days"] == 3
        assert _by_schedule(result)[3]["expected"] == 3
        rows = _by_user(result)
        assert rows["U4"]["expected"] == 3
        assert rows["U4"]["completed"] == 2
        assert rows["U4"]["completion_rate"] == 67  # 2/3 = 66.67 rounds to 67

    def test_vacation_removes_the_member_from_the_denominator(self):
        """U5 is a Morning participant but on leave, so Morning expects 3 people, not 4."""
        result = _result()
        assert _by_schedule(result)[1]["participants"] == 3
        assert _by_schedule(result)[1]["expected"] == 15  # 5 days x 3 people
        rows = _by_user(result)
        assert rows["U5"]["expected"] == 0
        assert rows["U5"]["on_vacation"] is True
        assert rows["U5"]["enrolled"] is True  # still listed on the schedule

    def test_enrolled_member_who_never_responds_counts_against_the_rate(self):
        rows = _by_user(_result())
        assert rows["U3"]["enrolled"] is True
        assert rows["U3"]["expected"] == 5
        assert rows["U3"]["completed"] == 0
        assert rows["U3"]["completion_rate"] == 0

    def test_unenrolled_member_is_flagged_not_dropped(self):
        """U6 is in no schedule. They stay in the payload with enrolled False."""
        rows = _by_user(_result())
        assert "U6" in rows
        assert rows["U6"]["enrolled"] is False
        assert rows["U6"]["expected"] == 0
        assert rows["U6"]["responses"] == 3  # ad-hoc standups are still reported
        assert rows["U6"]["completion_rate"] == 0

    def test_inactive_member_is_excluded(self):
        schedules, members, submissions = _workspace()
        members.append(_member("U7", "Gus", active=False))
        schedules[0]["participants"].append("U7")
        result = db.compute_participation(schedules, members, submissions, days=7, now=NOW)
        assert "U7" not in _by_user(result)
        assert _by_schedule(result)[1]["expected"] == 15  # unchanged


# ---------------------------------------------------------------------------
# Workspace and per-schedule totals
# ---------------------------------------------------------------------------


class TestWorkspaceTotals:
    def test_totals_match_the_hand_computed_figures(self):
        result = _result()
        assert result["expected"] == 23
        assert result["completed"] == 13
        assert result["missed"] == 10
        assert result["completion_rate"] == 57  # 13/23 = 56.52
        assert result["responses"] == 16  # raw submissions in the window

    def test_enrolment_counts_are_exposed(self):
        result = _result()
        assert result["total_members"] == 6
        assert result["enrolled_members"] == 5  # U1..U5, U6 is in no schedule
        assert result["unenrolled_members"] == 1
        assert result["on_vacation_members"] == 1
        assert result["responding_members"] == 4  # U1 U2 U4 U6

    def test_per_schedule_breakdown(self):
        """Morning 9/15, Evening 2/5, Tri 2/3.

        U1's submissions are attributed to their schedules in schedule_time
        order, so the single Tuesday and Friday standups land on Morning
        (09:00) and Evening (17:00) is the one recorded as missed.
        """
        rows = _by_schedule(_result())
        assert (rows[1]["expected"], rows[1]["completed"], rows[1]["completion_rate"]) == (15, 9, 60)
        assert (rows[2]["expected"], rows[2]["completed"], rows[2]["completion_rate"]) == (5, 2, 40)
        assert (rows[3]["expected"], rows[3]["completed"], rows[3]["completion_rate"]) == (3, 2, 67)

    def test_schedule_totals_sum_to_the_workspace_totals(self):
        result = _result()
        assert sum(s["expected"] for s in result["schedules"]) == result["expected"]
        assert sum(s["completed"] for s in result["schedules"]) == result["completed"]

    def test_paused_schedule_is_ignored(self):
        schedules, members, submissions = _workspace()
        schedules.append(_schedule(4, "Paused", ["U1", "U2", "U3"], active=False))
        result = db.compute_participation(schedules, members, submissions, days=7, now=NOW)
        assert result["expected"] == 23
        assert 4 not in _by_schedule(result)


class TestEmptyWorkspace:
    def test_no_schedules_no_members_no_divide_by_zero(self):
        result = db.compute_participation([], [], [], days=7, now=NOW)
        assert result["expected"] == 0
        assert result["completed"] == 0
        assert result["completion_rate"] == 0
        assert result["members"] == []
        assert result["schedules"] == []
        assert result["enrolled_members"] == 0

    def test_members_but_no_schedules(self):
        result = db.compute_participation([], [_member("U1"), _member("U2")], [], days=7, now=NOW)
        assert result["completion_rate"] == 0
        assert result["total_members"] == 2
        assert result["enrolled_members"] == 0
        assert all(r["enrolled"] is False for r in result["members"])

    def test_none_inputs_are_tolerated(self):
        result = db.compute_participation(None, None, None, days=7, now=NOW)
        assert result["completion_rate"] == 0
        assert result["expected"] == 0


# ---------------------------------------------------------------------------
# Timezones
# ---------------------------------------------------------------------------


class TestScheduleTimezone:
    def test_window_is_expanded_in_the_schedules_own_timezone(self):
        """At 2026-03-15 23:00 UTC it is already Monday 2026-03-16 in Auckland.

        A monday-only UTC schedule has its single occurrence on 03-09 (the only
        Monday in the UTC window Mon 03-09 .. Sun 03-15). The same schedule in
        Pacific/Auckland has its occurrence on 03-16, because its window is
        Tue 03-10 .. Mon 03-16.
        """
        now = dt.datetime(2026, 3, 15, 23, 0, tzinfo=UTC)
        utc_sched = _schedule(1, "UTC Monday", ["U1"], days="mon", tz="UTC")
        akl_sched = _schedule(2, "Auckland Monday", ["U2"], days="mon", tz="Pacific/Auckland")
        members = [_member("U1"), _member("U2")]
        submissions = [_submission("U1", "2026-03-09"), _submission("U2", "2026-03-16")]

        result = db.compute_participation([utc_sched, akl_sched], members, submissions, days=7, now=now)
        rows = _by_schedule(result)
        assert rows[1]["occurrence_days"] == 1
        assert rows[2]["occurrence_days"] == 1
        assert result["expected"] == 2
        assert result["completed"] == 2  # each submission lands on its own schedule's local date

    def test_unknown_timezone_falls_back_to_utc_instead_of_raising(self):
        sched = _schedule(1, "Typo", ["U1"], tz="Not/AZone")
        result = db.compute_participation([sched], [_member("U1")], [], days=7, now=NOW)
        assert result["expected"] == 5  # mon-fri in the UTC window


# ---------------------------------------------------------------------------
# The headline number: 42 members, 24 of them enrolled
# ---------------------------------------------------------------------------


class TestOldVersusNewHeadlineNumber:
    """Documents how much the number on the dashboard moves.

    42 active members. 24 are in the Morning standup, and 12 of those 24 are
    also in the Evening standup. 18 members are in no schedule at all.
    Both standups run mon-fri, so the window holds 5 occurrence days.

      denominator = 24 x 5 + 12 x 5                      = 180
      submissions = 24 x 5 (morning) + 12 x 3 (evening)  = 156
      matched     = 12 people x (3 days x 2 + 2 days x 1) = 96
                  + 12 people x 5 days x 1                = 60
                                                    total = 156
      new rate    = 156/180                              = 86.67 -> 87%

    Old formula, on the same data:
      min(100, int(156 / 42 * 100 / 5)) = int(74.29) = 74%
    """

    @staticmethod
    def _build():
        everyone = [f"M{i:02d}" for i in range(1, 43)]
        morning = everyone[:24]
        evening = everyone[:12]
        schedules = [
            _schedule(1, "Morning", morning, time_="09:00"),
            _schedule(2, "Evening", evening, time_="17:00"),
        ]
        members = [_member(u) for u in everyone]
        submissions = []
        for day in WORKING_DAYS:
            submissions += [_submission(u, day, hour=9) for u in morning]
        for day in (MON, TUE, WED):
            submissions += [_submission(u, day, hour=17) for u in evening]
        return schedules, members, submissions

    def test_new_denominator_counts_enrolled_occurrences(self):
        schedules, members, submissions = self._build()
        result = db.compute_participation(schedules, members, submissions, days=7, now=NOW)
        assert result["total_members"] == 42
        assert result["enrolled_members"] == 24
        assert result["unenrolled_members"] == 18
        assert result["expected"] == 180
        assert result["responses"] == 156
        assert result["completed"] == 156
        assert result["completion_rate"] == 87

    def test_old_formula_on_the_same_data_returned_74(self):
        """The replaced expression, fed the same numbers, reports 74 percent."""
        schedules, members, submissions = self._build()
        result = db.compute_participation(schedules, members, submissions, days=7, now=NOW)
        responses_week = result["responses"]
        total_members = result["total_members"]
        old_rate = min(100, int(responses_week / max(total_members, 1) * 100 / 5))
        assert old_rate == 74
        assert result["completion_rate"] == 87
        # The old number was low because 18 people who are never asked sat in
        # the denominator; it was propped back up because one person's several
        # standups a day all counted in the numerator.


# ---------------------------------------------------------------------------
# Public helpers on top of the model
# ---------------------------------------------------------------------------


class TestPublicHelpers:
    def test_get_participation_overview_uses_the_fetched_rows(self):
        schedules, members, submissions = _workspace()
        with (
            patch.object(db, "_fetch_participation_inputs", return_value=(schedules, members, submissions)),
            patch.object(db, "_utc_now", return_value=NOW),
        ):
            result = db.get_participation_overview("T1", days=7)
        assert result["expected"] == 23
        assert result["completion_rate"] == 57

    def test_get_participation_stats_returns_member_rows_with_legacy_keys(self):
        schedules, members, submissions = _workspace()
        with (
            patch.object(db, "_fetch_participation_inputs", return_value=(schedules, members, submissions)),
            patch.object(db, "_utc_now", return_value=NOW),
        ):
            rows = db.get_participation_stats("T1", days=7)
        assert isinstance(rows, list)
        by_user = {r["user_id"]: r for r in rows}
        # Keys the mailer, the MCP server and the dashboard already read.
        for key in ("user_id", "real_name", "responses", "days_with_blockers", "last_standup"):
            assert key in by_user["U1"]
        assert by_user["U1"]["responses"] == 6
        assert by_user["U4"]["days_with_blockers"] == 1
        assert by_user["U2"]["last_standup"] == dt.datetime(2026, 3, 13, 9, tzinfo=UTC)

    def test_get_participation_stats_sorts_enrolled_members_first(self):
        schedules, members, submissions = _workspace()
        with (
            patch.object(db, "_fetch_participation_inputs", return_value=(schedules, members, submissions)),
            patch.object(db, "_utc_now", return_value=NOW),
        ):
            rows = db.get_participation_stats("T1", days=7)
        assert rows[-1]["user_id"] == "U6"  # the only unenrolled member

    def test_get_dashboard_stats_keeps_its_old_keys_and_adds_the_denominator(self):
        schedules, members, submissions = _workspace()
        with (
            patch.object(db, "_fetch_participation_inputs", return_value=(schedules, members, submissions)),
            patch.object(db, "_utc_now", return_value=NOW),
        ):
            stats = db.get_dashboard_stats("T1")
        assert stats["completion_rate"] == 57
        assert stats["total_responses"] == 16
        assert stats["responses_this_week"] == 16
        assert stats["active_members"] == 4
        assert stats["total_members"] == 6
        assert stats["enrolled_members"] == 5
        assert stats["expected_responses"] == 23
        assert stats["completed_responses"] == 13
        assert len(stats["schedules"]) == 3

    def test_fetch_runs_three_queries_regardless_of_schedule_count(self):
        """The expansion must not be a query per schedule per day per person."""
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = []
        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur
        pool = MagicMock()
        pool.getconn.return_value = conn
        with patch.object(db, "_pool", pool):
            db.get_participation_overview("T1", days=7)
        assert cur.execute.call_count == 3


class TestSubmissionsNameTheirSchedule:
    """Before migration 026 a submission could not be attributed to a schedule.

    A member in a morning and an evening standup who filed only one was
    credited to whichever fired first, regardless of which they answered.
    """

    @staticmethod
    def _two_standups():
        people = ["U1"]
        morning = {
            "id": 1,
            "team_id": "T",
            "name": "Morning",
            "schedule_days": "mon",
            "schedule_tz": "UTC",
            "schedule_time": "09:00",
            "participants": people,
            "active": True,
        }
        evening = {
            "id": 2,
            "team_id": "T",
            "name": "Evening",
            "schedule_days": "mon",
            "schedule_tz": "UTC",
            "schedule_time": "18:00",
            "participants": people,
            "active": True,
        }
        members = [{"user_id": "U1", "real_name": "Ada", "active": True, "on_vacation": False}]
        monday = dt.date(2026, 3, 9)
        now = dt.datetime(2026, 3, 9, 23, 0, tzinfo=dt.timezone.utc)
        return [morning, evening], members, monday, now

    def _rate_for(self, result, schedule_id):
        return next(s for s in result["schedules"] if s["schedule_id"] == schedule_id)["completed"]

    def test_the_evening_standup_gets_the_credit_when_named(self):
        schedules, members, monday, now = self._two_standups()
        subs = [{"user_id": "U1", "standup_date": monday, "schedule_id": 2}]
        r = db.compute_participation(schedules, members, subs, days=1, now=now)
        assert self._rate_for(r, 2) == 1
        assert self._rate_for(r, 1) == 0

    def test_the_morning_standup_gets_it_when_that_is_the_one_named(self):
        schedules, members, monday, now = self._two_standups()
        subs = [{"user_id": "U1", "standup_date": monday, "schedule_id": 1}]
        r = db.compute_participation(schedules, members, subs, days=1, now=now)
        assert self._rate_for(r, 1) == 1
        assert self._rate_for(r, 2) == 0

    def test_a_row_with_no_schedule_id_still_falls_back(self):
        """Rows written before 026 keep the old time-order behaviour."""
        schedules, members, monday, now = self._two_standups()
        subs = [{"user_id": "U1", "standup_date": monday}]
        r = db.compute_participation(schedules, members, subs, days=1, now=now)
        assert self._rate_for(r, 1) == 1
        assert self._rate_for(r, 2) == 0

    def test_named_and_unnamed_rows_together(self):
        schedules, members, monday, now = self._two_standups()
        subs = [
            {"user_id": "U1", "standup_date": monday, "schedule_id": 2},
            {"user_id": "U1", "standup_date": monday},
        ]
        r = db.compute_participation(schedules, members, subs, days=1, now=now)
        assert self._rate_for(r, 1) == 1
        assert self._rate_for(r, 2) == 1

    def test_per_schedule_still_sums_to_the_workspace_total(self):
        schedules, members, monday, now = self._two_standups()
        subs = [{"user_id": "U1", "standup_date": monday, "schedule_id": 2}]
        r = db.compute_participation(schedules, members, subs, days=1, now=now)
        assert sum(s["completed"] for s in r["schedules"]) == r["completed"]

    def test_a_schedule_id_that_did_not_ask_them_is_ignored(self):
        """A stale id must not credit a schedule the person is not in."""
        schedules, members, monday, now = self._two_standups()
        subs = [{"user_id": "U1", "standup_date": monday, "schedule_id": 999}]
        r = db.compute_participation(schedules, members, subs, days=1, now=now)
        assert sum(s["completed"] for s in r["schedules"]) == r["completed"] == 1


# ---------------------------------------------------------------------------
# schedule ids on member rows
# ---------------------------------------------------------------------------


class TestScheduleIdsOnMemberRows:
    """The dashboard's "filter by standup" control needs ids, not names.

    It had only `schedules`, a list of display names, and compared a numeric
    schedule id against it. The comparison never matched, so picking any
    standup emptied the analytics table.
    """

    def test_rows_carry_the_ids_of_the_schedules_they_belong_to(self):
        result = _result()
        rows = _by_user(result)
        assert rows["U1"]["schedule_ids"] == [1, 2]
        assert rows["U4"]["schedule_ids"] == [3]

    def test_ids_line_up_with_the_names_beside_them(self):
        result = _result()
        names = {s["schedule_id"]: s["name"] for s in result["schedules"]}
        for row in result["members"]:
            assert [names[i] for i in row["schedule_ids"]] == row["schedules"], row["user_id"]

    def test_ids_are_integers_so_they_can_be_compared_after_stringifying(self):
        for row in _result()["members"]:
            assert all(isinstance(i, int) for i in row["schedule_ids"]), row["user_id"]

    def test_a_member_in_no_schedule_has_an_empty_list(self):
        rows = _by_user(_result())
        assert rows["U6"]["schedule_ids"] == []
        assert rows["U6"]["enrolled"] is False

    def test_filtering_by_a_real_id_selects_the_right_people(self):
        """What the dashboard actually does with the field."""
        rows = _result()["members"]
        picked = [r["user_id"] for r in rows if 2 in r["schedule_ids"]]
        assert picked == ["U1"]
        picked_one = sorted(r["user_id"] for r in rows if 1 in r["schedule_ids"])
        assert picked_one == ["U1", "U2", "U3", "U5"]

    def test_every_id_resolves_to_a_returned_schedule(self):
        result = _result()
        known = {s["schedule_id"] for s in result["schedules"]}
        for row in result["members"]:
            assert set(row["schedule_ids"]) <= known, row["user_id"]

    def test_someone_on_leave_still_belongs_to_their_standup(self):
        """Membership is the participant list, not "was asked this week".

        Occurrences skip anyone on approved leave, so deriving membership from
        them dropped those people out of the per-standup filter entirely.
        """
        rows = _by_user(_result())
        assert rows["U5"]["on_vacation"] is True
        assert rows["U5"]["expected"] == 0
        assert rows["U5"]["schedule_ids"] == [1]

    def test_a_schedule_that_did_not_come_round_this_week_still_counts(self):
        """A weekly standup with no occurrence in the window keeps its roster."""
        schedules, members, submissions = _workspace()
        schedules.append(_schedule(9, "Weekly", ["U2"], days="sun", time_="08:00"))
        result = db.compute_participation(schedules, members, submissions, days=3, now=NOW)
        row = _by_user(result)["U2"]
        assert 9 in row["schedule_ids"]
        assert "Weekly" in row["schedules"]

    def test_an_inactive_member_named_on_a_schedule_is_not_listed_at_all(self):
        """Deactivated people are dropped from the rows, ids or not."""
        schedules, members, submissions = _workspace()
        members = [m for m in members if m["user_id"] != "U3"]
        members.append(_member("U3", "Cy", active=False))
        result = db.compute_participation(schedules, members, submissions, days=7, now=NOW)
        assert "U3" not in _by_user(result)


# ---------------------------------------------------------------------------
# per-day grid and per-schedule trend
# ---------------------------------------------------------------------------


class TestPerDayGrid:
    """The dashboard draws a member-by-day grid, so a week cannot be one ratio.

    A single "4/5" hides which days were missed and cannot show a pattern. The
    distinction that matters is between a day nobody was asked about and a day
    that was asked and missed; collapsing those is what makes a weekend look
    like a failure.
    """

    def test_the_window_is_oldest_first_and_the_right_length(self):
        result = _result(days=7)
        assert len(result["window_days"]) == 7
        assert result["window_days"] == sorted(result["window_days"])

    def test_every_member_has_one_entry_per_day_in_the_window(self):
        result = _result(days=7)
        for row in result["members"]:
            assert [d["date"] for d in row["days"]] == result["window_days"], row["user_id"]

    def test_a_day_nobody_was_asked_about_expects_nothing(self):
        """The weekend. Not the same as a missed standup."""
        row = _by_user(_result())["U1"]
        weekend = [d for d in row["days"] if d["date"] in ("2026-03-07", "2026-03-08")]
        assert weekend and all(d["expected"] == 0 and d["completed"] == 0 for d in weekend)

    def test_a_member_in_two_standups_expects_two_a_day(self):
        row = _by_user(_result())["U1"]
        weekday = [d for d in row["days"] if d["expected"]]
        assert weekday and all(d["expected"] == 2 for d in weekday)

    def test_completed_never_exceeds_expected(self):
        for row in _result()["members"]:
            for day in row["days"]:
                assert day["completed"] <= day["expected"], (row["user_id"], day)

    def test_the_grid_sums_to_the_row_totals(self):
        for row in _result()["members"]:
            assert sum(d["expected"] for d in row["days"]) == row["expected"], row["user_id"]
            assert sum(d["completed"] for d in row["days"]) == row["completed"], row["user_id"]

    def test_a_blocked_day_is_marked_on_the_day_not_just_the_member(self):
        schedules, members, submissions = _workspace()
        submissions.append(_submission("U2", WED, has_blockers=True))
        result = db.compute_participation(schedules, members, submissions, days=7, now=NOW)
        row = _by_user(result)["U2"]
        blocked = [d["date"] for d in row["days"] if d["blocked"]]
        assert blocked == [str(WED)]

    def test_a_member_on_leave_has_an_empty_grid_rather_than_missed_days(self):
        row = _by_user(_result())["U5"]
        assert row["on_vacation"] is True
        assert all(d["expected"] == 0 for d in row["days"])


class TestScheduleSeries:
    def test_each_schedule_gets_one_point_per_day(self):
        result = _result(days=7)
        for sched in result["schedules"]:
            assert len(sched["series"]) == 7, sched["name"]

    def test_a_day_the_schedule_did_not_run_is_none_not_zero(self):
        """A mon/wed/fri standup must not draw as four days of failure."""
        by_name = {s["name"]: s for s in _result()["schedules"]}
        tri = by_name["Tri"]
        assert tri["series"].count(None) >= 4
        assert any(v == 100 for v in tri["series"] if v is not None)

    def test_points_are_percentages_within_range(self):
        for sched in _result()["schedules"]:
            for value in sched["series"]:
                assert value is None or 0 <= value <= 100, sched["name"]

    def test_a_fully_answered_day_reads_as_one_hundred(self):
        by_name = {s["name"]: s for s in _result()["schedules"]}
        assert 100 in by_name["Evening"]["series"]
