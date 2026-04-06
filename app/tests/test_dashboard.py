"""Tests for dashboard.py — Flask blueprint API endpoints."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Stub heavy dependencies before importing dashboard
sys.modules.setdefault("psycopg2", MagicMock())
sys.modules.setdefault("psycopg2.extras", MagicMock())
sys.modules.setdefault("psycopg2.pool", MagicMock())
sys.modules.setdefault("slack_sdk", MagicMock())
sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("markupsafe", MagicMock())

# Stub db and oauth at the module level before dashboard imports them.
# Save any prior values so we can restore them after dashboard is imported
# (avoiding interference with test_oauth.py which tests the real oauth module).
_prior_db = sys.modules.get("db")
_prior_oauth = sys.modules.get("oauth")

_db_mock = MagicMock()
_oauth_mock = MagicMock()
sys.modules["db"] = _db_mock
sys.modules["oauth"] = _oauth_mock

import dashboard  # noqa: E402
from flask import Flask  # noqa: E402

# Restore so test_oauth.py (and others) get the real modules
if _prior_db is not None:
    sys.modules["db"] = _prior_db
else:
    sys.modules.pop("db", None)
if _prior_oauth is not None:
    sys.modules["oauth"] = _prior_oauth
else:
    sys.modules.pop("oauth", None)


@pytest.fixture()
def app():
    flask_app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "../src/templates"))
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.register_blueprint(dashboard.dashboard_bp)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def authed_client(client, app):
    """Return a test client with a session containing team_id and user_id."""
    with client.session_transaction() as sess:
        sess["team_id"] = "T123"
        sess["user_id"] = "U456"
    return client


# ---------------------------------------------------------------------------
# Auth / redirect behaviour
# ---------------------------------------------------------------------------


class TestAuthGuard:
    def test_api_members_unauthenticated_returns_401(self, client):
        resp = client.get("/dashboard/api/members")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "Unauthorized"

    def test_api_reports_unauthenticated_returns_401(self, client):
        resp = client.get("/dashboard/api/reports")
        assert resp.status_code == 401

    def test_api_standups_unauthenticated_returns_401(self, client):
        resp = client.get("/dashboard/api/standups")
        assert resp.status_code == 401

    def test_dashboard_page_unauthenticated_redirects(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code in (301, 302)

    def test_logout_clears_session_and_redirects(self, authed_client):
        resp = authed_client.get("/dashboard/logout")
        assert resp.status_code in (301, 302)


# ---------------------------------------------------------------------------
# /dashboard/api/members
# ---------------------------------------------------------------------------


class TestApiMembers:
    def test_returns_200_with_list(self, authed_client):
        _db_mock.get_installation.return_value = {"bot_token": "xoxb-test", "team_name": "Acme"}
        _db_mock.get_active_members.return_value = []

        slack_client_mock = MagicMock()
        slack_client_mock.users_list.return_value = {
            "members": [
                {
                    "id": "U1",
                    "name": "alice",
                    "deleted": False,
                    "is_bot": False,
                    "tz": "UTC",
                    "profile": {"real_name": "Alice", "display_name": "alice", "image_48": "", "email": "a@b.com"},
                }
            ]
        }

        slack_sdk_mod = MagicMock()
        slack_sdk_mod.WebClient.return_value = slack_client_mock
        with patch.dict(sys.modules, {"slack_sdk": slack_sdk_mod}):
            resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_returns_empty_list_when_no_bot_token(self, authed_client):
        _db_mock.get_installation.return_value = None
        resp = authed_client.get("/dashboard/api/members")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_falls_back_to_db_on_slack_error(self, authed_client):
        _db_mock.get_installation.return_value = {"bot_token": "xoxb-test", "team_name": "Acme"}
        _db_mock.get_active_members.return_value = [
            {"user_id": "U2", "real_name": "Bob", "email": "b@c.com", "tz": "UTC", "role": "member"}
        ]

        slack_sdk_mod = MagicMock()
        slack_sdk_mod.WebClient.side_effect = Exception("Slack down")
        with patch.dict(sys.modules, {"slack_sdk": slack_sdk_mod}):
            resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# /dashboard/api/reports
# ---------------------------------------------------------------------------


class TestApiReports:
    def test_returns_200_with_expected_keys(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_stats.return_value = []
        resp = authed_client.get("/dashboard/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "standups" in data
        assert "participation" in data
        assert "total_days" in data

    def test_filters_by_user_id(self, authed_client):
        _db_mock.get_standups.return_value = [
            {"user_id": "U1", "yesterday": "a", "today": "b"},
            {"user_id": "U2", "yesterday": "c", "today": "d"},
        ]
        _db_mock.get_participation_stats.return_value = []
        resp = authed_client.get("/dashboard/api/reports?user_id=U1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(s["user_id"] == "U1" for s in data["standups"])

    def test_db_error_returns_empty_fallback(self, authed_client):
        _db_mock.get_standups.side_effect = Exception("DB error")
        resp = authed_client.get("/dashboard/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["standups"] == []
        _db_mock.get_standups.side_effect = None  # reset

    def test_date_from_param_accepted(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_stats.return_value = []
        resp = authed_client.get("/dashboard/api/reports?date_from=2024-01-01")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /dashboard/api/standups
# ---------------------------------------------------------------------------


class TestApiStandups:
    def test_list_standups_returns_200(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [
            {
                "id": 1,
                "name": "Morning",
                "channel_id": "C1",
                "schedule_time": "09:00",
                "schedule_tz": "UTC",
                "schedule_days": "mon,tue,wed,thu,fri",
                "questions": [],
                "active": True,
                "participants": [],
                "reminder_minutes": 0,
            }
        ]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_create_standup_returns_201(self, authed_client):
        _db_mock.create_standup_schedule.return_value = {
            "id": 2,
            "name": "New",
            "channel_id": "C2",
            "schedule_time": "10:00",
            "schedule_tz": "UTC",
            "schedule_days": "mon,tue,wed,thu,fri",
            "questions": [],
            "active": True,
            "participants": [],
            "reminder_minutes": 0,
        }
        resp = authed_client.post(
            "/dashboard/api/standups",
            json={"name": "New", "channel_id": "C2", "schedule_time": "10:00"},
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# /dashboard/api/stats
# ---------------------------------------------------------------------------


class TestApiStats:
    def test_returns_200(self, authed_client):
        _db_mock.get_dashboard_stats.return_value = {
            "total_standups": 10,
            "active_members": 3,
            "response_rate": 0.8,
        }
        resp = authed_client.get("/dashboard/api/stats")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# _is_safe_webhook_url helper
# ---------------------------------------------------------------------------


class TestIsSafeWebhookUrl:
    def test_localhost_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("http://localhost/hook") is False

    def test_loopback_ip_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("https://127.0.0.1/hook") is False

    def test_private_ip_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("https://192.168.1.1/hook") is False

    def test_public_url_allowed(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("https://hooks.example.com/standup") is True

    def test_non_http_scheme_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("ftp://hooks.example.com/hook") is False

    def test_invalid_url_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("not-a-url") is False


# ---------------------------------------------------------------------------
# _schedule_to_standup normalisation helper
# ---------------------------------------------------------------------------


class TestScheduleToStandup:
    def test_minimal_row_fills_defaults(self):
        from dashboard import _schedule_to_standup

        row = {"id": 1}
        result = _schedule_to_standup(row)
        assert result["id"] == 1
        assert result["name"] == "Morning Standup"
        assert result["schedule_days"] == ["mon", "tue", "wed", "thu", "fri"]
        assert isinstance(result["questions"], list)
        assert isinstance(result["participants"], list)

    def test_json_string_questions_parsed(self):
        from dashboard import _schedule_to_standup

        row = {"id": 2, "questions": '["Q1","Q2"]', "participants": "[]"}
        result = _schedule_to_standup(row)
        assert result["questions"] == ["Q1", "Q2"]

    def test_schedule_days_split(self):
        from dashboard import _schedule_to_standup

        row = {"id": 3, "schedule_days": "mon,wed,fri"}
        result = _schedule_to_standup(row)
        assert result["schedule_days"] == ["mon", "wed", "fri"]
