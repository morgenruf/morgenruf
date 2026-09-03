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


def _find_block(blocks, block_id):
    for block in blocks:
        if block.get("block_id") == block_id:
            return block
    return None


class TestStandupTimeFieldIsNamedForWhatItDoes:
    """#118 — the field that sets the DM time was labelled "Report time", so
    users set it believing it controlled when the channel summary posts."""

    def _modal(self, cfg=None):
        import blocks as blocks_mod

        return blocks_mod.create_standup_modal(cfg, bot_channels=[{"id": "C1", "name": "general"}])["blocks"]

    def test_standup_time_block_is_labelled_standup_time(self):
        block = _find_block(self._modal(), "standup_time")
        assert block is not None
        assert block["label"]["text"] == "Standup time"

    def test_no_block_claims_to_be_report_time_while_setting_the_dm_time(self):
        assert _find_block(self._modal(), "report_time") is not None
        assert _find_block(self._modal(), "report_time")["label"]["text"] == "Report time"

    def test_report_time_block_is_optional(self):
        assert _find_block(self._modal(), "report_time").get("optional") is True

    def test_report_time_defaults_to_an_hour_after_the_standup(self):
        block = _find_block(self._modal({"report_time": None, "standup_time": "16:45"}), "report_time")
        assert block["element"]["initial_option"]["value"] == "17:45"

    def test_existing_report_time_is_prefilled(self):
        block = _find_block(self._modal({"standup_time": "09:00", "report_time": "18:15"}), "report_time")
        assert block["element"]["initial_option"]["value"] == "18:15"


class TestModalSubmissionReadsBothTimes:
    def setup_method(self):
        self.handler = _view_handler("create_standup_modal")
        self.db = MagicMock()
        self.db.create_standup_schedule.return_value = None
        self.client = MagicMock()
        self.client.users_list.return_value = {
            "members": [{"id": "U1", "deleted": False, "is_bot": False}],
            "response_metadata": {},
        }

    def _submit(self, values):
        body = _modal_body()
        body["view"]["state"]["values"].update(values)
        with (
            patch.dict(sys.modules, {"db": self.db}),
            patch.object(schedule_validation, "pytz", _real_pytz),
        ):
            self.handler(MagicMock(), body, self.client)
        return self.db.create_standup_schedule.call_args

    def test_standup_time_block_sets_schedule_time(self):
        call = self._submit({"standup_time": {"standup_time": {"selected_option": {"value": "16:45"}}}})
        assert call.kwargs["schedule_time"] == "16:45"

    def test_explicit_report_time_is_persisted(self):
        call = self._submit(
            {
                "standup_time": {"standup_time": {"selected_option": {"value": "16:45"}}},
                "report_time": {"report_time": {"selected_option": {"value": "18:00"}}},
            }
        )
        assert call.kwargs["report_time"] == "18:00"

    def test_legacy_modal_without_standup_time_still_sets_the_dm_time(self):
        """A modal opened before this change submits the DM time as report_time."""
        call = self._submit({"report_time": {"report_time": {"selected_option": {"value": "16:45"}}}})
        assert call.kwargs["schedule_time"] == "16:45"

    def test_invalid_report_time_is_rejected(self):
        self._submit(
            {
                "standup_time": {"standup_time": {"selected_option": {"value": "16:45"}}},
                "report_time": {"report_time": {"selected_option": {"value": "6pm"}}},
            }
        )
        self.db.create_standup_schedule.assert_not_called()
