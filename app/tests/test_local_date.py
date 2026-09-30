"""Every standup "today" is the schedule's local day, not the database's.

Postgres CURRENT_DATE is the session date, which is UTC. A Sydney team with a
09:00 standup (23:00 UTC the day before) and a 10:00 report (00:00 UTC) had
its answers filed under the previous UTC day, so the report found nothing and
was skipped every day, and the nudge reminded people who had already
answered. A US team reporting at 17:00 Pacific or later hit the same thing
from the other side. These tests freeze the clock at those moments.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import src.core.db as real_db
import src.core.scheduler as sched_mod
from src.core import timezones

from tests.support import patch_modules

# 2026-09-28 23:30 UTC: 09:30 on the 29th in Sydney (AEST, before DST starts
# on 4 October), 16:30 on the 28th in Los Angeles.
SYDNEY_MORNING = datetime(2026, 9, 28, 23, 30, tzinfo=timezone.utc)
# 2026-09-29 00:30 UTC: 17:30 on the 28th in Los Angeles, already the 29th in UTC.
LA_EVENING = datetime(2026, 9, 29, 0, 30, tzinfo=timezone.utc)


@pytest.fixture
def frozen(monkeypatch):
    def freeze(moment: datetime) -> None:
        monkeypatch.setattr(timezones, "_utc_now", lambda: moment)

    return freeze


# ── the helper ───────────────────────────────────────────────────────────────


class TestLocalToday:
    def test_sydney_is_already_tomorrow(self, frozen):
        frozen(SYDNEY_MORNING)
        assert timezones.local_today("Australia/Sydney") == date(2026, 9, 29)

    def test_los_angeles_is_still_yesterday(self, frozen):
        frozen(LA_EVENING)
        assert timezones.local_today("America/Los_Angeles") == date(2026, 9, 28)

    def test_utc_is_the_utc_date(self, frozen):
        frozen(LA_EVENING)
        assert timezones.local_today("UTC") == date(2026, 9, 29)

    def test_legacy_alias_is_resolved(self, frozen):
        frozen(LA_EVENING)
        assert timezones.local_today("US/Pacific") == date(2026, 9, 28)
        frozen(SYDNEY_MORNING)
        assert timezones.local_today("Asia/Calcutta") == date(2026, 9, 29)

    @pytest.mark.parametrize("bad", ["Mars/Olympus_Mons", "", "   ", None, 42])
    def test_unusable_name_falls_back_to_utc(self, frozen, bad):
        frozen(LA_EVENING)
        assert timezones.local_today(bad) == date(2026, 9, 29)


# ── the database layer takes the date, it does not pick one ──────────────────


@pytest.fixture
def cursor(monkeypatch):
    calls = []
    cur = MagicMock()
    cur.__enter__.return_value = cur
    cur.execute.side_effect = lambda sql, params=(): calls.append((" ".join(sql.split()), tuple(params)))
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(real_db, "db_conn", fake_conn)
    cur.calls = calls
    return cur


class TestQueriesUseTheGivenDate:
    DAY = date(2026, 9, 29)

    def test_today_standups(self, cursor):
        real_db.get_today_standups("T1", for_date=self.DAY)
        sql, params = cursor.calls[0]
        assert "CURRENT_DATE" not in sql
        assert params == ("T1", self.DAY)

    def test_standups_for_schedule(self, cursor):
        real_db.get_standups_for_schedule("T1", 7, days=1, for_date=self.DAY)
        sql, params = cursor.calls[0]
        assert "CURRENT_DATE" not in sql
        assert params == ("T1", 7, self.DAY, 1, self.DAY)

    def test_skip_is_written_and_read_under_the_given_date(self, cursor):
        real_db.skip_today("T1", "U1", for_date=self.DAY)
        real_db.is_skipped_today("T1", "U1", for_date=self.DAY)
        assert all("CURRENT_DATE" not in sql for sql, _ in cursor.calls)
        assert cursor.calls[0][1] == ("T1", "U1", self.DAY)
        assert cursor.calls[1][1] == ("T1", "U1", self.DAY)

    def test_saved_standup_carries_its_date(self, cursor):
        cursor.fetchone.return_value = (1,)
        real_db.save_standup("T1", "U1", "y", "t", "none", questions=["a", "b", "c"], standup_date=self.DAY)
        sql, params = cursor.calls[0]
        assert "standup_date" in sql
        assert params[-1] == self.DAY

    def test_no_date_means_the_utc_date(self, cursor, frozen):
        frozen(LA_EVENING)
        real_db.get_today_standups("T1")
        assert cursor.calls[0][1] == ("T1", date(2026, 9, 29))


# ── the member path files answers under the schedule's day ───────────────────


def _sydney_db(**schedule):
    db = MagicMock()
    db.get_standup_schedule.return_value = {
        "id": 1,
        "name": "Daily standup",
        "active": True,
        "schedule_tz": "Australia/Sydney",
        "participants": ["U1", "U2"],
        "questions": [],
        "post_summary": True,
        "group_by": "member",
        "report_channel": "",
        "nudge_missing": True,
        "nudge_minutes_before": 20,
        **schedule,
    }
    db.get_workspace_config.return_value = {"questions": [], "ai_summary_enabled": False, "schedule_tz": "UTC"}
    db.get_daily_thread_ts.return_value = None
    db.get_installation.return_value = {"team_name": "Acme", "bot_token": "xoxb-test"}
    db.get_active_members.return_value = [{"user_id": "U1", "real_name": "Ada"}]
    return db


def test_a_sydney_answer_is_filed_under_the_sydney_date(frozen):
    frozen(SYDNEY_MORNING)
    db = _sydney_db()
    with patch_modules({"src.core.db": db}):
        from src.modules.standup.handlers import _persist_standup

        _persist_standup("T1", "U1", ["y", "t", "none"], schedule_id=1)

    assert db.save_standup.call_args.kwargs["standup_date"] == date(2026, 9, 29)


def test_a_skip_is_filed_under_the_open_sessions_schedule_day(frozen):
    frozen(SYDNEY_MORNING)
    db = _sydney_db()
    import src.modules.standup.handlers as handlers

    with (
        patch_modules({"src.core.db": db}),
        patch.object(handlers.state_store, "get", return_value=SimpleNamespace(schedule_id=1)),
    ):
        handlers._record_skip("T1", "U1")

    db.get_standup_schedule.assert_called_with("T1", 1)
    assert db.skip_today.call_args.kwargs["for_date"] == date(2026, 9, 29)


# ── the report looks for them on the same day ────────────────────────────────


def _run_report(db):
    client = MagicMock()
    client.token = "xoxb-test"
    client.chat_postMessage.return_value = {"ts": "111.222"}
    with (
        patch_modules({"src.core.db": db}),
        patch.object(sched_mod, "WebClient", return_value=client),
        patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb-test"),
        patch.object(sched_mod, "_call_with_auth_retry", return_value=None),
    ):
        sched_mod._post_scheduled_report("T1", "xoxb-test", "C_STANDUP", 1)
    return client


def test_sydney_report_queries_the_local_date(frozen):
    frozen(SYDNEY_MORNING)
    db = _sydney_db()
    answers = [{"user_id": "U1", "yesterday": "a", "today": "b", "blockers": "", "has_blockers": False}]
    # Only the Sydney date has answers, as the member path now files them.
    db.get_today_standups.side_effect = lambda team_id, for_date=None: answers if for_date == date(2026, 9, 29) else []

    client = _run_report(db)

    assert db.get_today_standups.call_args.kwargs["for_date"] == date(2026, 9, 29)
    assert client.chat_postMessage.called
    # The daily thread is looked up under the same day the member path made it.
    assert db.get_daily_thread_ts.call_args.args[2] == "2026-09-29"


def test_late_us_report_queries_the_pacific_date(frozen):
    frozen(LA_EVENING)
    db = _sydney_db(schedule_tz="America/Los_Angeles")
    db.get_today_standups.return_value = []

    _run_report(db)

    assert db.get_today_standups.call_args.kwargs["for_date"] == date(2026, 9, 28)


# ── the nudge does not nag people who already answered or skipped ────────────


def _run_nudge(db):
    client = MagicMock()
    slack = MagicMock()
    slack.WebClient.return_value = client
    roster = MagicMock()
    roster.eligible_members.return_value = [SimpleNamespace(user_id="U1"), SimpleNamespace(user_id="U2")]
    with (
        patch_modules({"src.core.db": db, "src.core.roster": roster, "slack_sdk": slack}),
        patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb-test"),
    ):
        sched_mod._nudge_missing("T1", "xoxb-test", 1)
    return [c.kwargs["channel"] for c in client.chat_postMessage.call_args_list]


def test_nudge_skips_someone_who_answered_under_the_local_date(frozen):
    frozen(SYDNEY_MORNING)
    db = _sydney_db()
    db.get_standups_for_schedule.side_effect = lambda team_id, schedule_id, days=1, for_date=None: (
        [{"user_id": "U1"}] if for_date == date(2026, 9, 29) else []
    )
    db.is_skipped_today.return_value = False

    assert _run_nudge(db) == ["U2"]


def test_nudge_honours_a_skip_under_the_local_date(frozen):
    frozen(SYDNEY_MORNING)
    db = _sydney_db()
    db.get_standups_for_schedule.return_value = []
    db.is_skipped_today.side_effect = lambda team_id, user_id, for_date=None: (
        user_id == "U2" and for_date == date(2026, 9, 29)
    )

    assert _run_nudge(db) == ["U1"]


class TestWorkspaceLocalToday:
    def test_first_active_schedule_wins(self, frozen):
        frozen(SYDNEY_MORNING)
        schedules = [
            {"active": False, "schedule_tz": "America/Los_Angeles"},
            {"active": True, "schedule_tz": "Australia/Sydney"},
        ]
        with patch.object(real_db, "get_standup_schedules", return_value=schedules):
            assert real_db.workspace_local_today("T1") == date(2026, 9, 29)

    def test_falls_back_to_the_workspace_default_then_utc(self, frozen):
        frozen(LA_EVENING)
        with (
            patch.object(real_db, "get_standup_schedules", return_value=[]),
            patch.object(real_db, "get_workspace_config", return_value={"schedule_tz": "America/Los_Angeles"}),
        ):
            assert real_db.workspace_local_today("T1") == date(2026, 9, 28)
        with (
            patch.object(real_db, "get_standup_schedules", side_effect=Exception("db down")),
        ):
            assert real_db.workspace_local_today("T1") == date(2026, 9, 29)
