"""Tests for scheduler.py — DB→scheduler reconciliation and reminder guards."""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Earlier test modules leave MagicMock stubs in sys.modules (test_handlers stubs
# pytz, test_dashboard stubs slack_sdk). The scheduler needs the real pytz for
# CronTrigger timezones, so drop leaked stubs before importing it.
for _name in ("pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

# Stub session_store before importing state (state.py imports it at module level).
_prior_session_store = sys.modules.get("session_store")
_ss_mock = MagicMock()
_ss_mock.get_session.return_value = None
# Without this the bare MagicMock answers "yes" and every member looks like they
# already have a session open, which only shows up when this module runs alone.
_ss_mock.has_session.return_value = False
sys.modules["session_store"] = _ss_mock

_had_scheduler = "scheduler" in sys.modules
import scheduler as sched_mod  # noqa: E402

if _had_scheduler:
    # Re-import so module-level bindings (pytz, WebClient) point at the real deps.
    sched_mod = importlib.reload(sched_mod)

if _prior_session_store is not None:
    sys.modules["session_store"] = _prior_session_store
else:
    sys.modules.pop("session_store", None)

from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402


def _schedule_row(team_id="T1", schedule_id=1, **overrides):
    row = {
        "id": schedule_id,
        "team_id": team_id,
        "bot_token": "xoxb-test",
        "name": "Morning Standup",
        "channel_id": "C1",
        "schedule_time": "10:00",
        "schedule_tz": "Europe/Amsterdam",
        "schedule_days": "mon,tue,wed,thu,fri",
        "questions": [],
        "participants": ["U1", "U2"],
        "reminder_minutes": 30,
        "weekend_reminder": False,
        "report_time": None,
        "active": True,
    }
    row.update(overrides)
    return row


def _installation_row(team_id="T1"):
    return {"team_id": team_id, "bot_token": "xoxb-test", "team_name": "Test"}


def _make_db(schedules=None, installations=None, config=None):
    db = MagicMock()
    db.get_all_active_schedules.return_value = schedules or []
    db.get_all_installations.return_value = installations or []
    db.get_workspace_config.return_value = config if config is not None else {"active": True}
    return db


class _SyncTestBase:
    def setup_method(self):
        self.scheduler = BackgroundScheduler()
        sched_mod._scheduler = self.scheduler
        sched_mod._synced_schedule_fps.clear()
        sched_mod._synced_workspace_fps.clear()

    def teardown_method(self):
        sched_mod._scheduler = None
        sched_mod._synced_schedule_fps.clear()
        sched_mod._synced_workspace_fps.clear()

    def sync(self, db):
        with patch.dict(sys.modules, {"db": db}):
            sched_mod._sync_jobs_from_db()


class TestSyncRegistersNewSchedules(_SyncTestBase):
    def test_new_schedule_gets_jobs(self):
        db = _make_db(schedules=[_schedule_row()], installations=[_installation_row()])
        self.sync(db)
        assert self.scheduler.get_job("schedule_T1_1") is not None
        assert self.scheduler.get_job("reminder_schedule_T1_1") is not None
        assert self.scheduler.get_job("report_schedule_T1_1") is not None

    def test_team_with_schedules_gets_digests_only(self):
        db = _make_db(schedules=[_schedule_row()], installations=[_installation_row()])
        self.sync(db)
        assert self.scheduler.get_job("digest_T1") is not None
        assert self.scheduler.get_job("standup_T1") is None

    def test_team_without_schedules_gets_workspace_job(self):
        config = {"active": True, "channel_id": "C9", "schedule_time": "09:00", "schedule_tz": "UTC"}
        db = _make_db(installations=[_installation_row()], config=config)
        self.sync(db)
        assert self.scheduler.get_job("standup_T1") is not None

    def test_unchanged_schedule_not_reregistered(self):
        db = _make_db(schedules=[_schedule_row()], installations=[_installation_row()])
        self.sync(db)
        job_before = self.scheduler.get_job("schedule_T1_1")
        with patch.object(sched_mod, "register_schedule_job") as reg:
            self.sync(db)
            reg.assert_not_called()
        assert self.scheduler.get_job("schedule_T1_1") is job_before


class TestSyncPicksUpEdits(_SyncTestBase):
    def test_time_change_reregisters(self):
        db = _make_db(schedules=[_schedule_row(schedule_time="10:00")], installations=[_installation_row()])
        self.sync(db)
        db2 = _make_db(schedules=[_schedule_row(schedule_time="11:30")], installations=[_installation_row()])
        self.sync(db2)
        trigger = self.scheduler.get_job("schedule_T1_1").trigger
        assert "hour='11'" in str(trigger)
        assert "minute='30'" in str(trigger)

    def test_reminder_switched_off_removes_reminder_job(self):
        db = _make_db(schedules=[_schedule_row(reminder_minutes=30)], installations=[_installation_row()])
        self.sync(db)
        assert self.scheduler.get_job("reminder_schedule_T1_1") is not None
        db2 = _make_db(schedules=[_schedule_row(reminder_minutes=0)], installations=[_installation_row()])
        self.sync(db2)
        assert self.scheduler.get_job("reminder_schedule_T1_1") is None
        assert self.scheduler.get_job("schedule_T1_1") is not None


class TestSyncRemovesDeletedSchedules(_SyncTestBase):
    def test_deleted_schedule_jobs_removed(self):
        db = _make_db(schedules=[_schedule_row()], installations=[_installation_row()])
        self.sync(db)
        db2 = _make_db(schedules=[], installations=[_installation_row()])
        self.sync(db2)
        assert self.scheduler.get_job("schedule_T1_1") is None
        assert self.scheduler.get_job("reminder_schedule_T1_1") is None
        # Workspace falls back to workspace-level standup jobs
        assert self.scheduler.get_job("standup_T1") is not None

    def test_uninstalled_workspace_jobs_removed(self):
        db = _make_db(installations=[_installation_row()])
        self.sync(db)
        assert self.scheduler.get_job("standup_T1") is not None
        db2 = _make_db(installations=[])
        self.sync(db2)
        assert self.scheduler.get_job("standup_T1") is None
        assert self.scheduler.get_job("digest_T1") is None


class TestSyncResilience(_SyncTestBase):
    def test_db_error_leaves_jobs_untouched(self):
        db = _make_db(schedules=[_schedule_row()], installations=[_installation_row()])
        self.sync(db)
        bad_db = MagicMock()
        bad_db.get_all_active_schedules.side_effect = RuntimeError("db down")
        self.sync(bad_db)
        assert self.scheduler.get_job("schedule_T1_1") is not None

    def test_noop_without_scheduler(self):
        sched_mod._scheduler = None
        db = _make_db(schedules=[_schedule_row()])
        self.sync(db)  # must not raise


class TestBuildSchedulerRegistersSyncJob(_SyncTestBase):
    def test_sync_job_present(self):
        db = _make_db(schedules=[_schedule_row()])
        with patch.dict(sys.modules, {"db": db}):
            scheduler = sched_mod.build_scheduler([])
        assert scheduler.get_job("schedule_sync") is not None
        # build seeds fingerprints so the first sync run doesn't re-register
        assert ("T1", 1) in sched_mod._synced_schedule_fps


class TestEndToEndStandupDelivery(_SyncTestBase):
    """Regression test for #51: a schedule created via the dashboard after boot
    must be picked up by the sync job and actually deliver the standup DM."""

    def test_dashboard_created_schedule_delivers_dm(self):
        # Master process booted before the schedule existed
        empty_db = _make_db(installations=[_installation_row()])
        self.sync(empty_db)
        assert self.scheduler.get_job("schedule_T1_1") is None

        # The dashboard (in the forked worker) inserts the schedule into the DB;
        # the next sync tick in this process must register it.
        db = _make_db(schedules=[_schedule_row()], installations=[_installation_row()])
        db.get_standup_schedule.return_value = _schedule_row()
        db.get_installation.return_value = {"bot_token": "xoxb-test"}
        db.get_active_members.return_value = [{"user_id": "U1", "real_name": "Davide"}]
        db.is_skipped_today.return_value = False
        db.is_on_vacation.return_value = False
        self.sync(db)
        job = self.scheduler.get_job("schedule_T1_1")
        assert job is not None

        # Fire the registered job and assert the standup DM goes out.
        client = MagicMock()
        client.conversations_open.return_value = {"channel": {"id": "D123"}}
        with (
            patch.dict(sys.modules, {"db": db}),
            patch.object(sched_mod, "WebClient", return_value=client),
        ):
            job.func(*job.args)

        client.conversations_open.assert_called_once_with(users="U1")
        posted = [kwargs for _, kwargs in client.chat_postMessage.call_args_list]
        assert any(kw.get("channel") == "D123" for kw in posted)
        assert any("Time for your standup" in (kw.get("text") or "") for kw in posted)


class TestReminderSkipsInactiveSchedule(_SyncTestBase):
    def _run_reminder(self, sched_row):
        db = MagicMock()
        db.get_active_members.return_value = [{"user_id": "U1"}]
        db.get_standup_schedule.return_value = sched_row
        db.get_installation.return_value = None
        with (
            patch.dict(sys.modules, {"db": db}),
            patch.object(sched_mod, "WebClient") as web_client,
            patch.object(sched_mod, "evaluate_rules", create=True),
        ):
            sched_mod._send_reminder_to_workspace("T1", "xoxb-test", 30, schedule_id=1)
        return web_client

    def test_deleted_schedule_sends_nothing(self):
        web_client = self._run_reminder(None)
        web_client.return_value.conversations_open.assert_not_called()

    def test_inactive_schedule_sends_nothing(self):
        web_client = self._run_reminder(_schedule_row(active=False))
        web_client.return_value.conversations_open.assert_not_called()


class TestInvalidScheduleIsReportable(_SyncTestBase):
    """#67: an unusable timezone leaves an Active schedule with no job at all."""

    def test_invalid_timezone_registers_no_job(self):
        sched_mod.register_schedule_job(self.scheduler, _schedule_row(schedule_tz="Asia/Kolkatta"))
        assert self.scheduler.get_job("schedule_T1_1") is None

    def test_invalid_timezone_is_reported(self):
        rows = [_schedule_row(schedule_tz="Asia/Kolkatta")]
        problems = sched_mod.get_unregistered_schedules(self.scheduler, rows)
        assert len(problems) == 1
        assert problems[0]["id"] == 1
        assert problems[0]["team_id"] == "T1"
        assert "Asia/Kolkatta" in problems[0]["reason"]

    def test_invalid_time_is_reported(self):
        problems = sched_mod.get_unregistered_schedules(self.scheduler, [_schedule_row(schedule_time="9am")])
        assert len(problems) == 1
        assert "9am" in problems[0]["reason"]

    def test_registered_schedule_is_not_reported(self):
        rows = [_schedule_row()]
        sched_mod.register_schedule_job(self.scheduler, rows[0])
        assert sched_mod.get_unregistered_schedules(self.scheduler, rows) == []

    def test_active_schedule_with_no_job_is_reported(self):
        problems = sched_mod.get_unregistered_schedules(self.scheduler, [_schedule_row()])
        assert len(problems) == 1
        assert "No standup job" in problems[0]["reason"]

    def test_inactive_schedule_is_ignored(self):
        assert sched_mod.get_unregistered_schedules(self.scheduler, [_schedule_row(active=False)]) == []

    def test_config_problems_are_reported_without_a_running_scheduler(self):
        """The dashboard worker has no scheduler of its own, but can still tell."""
        problems = sched_mod.get_unregistered_schedules(None, [_schedule_row(schedule_tz="IST")])
        assert len(problems) == 1

    def test_schedules_are_read_from_the_db_when_not_supplied(self):
        db = _make_db(schedules=[_schedule_row(schedule_tz="Asia/Kolkatta")])
        with patch.dict(sys.modules, {"db": db}):
            problems = sched_mod.get_unregistered_schedules(self.scheduler)
        assert len(problems) == 1

    def test_db_error_reports_nothing(self):
        db = MagicMock()
        db.get_all_active_schedules.side_effect = RuntimeError("db down")
        with patch.dict(sys.modules, {"db": db}):
            assert sched_mod.get_unregistered_schedules(self.scheduler) == []
