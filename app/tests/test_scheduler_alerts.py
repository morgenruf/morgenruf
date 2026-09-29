"""Weekend reminder scope, and operator alerts when a scheduled job fails or misses.

The weekend reminder was registered without its schedule id, so it DMed every
active member of the workspace instead of the schedule's participants. And a
job that raised or missed its time left only a log line, which is how a coffee
round went missing on 2026-09-28 with nobody told.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

for _name in ("pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

_prior_session_store = sys.modules.get("src.core.session_store")
_ss_mock = MagicMock()
_ss_mock.get_session.return_value = None
_ss_mock.has_session.return_value = False
sys.modules["src.core.session_store"] = _ss_mock
import src.core.scheduler as sched_mod  # noqa: E402

if _prior_session_store is not None:
    sys.modules["src.core.session_store"] = _prior_session_store
else:
    sys.modules.pop("src.core.session_store", None)

import pytest  # noqa: E402
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobExecutionEvent  # noqa: E402
from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402
from apscheduler.triggers.cron import CronTrigger  # noqa: E402
from apscheduler.triggers.interval import IntervalTrigger  # noqa: E402


def _row(**overrides):
    row = {
        "id": 7,
        "team_id": "T1",
        "bot_token": "xoxb-test",
        "name": "Morning Standup",
        "channel_id": "C1",
        "schedule_time": "10:00",
        "schedule_tz": "Europe/Amsterdam",
        "schedule_days": "mon,tue,wed,thu,fri",
        "questions": [],
        "participants": ["U1", "U2"],
        "reminder_minutes": 30,
        "weekend_reminder": True,
        "report_time": None,
        "active": True,
    }
    row.update(overrides)
    return row


class TestWeekendReminderScope:
    def test_weekend_reminder_carries_the_schedule_id(self):
        scheduler = BackgroundScheduler()
        sched_mod.register_schedule_job(scheduler, _row())
        job = scheduler.get_job("weekend_reminder_schedule_T1_7")
        assert job is not None
        assert job.args[3] == 7

    def test_weekend_reminder_via_minus_one_carries_the_schedule_id(self):
        scheduler = BackgroundScheduler()
        sched_mod.register_schedule_job(scheduler, _row(weekend_reminder=False, reminder_minutes=-1))
        job = scheduler.get_job("weekend_reminder_schedule_T1_7")
        assert job.args[3] == 7


class TestJobAlerts:
    @pytest.fixture(autouse=True)
    def scheduler(self):
        scheduler = BackgroundScheduler()
        scheduler.add_job(lambda: None, CronTrigger(hour=9), id="standup_T1_7")
        scheduler.add_job(lambda: None, IntervalTrigger(minutes=2), id="db_sync")
        sched_mod._scheduler = scheduler
        sched_mod._job_alerted_at.clear()
        yield scheduler
        sched_mod._scheduler = None
        sched_mod._job_alerted_at.clear()

    def _fire(self, code, job_id, exception=None):
        event = JobExecutionEvent(
            code, job_id, "default", datetime(2026, 9, 28, 9, tzinfo=timezone.utc), exception=exception
        )
        with patch("src.core.alerts.notify") as notify:
            sched_mod._alert_on_job_problem(event)
        return notify

    def test_missed_cron_job_alerts(self):
        notify = self._fire(EVENT_JOB_MISSED, "standup_T1_7")
        notify.assert_called_once()
        assert "standup_T1_7" in notify.call_args.args[0]
        assert "missed" in notify.call_args.args[0]

    def test_missed_interval_job_does_not_alert(self):
        self._fire(EVENT_JOB_MISSED, "db_sync").assert_not_called()

    def test_failed_job_alerts_with_the_error(self):
        notify = self._fire(EVENT_JOB_ERROR, "db_sync", RuntimeError("token revoked"))
        assert "token revoked" in notify.call_args.args[0]

    def test_repeat_failures_alert_once_per_window(self):
        self._fire(EVENT_JOB_ERROR, "standup_T1_7", RuntimeError("x")).assert_called_once()
        self._fire(EVENT_JOB_ERROR, "standup_T1_7", RuntimeError("x")).assert_not_called()

    def test_alert_failure_never_raises(self):
        event = JobExecutionEvent(EVENT_JOB_ERROR, "standup_T1_7", "default", None, exception=RuntimeError("x"))
        with patch("src.core.alerts.notify", side_effect=RuntimeError("webhook down")):
            sched_mod._alert_on_job_problem(event)

    def test_build_scheduler_registers_the_listener(self):
        with patch.object(sched_mod, "BackgroundScheduler") as cls:
            with patch.dict(sys.modules, {"src.core.db": MagicMock(get_all_active_schedules=lambda: [])}):
                sched_mod.build_scheduler([])
        cls.return_value.add_listener.assert_called_once_with(
            sched_mod._alert_on_job_problem, EVENT_JOB_ERROR | EVENT_JOB_MISSED
        )


class TestExecutors:
    def test_background_jobs_and_standups_use_separate_pools(self):
        with patch.dict(sys.modules, {"src.core.db": MagicMock(get_all_active_schedules=lambda: [])}):
            scheduler = sched_mod.build_scheduler([])
        bulk = {j.id for j in scheduler.get_jobs() if j.executor == sched_mod.BULK_EXECUTOR}
        assert {"member_sync", "schedule_sync", "module_job_sync", "token_maintenance"} <= bulk

    def test_standup_jobs_stay_on_the_default_pool(self):
        scheduler = BackgroundScheduler()
        sched_mod.register_schedule_job(scheduler, _row())
        assert {j.executor for j in scheduler.get_jobs()} == {"default"}
