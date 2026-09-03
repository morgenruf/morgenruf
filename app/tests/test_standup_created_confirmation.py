"""#119 — creating a standup must say what was saved and when it will run.

The success path used to end with a silent App Home refresh. A creator who left
themselves off the participant list got no DM at the trigger time and no channel
message until somebody else answered, so a working standup and a broken one
looked identical.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("requests", MagicMock())

if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]
import pytz as _real_pytz  # noqa: E402

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


class TestCreatorIsToldWhatWasSaved:
    def setup_method(self):
        captured: dict = {}

        def view(name):
            def decorator(fn):
                captured[name] = fn
                return fn

            return decorator

        app = MagicMock()
        app.view.side_effect = view
        handlers.register_handlers(app)
        self.handler = captured["create_standup_modal"]

        self.db = MagicMock()
        self.db.create_standup_schedule.return_value = {
            "id": 30,
            "team_id": "T1",
            "name": "Field Notes",
            "channel_id": "C1",
            "schedule_time": "16:45",
            "schedule_tz": "America/Chicago",
            "schedule_days": "mon,tue,wed,thu,fri",
            "participants": ["U2", "U3"],
            "active": True,
        }
        self.db.get_installation.return_value = None
        self.client = MagicMock()
        self.client.users_list.return_value = {
            "members": [
                {"id": "U1", "deleted": False, "is_bot": False},
                {"id": "U2", "deleted": False, "is_bot": False},
                {"id": "U3", "deleted": False, "is_bot": False},
            ],
            "response_metadata": {},
        }

    def _submit(self, members=("U2", "U3"), creator="U1"):
        body = {
            "user": {"id": creator},
            "team": {"id": "T1"},
            "view": {
                "private_metadata": "",
                "state": {
                    "values": {
                        "standup_channel": {"standup_channel": {"selected_channel": "C1"}},
                        "questions": {"questions": {"value": "What did you do?"}},
                        "standup_time": {"standup_time": {"selected_option": {"value": "16:45"}}},
                        "timezone": {"timezone": {"selected_option": {"value": "America/Chicago"}}},
                        "reminder": {"reminder": {"selected_option": {"value": "0"}}},
                        "members": {"members": {"selected_users": list(members)}},
                        "days": {"days": {"selected_options": [{"value": "mon"}]}},
                        "standup_name": {"standup_name": {"value": "Field Notes"}},
                    }
                },
            },
        }
        with (
            patch.dict(sys.modules, {"db": self.db}),
            patch.object(schedule_validation, "pytz", _real_pytz),
        ):
            self.handler(MagicMock(), body, self.client)
        return "\n".join(kwargs.get("text", "") for _, kwargs in self.client.chat_postMessage.call_args_list)

    def test_creator_gets_a_message(self):
        assert self._submit().strip(), "saving a standup must confirm to the creator"

    def test_confirmation_names_the_standup(self):
        assert "Field Notes" in self._submit()

    def test_confirmation_shows_the_time_and_timezone(self):
        text = self._submit()
        assert "16:45" in text
        assert "America/Chicago" in text

    def test_confirmation_shows_the_participant_count(self):
        assert "2" in self._submit()

    def test_creator_left_off_the_list_is_warned(self):
        text = self._submit(members=("U2", "U3"), creator="U1")
        assert "not on" in text.lower() or "won't get" in text.lower() or "will not get" in text.lower()

    def test_creator_on_the_list_is_not_warned(self):
        self.db.create_standup_schedule.return_value["participants"] = ["U1", "U2"]
        text = self._submit(members=("U1", "U2"), creator="U1")
        assert "not on" not in text.lower()

    def test_confirmation_explains_answers_reach_the_channel_via_the_dm(self):
        assert "dm" in self._submit().lower()


class TestAppHomeShowsNextRun:
    """#119 — the standup list must say when each one next fires."""

    def _text(self, standup):
        import blocks as blocks_mod

        view = blocks_mod.app_home_configure_view([standup], user_id="U1")
        return "\n".join(b.get("text", {}).get("text", "") for b in view["blocks"] if b.get("type") == "section")

    def test_next_run_is_rendered(self):
        text = self._text(
            {
                "id": 30,
                "name": "Field Notes",
                "channel_id": "C1",
                "schedule_time": "16:45",
                "schedule_tz": "America/Chicago",
                "schedule_days": "mon,tue,wed,thu,fri",
                "participants": ["U1"],
                "active": True,
                "next_run": "2026-09-04T16:45:00-05:00",
            }
        )
        assert "Next" in text
        assert "16:45" in text

    def test_no_next_run_renders_nothing_extra(self):
        text = self._text(
            {
                "id": 30,
                "name": "Field Notes",
                "channel_id": "C1",
                "schedule_time": "16:45",
                "schedule_tz": "America/Chicago",
                "participants": ["U1"],
                "active": True,
            }
        )
        assert "Next" not in text
