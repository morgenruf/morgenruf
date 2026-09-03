"""#117 — the channel summary must be reachable from the shipped UI.

`post_summary` defaulted to FALSE and was exposed in no interface, so every
schedule in every install had the daily roll-up permanently off and no way to
turn it on short of a hand-written API call.
"""

from __future__ import annotations

import os
import re
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

import blocks as blocks_mod  # noqa: E402
import handlers  # noqa: E402
import schedule_validation  # noqa: E402

if _prior_session_store is not None:
    sys.modules["session_store"] = _prior_session_store
else:
    sys.modules.pop("session_store", None)

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "../src/templates/dashboard.html")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "../migrations")


def _find_block(blocks, block_id):
    for block in blocks:
        if block.get("block_id") == block_id:
            return block
    return None


def _modal(cfg=None):
    return blocks_mod.create_standup_modal(cfg, bot_channels=[{"id": "C1", "name": "general"}])["blocks"]


class TestSlackModalExposesTheToggle:
    def test_modal_has_a_post_summary_block(self):
        assert _find_block(_modal(), "post_summary") is not None

    def test_new_schedule_has_the_summary_switched_on(self):
        element = _find_block(_modal(), "post_summary")["element"]
        assert element.get("initial_options"), "a new standup should post its summary by default"

    def test_a_schedule_with_the_summary_off_renders_unchecked(self):
        element = _find_block(_modal({"post_summary": False, "standup_id": "7"}), "post_summary")["element"]
        assert not element.get("initial_options")


class TestModalSubmissionPersistsTheToggle:
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
        self.db.create_standup_schedule.return_value = None
        self.client = MagicMock()
        self.client.users_list.return_value = {
            "members": [{"id": "U1", "deleted": False, "is_bot": False}],
            "response_metadata": {},
        }

    def _submit(self, post_summary_opts):
        body = {
            "user": {"id": "U1"},
            "team": {"id": "T1"},
            "view": {
                "private_metadata": "",
                "state": {
                    "values": {
                        "standup_channel": {"standup_channel": {"selected_channel": "C1"}},
                        "questions": {"questions": {"value": "What did you do?"}},
                        "standup_time": {"standup_time": {"selected_option": {"value": "09:00"}}},
                        "timezone": {"timezone": {"selected_option": {"value": "UTC"}}},
                        "reminder": {"reminder": {"selected_option": {"value": "0"}}},
                        "members": {"members": {"selected_users": ["U1"]}},
                        "days": {"days": {"selected_options": [{"value": "mon"}]}},
                        "standup_name": {"standup_name": {"value": "Daily Standup"}},
                        "post_summary": {"post_summary": {"selected_options": post_summary_opts}},
                    }
                },
            },
        }
        with (
            patch.dict(sys.modules, {"db": self.db}),
            patch.object(schedule_validation, "pytz", _real_pytz),
        ):
            self.handler(MagicMock(), body, self.client)
        return self.db.create_standup_schedule.call_args

    def test_checked_saves_true(self):
        assert self._submit([{"value": "post_summary"}]).kwargs["post_summary"] is True

    def test_unchecked_saves_false(self):
        assert self._submit([]).kwargs["post_summary"] is False


class TestDashboardExposesTheToggle:
    def test_template_has_a_post_summary_control(self):
        with open(TEMPLATE_PATH, encoding="utf-8") as fh:
            markup = fh.read()
        assert "post_summary" in markup, "the dashboard standup editor must expose the summary toggle"


class TestNewSchedulesDefaultToPosting:
    def test_api_create_defaults_to_true(self):
        import dashboard

        db = MagicMock()
        db.create_standup_schedule.return_value = {"id": 1}
        with patch.dict(sys.modules, {"db": db}):
            dashboard.db = db
        # The payload a client sends without the key must still post its summary.
        assert dashboard._post_summary_default({}) is True
        assert dashboard._post_summary_default({"post_summary": False}) is False

    def test_a_migration_sets_the_column_default_back_to_true(self):
        pattern = re.compile(r"post_summary\s+SET\s+DEFAULT\s+TRUE", re.IGNORECASE)
        for name in os.listdir(MIGRATIONS_DIR):
            if not name.endswith(".sql"):
                continue
            with open(os.path.join(MIGRATIONS_DIR, name), encoding="utf-8") as fh:
                if pattern.search(fh.read()):
                    return
        raise AssertionError("no migration restores the post_summary column default to TRUE")

    def test_the_migration_leaves_existing_rows_alone(self):
        """Flipping 19 live schedules on would post to their channels unannounced."""
        bad = re.compile(r"UPDATE\s+standup_schedules\s+SET\s+post_summary\s*=\s*TRUE", re.IGNORECASE)
        for name in os.listdir(MIGRATIONS_DIR):
            if not name.endswith(".sql"):
                continue
            with open(os.path.join(MIGRATIONS_DIR, name), encoding="utf-8") as fh:
                assert not bad.search(fh.read()), f"{name} backfills post_summary on existing rows"
