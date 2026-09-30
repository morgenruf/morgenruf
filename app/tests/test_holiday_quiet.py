"""Standups and coffee chats stay quiet on a company holiday.

The holiday list was only read by Celebrations, so the standup DM, the
reminder, the nudge, the report and coffee chat rounds all fired on a
company holiday, while the Celebrations page says the calendar is shared.

Only the holiday list applies. The working week column defaults to Monday
to Friday for every workspace, so it cannot suppress a Saturday standup
somebody set up on purpose.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import src.core.scheduler as sched_mod
import src.core.workspace_calendar as wcal

from tests.support import patch_modules

HOLIDAY = date(2026, 12, 25)
SATURDAY = date(2026, 9, 26)


def _db(holidays=(HOLIDAY,)):
    db = MagicMock()
    db.list_holidays.return_value = [{"date": d, "name": "Day off"} for d in holidays]
    db.get_standup_schedule.return_value = {
        "id": 1,
        "name": "Daily",
        "active": True,
        "participants": ["U1"],
        "channel_id": "C1",
        "schedule_tz": "UTC",
        "nudge_missing": True,
    }
    db.get_active_members.return_value = [{"user_id": "U1"}]
    db.is_skipped_today.return_value = False
    db.is_on_vacation.return_value = False
    db.get_standups_for_schedule.return_value = []
    db.get_today_standups.return_value = [{"user_id": "U1"}]
    return db


class TestIsCompanyHoliday:
    def test_a_listed_day_is_a_holiday(self):
        with patch_modules({"src.core.db": _db()}):
            assert wcal.is_company_holiday("T1", HOLIDAY) is True
            assert wcal.is_company_holiday("T1", date(2026, 12, 24)) is False

    def test_the_working_week_is_not_consulted(self):
        db = _db(holidays=())
        db.get_working_days.return_value = "mon,tue,wed,thu,fri"
        with patch_modules({"src.core.db": db}):
            assert wcal.is_company_holiday("T1", SATURDAY) is False

    def test_a_failed_lookup_is_an_ordinary_day(self):
        db = _db()
        db.list_holidays.side_effect = Exception("db down")
        with patch_modules({"src.core.db": db}):
            assert wcal.is_company_holiday("T1", HOLIDAY) is False


def _run(func, day, db, *args):
    # A stand-in session store, so a delivered DM leaves no session behind
    # for later tests to trip over.
    store = MagicMock()
    store.blocks_scheduled_dm.return_value = False
    client = MagicMock()
    client.token = "xoxb"
    with (
        patch_modules({"src.core.db": db}),
        patch.object(sched_mod, "WebClient", return_value=client),
        patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb"),
        patch.object(sched_mod, "_call_with_auth_retry", return_value=None),
        patch.object(sched_mod, "_slack_dm_with_retry") as dm,
        patch.object(sched_mod, "state_store", store),
        patch.object(sched_mod, "local_today", return_value=day),
        patch.object(sched_mod, "_schedule_today", return_value=day),
        patch("src.core.roster.eligible_members", return_value=[MagicMock(user_id="U1")]),
        patch("slack_sdk.WebClient", return_value=client),
        patch("src.modules.standup.workflow.evaluate_low_participation") as rules,
    ):
        func(*args)
    return client, dm, rules


class TestStandupJobs:
    def test_no_standup_dm_on_a_holiday(self):
        _, dm, _ = _run(sched_mod._send_standup_to_workspace, HOLIDAY, _db(), "T1", "xoxb", "C1", 1)
        dm.assert_not_called()

    def test_a_saturday_standup_still_runs(self):
        _, dm, _ = _run(sched_mod._send_standup_to_workspace, SATURDAY, _db(), "T1", "xoxb", "C1", 1)
        dm.assert_called_once()

    def test_no_reminder_on_a_holiday(self):
        _, dm, _ = _run(sched_mod._send_reminder_to_workspace, HOLIDAY, _db(), "T1", "xoxb", 15, 1)
        dm.assert_not_called()

    def test_no_nudge_on_a_holiday(self):
        client, _, _ = _run(sched_mod._nudge_missing, HOLIDAY, _db(), "T1", "xoxb", 1)
        client.chat_postMessage.assert_not_called()

    def test_nudge_still_runs_on_an_ordinary_day(self):
        client, _, _ = _run(sched_mod._nudge_missing, date(2026, 12, 23), _db(), "T1", "xoxb", 1)
        client.chat_postMessage.assert_called_once()

    def test_no_report_or_participation_check_on_a_holiday(self):
        client, _, rules = _run(sched_mod._post_scheduled_report, HOLIDAY, _db(), "T1", "xoxb", "C1", 1)
        client.chat_postMessage.assert_not_called()
        rules.assert_not_called()


class TestConnectRounds:
    def _run_round(self, monkeypatch, holiday, force=False):
        import src.modules.connect.db as cdb
        import src.modules.connect.jobs as jobs

        monday = datetime(2026, 12, 21, 14, 0, tzinfo=timezone.utc)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return monday.astimezone(tz) if tz else monday

        monkeypatch.setattr(jobs, "datetime", FixedDatetime)
        program = {
            "id": 1,
            "team_id": "T1",
            "channel_id": "C1",
            "enabled": True,
            "interval_weeks": 1,
            "day_of_week": 0,
            "timezone": "UTC",
            "next_round_date": None,
            "last_round": None,
            "last_scheduled_round": None,
        }
        monkeypatch.setattr(cdb, "get_program", lambda _id: program)
        monkeypatch.setattr(jobs, "is_company_holiday", lambda team, day: holiday and day == date(2026, 12, 21))
        created = []
        monkeypatch.setattr(cdb, "create_round", lambda *a, **k: created.append(a) or None)
        monkeypatch.setattr(cdb, "optout_user_ids", lambda *a, **k: set())
        monkeypatch.setattr(jobs, "_client", lambda *_: object())
        monkeypatch.setattr(jobs.api, "channel_member_ids", lambda *_: ["U1", "U2", "U3"])
        import src.core.roster as roster

        monkeypatch.setattr(
            roster, "eligible_members", lambda _t: [type("M", (), {"user_id": u})() for u in ("U1", "U2", "U3")]
        )
        jobs.run_round(1, force=force)
        return created

    def test_no_round_on_a_holiday(self, monkeypatch):
        assert self._run_round(monkeypatch, holiday=True) == []

    def test_a_round_runs_on_an_ordinary_day(self, monkeypatch):
        assert len(self._run_round(monkeypatch, holiday=False)) == 1

    def test_run_now_is_not_blocked(self, monkeypatch):
        assert len(self._run_round(monkeypatch, holiday=True, force=True)) == 1
