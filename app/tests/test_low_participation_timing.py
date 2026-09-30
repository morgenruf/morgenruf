"""low_participation rules run when the report is posted, for that standup only.

They used to run in the pre-standup reminder over the whole workspace with a
one day window. Nobody has answered before the standup starts, so the figure
was 0 percent and the rule fired every single day.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import src.core.scheduler as sched_mod

from tests.support import patch_modules

DAY = date(2026, 9, 29)


def _schedule(participants):
    return {
        "id": 1,
        "name": "Daily standup",
        "participants": participants,
        "questions": [],
        "post_summary": True,
        "group_by": "member",
        "report_channel": "",
        "schedule_tz": "UTC",
    }


def _db(participants, answered, skipped=()):
    db = MagicMock()
    db.get_standup_schedule.return_value = _schedule(participants)
    db.get_today_standups.return_value = [
        {"user_id": u, "yesterday": "a", "today": "b", "blockers": "", "has_blockers": False} for u in answered
    ]
    db.is_skipped_today.side_effect = lambda team, user, for_date=None: user in skipped
    db.get_workspace_config.return_value = {"questions": [], "ai_summary_enabled": False}
    db.get_daily_thread_ts.return_value = None
    db.get_installation.return_value = {"team_name": "Acme", "bot_token": "xoxb-test"}
    db.list_holidays.return_value = []
    return db


def _report(db, eligible):
    client = MagicMock()
    client.token = "xoxb-test"
    client.chat_postMessage.return_value = {"ts": "1.2"}
    rules = MagicMock()
    members = [SimpleNamespace(user_id=u) for u in eligible]
    with (
        patch_modules({"src.core.db": db}),
        patch.object(sched_mod, "WebClient", return_value=client),
        patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb-test"),
        patch.object(sched_mod, "_call_with_auth_retry", return_value=None),
        patch.object(sched_mod, "_schedule_today", return_value=DAY),
        patch("src.core.roster.eligible_members", return_value=members),
        patch("src.modules.standup.workflow.evaluate_rules", rules),
    ):
        sched_mod._post_scheduled_report("T1", "xoxb-test", "C1", 1)
    return rules


def _pct(rules):
    assert rules.call_count == 1
    trigger, context = rules.call_args.args[1], rules.call_args.args[2]
    assert trigger == "low_participation"
    return context["participation_pct"]


class TestAtReportTime:
    def test_nobody_answered_still_evaluates_the_rule(self):
        # The report itself is skipped, but this is the day the rule is for.
        rules = _report(_db(["U1", "U2"], answered=[]), eligible=["U1", "U2"])
        assert _pct(rules) == 0

    def test_counts_only_this_standups_participants(self):
        # U3 is in the workspace and did not answer, but is not on this standup.
        rules = _report(_db(["U1", "U2"], answered=["U1"]), eligible=["U1", "U2", "U3"])
        assert _pct(rules) == 50

    def test_everyone_answered_is_100(self):
        rules = _report(_db(["U1", "U2"], answered=["U1", "U2"]), eligible=["U1", "U2"])
        assert _pct(rules) == 100

    def test_skips_and_leave_are_not_counted_as_missing(self):
        # U2 skipped today and U3 is on leave (not eligible).
        rules = _report(_db(["U1", "U2", "U3"], answered=["U1"], skipped={"U2"}), eligible=["U1", "U2"])
        assert _pct(rules) == 100


class TestNotInTheReminder:
    def test_reminder_does_not_evaluate_rules(self):
        db = MagicMock()
        db.get_active_members.return_value = [{"user_id": "U1"}]
        db.get_standup_schedule.return_value = {**_schedule(["U1"]), "active": True}
        db.is_skipped_today.return_value = False
        db.list_holidays.return_value = []
        rules = MagicMock()
        with (
            patch_modules({"src.core.db": db}),
            patch.object(sched_mod, "WebClient"),
            patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb-test"),
            patch.object(sched_mod, "_slack_dm_with_retry"),
            patch("src.modules.standup.workflow.evaluate_rules", rules),
        ):
            sched_mod._send_reminder_to_workspace("T1", "xoxb-test", 15, schedule_id=1)
        rules.assert_not_called()
