"""Workspace-level settings on the schedule form have to actually persist.

The form posts one payload that mixes per-schedule settings with
workspace-level ones. api_update_standup handed the whole lot to
update_standup_schedule, whose allowlist silently dropped every workspace
field: AI provider, the AI summary toggle, the Jira / GitHub / Linear
autolinks, the manager digest address and its toggle. The dashboard said
"saved", stored nothing, and the GET then returned hardcoded defaults, so
the form appeared to revert on reload.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]

for mod in ("psycopg2", "psycopg2.extras", "psycopg2.pool", "slack_sdk", "slack_bolt", "markupsafe"):
    sys.modules.setdefault(mod, MagicMock())

_prior_db = sys.modules.get("src.core.db")
_prior_oauth = sys.modules.get("src.core.oauth")
sys.modules["src.core.db"] = MagicMock()
sys.modules["src.core.oauth"] = MagicMock()

import src.core.dashboard as dashboard  # noqa: E402
from flask import Flask  # noqa: E402

if _prior_db is not None:
    sys.modules["src.core.db"] = _prior_db
else:
    sys.modules.pop("src.core.db", None)
if _prior_oauth is not None:
    sys.modules["src.core.oauth"] = _prior_oauth
else:
    sys.modules.pop("src.core.oauth", None)


SCHEDULE_ROW = {
    "id": 1,
    "team_id": "T123",
    "name": "Daily standup",
    "channel_id": "C1",
    "schedule_time": "09:30",
    "schedule_tz": "UTC",
    "schedule_days": "mon,tue",
    "questions": [],
    "participants": [],
    "active": True,
}


@pytest.fixture()
def authed(monkeypatch):
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.register_blueprint(dashboard.dashboard_bp)
    flask_app.register_blueprint(dashboard.browser_bp)

    store: dict = {}

    db = MagicMock()
    # Editing a schedule is admin-only.
    db.get_member_role.return_value = "admin"
    db.update_standup_schedule.return_value = dict(SCHEDULE_ROW)
    db.get_standup_schedules.return_value = [dict(SCHEDULE_ROW)]
    db.get_workspace_config.side_effect = lambda team_id: dict(store)

    def _upsert(team_id, **kwargs):
        store.update(kwargs)
        return dict(store)

    db.upsert_workspace_config.side_effect = _upsert
    monkeypatch.setattr(dashboard, "db", db)

    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["team_id"] = "T123"
        sess["user_id"] = "U456"
    return client, db, store


def _put(client, payload):
    base = {"name": "Daily standup", "schedule_time": "09:30", "schedule_tz": "UTC"}
    return client.put("/dashboard/api/standups/1", json={**base, **payload})


class TestWorkspaceSettingsPersist:
    def test_ai_provider_is_written_to_workspace_config(self, authed):
        client, db, store = authed
        assert _put(client, {"ai_provider": "anthropic"}).status_code == 200
        assert store["ai_provider"] == "anthropic"

    def test_autolink_settings_are_written(self, authed):
        client, db, store = authed
        _put(
            client,
            {
                "jira_base_url": "https://acme.atlassian.net",
                "github_repo": "acme/api",
                "linear_team": "ENG",
            },
        )
        assert store["jira_base_url"] == "https://acme.atlassian.net"
        assert store["github_repo"] == "acme/api"
        assert store["linear_team"] == "ENG"

    def test_manager_digest_settings_are_written(self, authed):
        client, db, store = authed
        _put(client, {"manager_email": "boss@acme.com", "manager_digest_enabled": True})
        assert store["manager_email"] == "boss@acme.com"
        assert store["manager_digest_enabled"] is True

    def test_ai_summary_toggle_is_written(self, authed):
        client, db, store = authed
        _put(client, {"ai_summary_enabled": True})
        assert store["ai_summary_enabled"] is True

    def test_edit_window_maps_to_hours(self, authed):
        client, db, store = authed
        _put(client, {"edit_window": "4h"})
        assert store["edit_window_hours"] == 4
        _put(client, {"edit_window": "none"})
        assert store["edit_window_hours"] is None

    def test_the_response_reflects_what_was_stored(self, authed):
        client, db, store = authed
        body = _put(client, {"ai_provider": "anthropic"}).get_json()
        assert body["ai_provider"] == "anthropic"

    def test_the_list_endpoint_reflects_what_was_stored(self, authed):
        client, db, store = authed
        _put(client, {"ai_provider": "anthropic", "github_repo": "acme/api"})
        row = client.get("/dashboard/api/standups").get_json()[0]
        assert row["ai_provider"] == "anthropic"
        assert row["github_repo"] == "acme/api"

    def test_a_toggle_only_update_touches_no_workspace_settings(self, authed):
        # The Active switch PUTs {active: false} alone. It must not write
        # workspace config, or it would overwrite settings with defaults.
        client, db, store = authed
        client.put("/dashboard/api/standups/1", json={"active": False})
        db.upsert_workspace_config.assert_not_called()

    def test_schedule_fields_still_go_to_the_schedule(self, authed):
        client, db, store = authed
        _put(client, {"report_channel": "C_MANAGERS"})
        kwargs = db.update_standup_schedule.call_args.kwargs
        assert kwargs["report_channel"] == "C_MANAGERS"
