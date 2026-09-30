"""blocker.detected and participation.low are sent, not only offered.

Both were in the webhook event list, but the app only ever called
fire_webhooks with standup.completed, so a subscriber to either got nothing.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import src.modules.standup.handlers as handlers
import src.modules.standup.workflow as workflow

from tests.support import patch_modules

QUESTIONS = ["What did you do?", "What will you do?", "Any blockers?"]


def _session(answers):
    return SimpleNamespace(
        team_id="T1",
        channel="C1",
        questions=list(QUESTIONS),
        answers=list(answers),
        standup_name="Daily",
        schedule_id=7,
        editing_standup_id=None,
    )


def _complete(answers):
    db = MagicMock()
    db.get_standup_schedule.return_value = {"id": 7, "name": "Daily", "channel_id": "C1"}
    db.get_workspace_config.return_value = {}
    db.get_daily_thread_ts.return_value = "1.1"
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "2.2"}
    fired = MagicMock()
    with (
        patch_modules({"src.core.db": db}),
        patch.object(handlers, "_persist_standup", return_value=42),
        patch.object(handlers, "fire_webhooks", fired),
        patch.object(handlers, "state_store"),
        patch("src.core.scheduler.standup_local_date", return_value=date(2026, 9, 29)),
        patch("src.modules.standup.workflow.evaluate_rules"),
    ):
        handlers._complete_standup("U1", _session(answers), client)
    return {call.args[1]: call.args[2] for call in fired.call_args_list}


class TestBlockerDetected:
    def test_a_reported_blocker_fires_the_event(self):
        events = _complete(["shipped", "testing", "waiting on the API keys"])
        assert "standup.completed" in events
        payload = events["blocker.detected"]
        assert payload["team_id"] == "T1"
        assert payload["user_id"] == "U1"
        assert payload["schedule_id"] == 7
        assert payload["blockers"] == "waiting on the API keys"
        assert "timestamp" in payload

    def test_no_blocker_sends_only_completed(self):
        events = _complete(["shipped", "testing", "none"])
        assert set(events) == {"standup.completed"}


class TestParticipationLow:
    def _run(self, answered, participants=("U1", "U2", "U3", "U4")):
        fired = MagicMock()
        db = MagicMock()
        db.is_skipped_today.return_value = False
        standups = [{"user_id": u} for u in answered]
        with (
            patch_modules({"src.core.db": db}),
            patch("src.core.roster.eligible_members", return_value=[SimpleNamespace(user_id=u) for u in participants]),
            patch("src.modules.standup.workflow.evaluate_rules"),
            patch("src.modules.standup.handlers.fire_webhooks", fired),
        ):
            workflow.evaluate_low_participation(
                "T1", {"id": 7, "name": "Daily", "participants": list(participants)}, date(2026, 9, 29), standups, None
            )
        return fired

    def test_below_the_threshold_fires(self):
        fired = self._run(answered=["U1"])  # 25 percent
        fired.assert_called_once()
        team, event, payload = fired.call_args.args
        assert (team, event) == ("T1", "participation.low")
        assert payload["schedule_id"] == 7
        assert payload["schedule"] == "Daily"
        assert payload["participation_pct"] == 25
        assert payload["threshold"] == 50
        assert payload["date"] == "2026-09-29"

    def test_at_or_above_the_threshold_does_not_fire(self):
        fired = self._run(answered=["U1", "U2"])  # 50 percent
        fired.assert_not_called()
