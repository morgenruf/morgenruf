"""Tests for the create standup modal guard against timing the scheduler rejects (#67).

Kept out of test_handlers.py because that module stubs pytz with a MagicMock,
which would accept every timezone.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Stub heavy third-party deps before any import of handlers
sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("requests", MagicMock())

# The validator needs the real tz database, whatever another module left behind.
if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]
import pytz as _real_pytz  # noqa: E402

# Stub session_store before importing state (state.py imports it at module level).
_prior_session_store = sys.modules.get("session_store")
_ss_mock = MagicMock()
_ss_mock.get_session.return_value = None
_ss_mock.has_session.return_value = False
sys.modules["session_store"] = _ss_mock

import handlers  # noqa: E402
import schedule_validation  # noqa: E402

if _prior_session_store is not None:
    sys.modules["session_store"] = _prior_session_store
else:
    sys.modules.pop("session_store", None)


def _view_handler(callback_id: str):
    """Register handlers against a fake Bolt app and return one view callback."""
    captured: dict = {}

    def view(name):
        def decorator(fn):
            captured[name] = fn
            return fn

        return decorator

    app = MagicMock()
    app.view.side_effect = view
    handlers.register_handlers(app)
    return captured[callback_id]


def _modal_body(timezone="Asia/Kolkata", report_time="09:30"):
    return {
        "user": {"id": "U1"},
        "team": {"id": "T1"},
        "view": {
            "private_metadata": "",
            "state": {
                "values": {
                    "standup_channel": {"standup_channel": {"selected_channel": "C1"}},
                    "questions": {"questions": {"value": "What did you do?"}},
                    "report_time": {"report_time": {"selected_option": {"value": report_time}}},
                    "timezone": {"timezone": {"selected_option": {"value": timezone}}},
                    "reminder": {"reminder": {"selected_option": {"value": "0"}}},
                    "members": {"members": {"selected_users": ["U1"]}},
                    "days": {"days": {"selected_options": [{"value": "mon"}]}},
                    "standup_name": {"standup_name": {"value": "Daily Standup"}},
                }
            },
        },
    }


class TestCreateStandupModalTimingGuard:
    def setup_method(self):
        self.handler = _view_handler("create_standup_modal")
        self.db = MagicMock()
        self.db.create_standup_schedule.return_value = None
        self.client = MagicMock()
        self.client.users_list.return_value = {
            "members": [{"id": "U1", "deleted": False, "is_bot": False}],
            "response_metadata": {},
        }

    def _submit(self, **body_kwargs):
        with (
            patch.dict(sys.modules, {"db": self.db}),
            patch.object(schedule_validation, "pytz", _real_pytz),
        ):
            self.handler(MagicMock(), _modal_body(**body_kwargs), self.client)

    def _messages(self):
        return [kwargs.get("text", "") for _, kwargs in self.client.chat_postMessage.call_args_list]

    def test_valid_timezone_is_saved(self):
        self._submit(timezone="Asia/Kolkata")
        self.db.create_standup_schedule.assert_called_once()

    def test_invalid_timezone_is_not_saved(self):
        self._submit(timezone="Asia/Kolkatta")
        self.db.create_standup_schedule.assert_not_called()

    def test_invalid_timezone_tells_the_user_why(self):
        self._submit(timezone="Asia/Kolkatta")
        assert any("Asia/Kolkatta" in text for text in self._messages())

    def test_invalid_time_is_not_saved(self):
        self._submit(report_time="9am")
        self.db.create_standup_schedule.assert_not_called()
        assert any("9am" in text for text in self._messages())
