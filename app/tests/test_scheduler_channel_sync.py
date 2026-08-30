"""Regression tests for #53: channel sync must not add bots as participants.

Kept in its own module (rather than test_scheduler.py) so it does not collide
with the scheduler test file added by the #51 reconciliation work.
"""

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

_had_scheduler = "scheduler" in sys.modules
import scheduler as sched_mod  # noqa: E402

if _had_scheduler:
    sched_mod = importlib.reload(sched_mod)


def _slack_user(uid, **overrides):
    user = {"id": uid, "deleted": False, "is_bot": False}
    user.update(overrides)
    return user


def _schedule(**overrides):
    row = {
        "id": 1,
        "team_id": "T1",
        "name": "Morning Standup",
        "channel_id": "C1",
        "sync_with_channel": True,
        "participants": [],
        "questions": [],
        "active": True,
    }
    row.update(overrides)
    return row


class TestChannelSyncFiltersBots:
    """The channel contains the reporter plus two apps, one of them Morgenruf."""

    def setup_method(self):
        self.db = MagicMock()
        self.db.get_standup_schedule.return_value = _schedule()
        self.db.get_active_members.return_value = [
            {"user_id": "U1", "real_name": "Reporter"},
            {"user_id": "BMORGENRUF", "real_name": "Morgenruf"},
            {"user_id": "BOTHER", "real_name": "Other App"},
        ]
        self.db.is_skipped_today.return_value = False
        self.db.is_on_vacation.return_value = False

        self.client = MagicMock()
        self.client.conversations_members.return_value = {
            "members": ["U1", "BMORGENRUF", "BOTHER"],
            "response_metadata": {},
        }
        self.client.users_list.return_value = {
            "members": [
                _slack_user("U1"),
                _slack_user("BMORGENRUF", is_bot=True),
                _slack_user("BOTHER", is_bot=True),
            ],
            "response_metadata": {},
        }
        self.client.conversations_open.return_value = {"channel": {"id": "D1"}}

    def _run(self):
        with (
            patch.dict(sys.modules, {"db": self.db}),
            patch.object(sched_mod, "WebClient", return_value=self.client),
            patch.object(sched_mod.state_store, "is_active", return_value=False),
        ):
            sched_mod._send_standup_to_workspace("T1", "xoxb-test", "C1", 1)

    def test_bots_are_not_saved_as_participants(self):
        self._run()
        self.db.update_standup_schedule.assert_called_once()
        _, kwargs = self.db.update_standup_schedule.call_args
        assert set(kwargs["participants"]) == {"U1"}

    def test_bots_are_not_upserted_as_members(self):
        self._run()
        upserted = {call.args[1] for call in self.db.upsert_member.call_args_list}
        assert upserted == {"U1"}

    def test_no_dm_is_attempted_against_a_bot(self):
        self._run()
        dm_targets = {kwargs["users"] for _, kwargs in self.client.conversations_open.call_args_list}
        assert dm_targets == {"U1"}
