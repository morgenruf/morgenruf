"""Tests for dashboard.py — Flask blueprint API endpoints."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# schedule_validation (imported by dashboard) needs the real pytz to tell a
# valid timezone from a typo. Drop a MagicMock left behind by another module.
if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]

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


def _overview(members=None, schedules=None, **totals):
    """A get_participation_overview payload, shaped like db.compute_participation returns."""
    base = {
        "days": 7,
        "expected": 0,
        "completed": 0,
        "missed": 0,
        "completion_rate": 0,
        "responses": 0,
        "responding_members": 0,
        "total_members": 0,
        "enrolled_members": 0,
        "unenrolled_members": 0,
        "on_vacation_members": 0,
        "schedules": schedules or [],
        "members": members or [],
    }
    base.update(totals)
    return base


class TestApiReports:
    def test_returns_200_with_expected_keys(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_overview.return_value = _overview()
        resp = authed_client.get("/dashboard/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "standups" in data
        assert "participation" in data
        assert "total_days" in data
        assert "summary" in data
        assert "schedules" in data

    def test_filters_by_user_id(self, authed_client):
        _db_mock.get_standups.return_value = [
            {"user_id": "U1", "yesterday": "a", "today": "b"},
            {"user_id": "U2", "yesterday": "c", "today": "d"},
        ]
        _db_mock.get_participation_overview.return_value = _overview()
        resp = authed_client.get("/dashboard/api/reports?user_id=U1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["standups"]  # the real path ran, not the error fallback
        assert all(s["user_id"] == "U1" for s in data["standups"])

    def test_db_error_returns_empty_fallback(self, authed_client):
        _db_mock.get_standups.side_effect = Exception("DB error")
        resp = authed_client.get("/dashboard/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["standups"] == []
        assert data["summary"]["expected"] == 0
        _db_mock.get_standups.side_effect = None  # reset

    def test_date_from_param_accepted(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_overview.return_value = _overview()
        resp = authed_client.get("/dashboard/api/reports?date_from=2024-01-01")
        assert resp.status_code == 200

    def test_member_total_is_what_was_expected_not_the_window_length(self, authed_client):
        """A mon/wed/fri member expected 3 standups reports 3, not the 7 day window."""
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_overview.return_value = _overview(
            members=[
                {
                    "user_id": "U4",
                    "real_name": "Dee",
                    "enrolled": True,
                    "on_vacation": False,
                    "expected": 3,
                    "completed": 2,
                    "missed": 1,
                    "responses": 2,
                    "completion_rate": 67,
                    "last_standup": None,
                    "days_with_blockers": 0,
                    "schedules": ["Tri"],
                }
            ],
            expected=3,
            completed=2,
            missed=1,
            completion_rate=67,
            enrolled_members=1,
            total_members=1,
        )
        resp = authed_client.get("/dashboard/api/reports")
        row = resp.get_json()["participation"][0]
        assert row["total"] == 3
        assert row["expected"] == 3
        assert row["completion_rate"] == 67
        assert row["stars"] == 3  # 67 percent of 5 stars, rounded

    def test_unenrolled_member_is_returned_flagged_with_zero_stars(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_overview.return_value = _overview(
            members=[
                {
                    "user_id": "U6",
                    "real_name": "Fin",
                    "enrolled": False,
                    "on_vacation": False,
                    "expected": 0,
                    "completed": 0,
                    "missed": 0,
                    "responses": 3,
                    "completion_rate": 0,
                    "last_standup": None,
                    "days_with_blockers": 0,
                    "schedules": [],
                }
            ],
            total_members=1,
            unenrolled_members=1,
        )
        resp = authed_client.get("/dashboard/api/reports")
        data = resp.get_json()
        row = data["participation"][0]
        assert row["enrolled"] is False
        assert row["expected"] == 0
        assert row["responses"] == 3
        assert row["stars"] == 0
        assert data["summary"]["unenrolled_members"] == 1

    def test_summary_carries_the_denominator(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_overview.return_value = _overview(
            expected=180,
            completed=156,
            missed=24,
            completion_rate=87,
            total_members=42,
            enrolled_members=24,
            unenrolled_members=18,
        )
        summary = authed_client.get("/dashboard/api/reports").get_json()["summary"]
        assert summary["completion_rate"] == 87
        assert summary["expected"] == 180
        assert summary["enrolled_members"] == 24
        assert summary["total_members"] == 42
        assert summary["unenrolled_members"] == 18


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

    def test_passes_through_the_enrolment_denominator(self, authed_client):
        _db_mock.get_dashboard_stats.return_value = {
            "completion_rate": 87,
            "active_members": 24,
            "total_responses": 156,
            "responses_this_week": 156,
            "total_members": 42,
            "enrolled_members": 24,
            "unenrolled_members": 18,
            "expected_responses": 180,
            "completed_responses": 156,
            "schedules": [{"schedule_id": 1, "name": "Morning", "completion_rate": 100}],
        }
        data = authed_client.get("/dashboard/api/stats").get_json()
        assert data["completion_rate"] == 87
        assert data["enrolled_members"] == 24
        assert data["total_members"] == 42
        assert data["expected_responses"] == 180
        assert data["schedules"][0]["name"] == "Morning"

    def test_error_fallback_still_carries_the_new_keys(self, authed_client):
        _db_mock.get_dashboard_stats.side_effect = Exception("DB error")
        data = authed_client.get("/dashboard/api/stats").get_json()
        _db_mock.get_dashboard_stats.side_effect = None
        assert data["completion_rate"] == 0
        assert data["enrolled_members"] == 0
        assert data["expected_responses"] == 0
        assert data["schedules"] == []


class TestApiAnalytics:
    """/dashboard/api/analytics and its per-schedule companion."""

    @staticmethod
    def _unenrolled_row():
        return {
            "user_id": "U6",
            "real_name": "Fin",
            "enrolled": False,
            "on_vacation": False,
            "expected": 0,
            "completed": 0,
            "missed": 0,
            "responses": 3,
            "completion_rate": 0,
            "last_standup": None,
            "days_with_blockers": 0,
            "schedules": [],
        }

    def test_rows_keep_the_enrolment_flags(self, authed_client):
        _db_mock.get_participation_overview.return_value = _overview(members=[self._unenrolled_row()])
        payload = authed_client.get("/dashboard/api/analytics?days=7").get_json()
        rows = payload["members"]
        assert rows[0]["enrolled"] is False
        assert rows[0]["expected"] == 0
        assert rows[0]["responses"] == 3

    def test_response_carries_the_workspace_totals(self, authed_client):
        """#85: the page must not have to compute the headline itself.

        It used to average the per-member ratios, which is a different statistic
        from the server's completed over expected, so the Standups card and the
        Analytics card disagreed about the same window.
        """
        _db_mock.get_participation_overview.return_value = _overview(
            members=[self._unenrolled_row()],
            expected=15,
            completed=7,
            completion_rate=47,
            enrolled_members=6,
            unenrolled_members=1,
        )
        payload = authed_client.get("/dashboard/api/analytics?days=7").get_json()
        assert payload["completion_rate"] == 47
        assert payload["expected"] == 15
        assert payload["completed"] == 7
        assert payload["enrolled_members"] == 6
        assert payload["unenrolled_members"] == 1

    def test_failure_returns_a_usable_shape(self, authed_client):
        _db_mock.get_participation_overview.side_effect = Exception("db down")
        payload = authed_client.get("/dashboard/api/analytics?days=7").get_json()
        _db_mock.get_participation_overview.side_effect = None
        assert payload["members"] == []
        assert payload["schedules"] == []

    def test_schedule_breakdown_endpoint(self, authed_client):
        _db_mock.get_participation_overview.return_value = _overview(
            schedules=[
                {
                    "schedule_id": 1,
                    "name": "Morning",
                    "occurrence_days": 5,
                    "participants": 3,
                    "expected": 15,
                    "completed": 9,
                    "missed": 6,
                    "completion_rate": 60,
                }
            ],
            expected=15,
            completed=9,
            completion_rate=60,
        )
        data = authed_client.get("/dashboard/api/analytics/schedules?days=7").get_json()
        assert data["schedules"][0]["completion_rate"] == 60
        assert data["summary"]["expected"] == 15

    def test_schedule_breakdown_requires_login(self, client):
        assert client.get("/dashboard/api/analytics/schedules").status_code == 401


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


# Timezone and time validation on the schedule APIs (#67)


def _schedule_row(**overrides):
    row = {
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
    row.update(overrides)
    return row


class TestScheduleTimingValidation:
    """A typo in the timezone used to save fine and then never fire."""

    def test_create_standup_with_bad_timezone_returns_400(self, authed_client):
        _db_mock.create_standup_schedule.reset_mock()
        resp = authed_client.post(
            "/dashboard/api/standups",
            json={"name": "New", "channel_id": "C2", "schedule_tz": "Asia/Kolkatta"},
        )
        assert resp.status_code == 400
        assert "Asia/Kolkatta" in resp.get_json()["error"]
        _db_mock.create_standup_schedule.assert_not_called()

    def test_create_standup_with_valid_timezone_still_works(self, authed_client):
        _db_mock.create_standup_schedule.reset_mock()
        _db_mock.create_standup_schedule.return_value = _schedule_row(id=2, schedule_tz="Asia/Kolkata")
        resp = authed_client.post(
            "/dashboard/api/standups",
            json={"name": "New", "channel_id": "C2", "schedule_tz": "Asia/Kolkata"},
        )
        assert resp.status_code == 201

    def test_update_standup_with_bad_timezone_returns_400(self, authed_client):
        _db_mock.update_standup_schedule.reset_mock()
        resp = authed_client.put("/dashboard/api/standups/1", json={"schedule_tz": "GMT+5:30"})
        assert resp.status_code == 400
        _db_mock.update_standup_schedule.assert_not_called()

    def test_update_standup_with_bad_time_returns_400(self, authed_client):
        _db_mock.update_standup_schedule.reset_mock()
        resp = authed_client.put("/dashboard/api/standups/1", json={"schedule_time": "9am"})
        assert resp.status_code == 400
        assert "09:30" in resp.get_json()["error"]
        _db_mock.update_standup_schedule.assert_not_called()

    def test_update_standup_without_timing_fields_is_untouched(self, authed_client):
        _db_mock.update_standup_schedule.reset_mock()
        _db_mock.update_standup_schedule.return_value = _schedule_row()
        resp = authed_client.put("/dashboard/api/standups/1", json={"name": "Renamed"})
        assert resp.status_code == 200
        _db_mock.update_standup_schedule.assert_called_once()

    def test_create_schedule_with_bad_timezone_returns_400(self, authed_client):
        _db_mock.create_standup_schedule.reset_mock()
        resp = authed_client.post("/dashboard/api/schedules", json={"name": "Daily", "schedule_tz": "IST"})
        assert resp.status_code == 400
        _db_mock.create_standup_schedule.assert_not_called()

    def test_update_schedule_with_bad_timezone_returns_400(self, authed_client):
        _db_mock.update_standup_schedule.reset_mock()
        resp = authed_client.put("/dashboard/api/schedules/1", json={"schedule_tz": "Mars/Olympus"})
        assert resp.status_code == 400
        _db_mock.update_standup_schedule.assert_not_called()


class TestRegistrationErrorSurfacing:
    """An Active schedule the scheduler refuses must not look healthy (#67)."""

    def test_standup_list_flags_a_schedule_that_can_never_fire(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [_schedule_row(schedule_tz="Asia/Kolkatta")]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.status_code == 200
        assert "Asia/Kolkatta" in resp.get_json()[0]["registration_error"]

    def test_healthy_schedule_has_no_error(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [_schedule_row(schedule_tz="Asia/Kolkata")]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.get_json()[0]["registration_error"] is None

    def test_inactive_schedule_is_not_flagged(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [_schedule_row(schedule_tz="Asia/Kolkatta", active=False)]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.get_json()[0]["registration_error"] is None

    def test_schedules_list_flags_it_too(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [_schedule_row(schedule_time="25:00")]
        resp = authed_client.get("/dashboard/api/schedules")
        assert resp.status_code == 200
        assert resp.get_json()[0]["registration_error"] is not None


class TestApiAnalyticsGridPayload:
    """The analytics endpoint builds its payload from an explicit key list.

    Anything added to compute_participation has to be named there too. It was
    not, so the grid received no dates, drew no columns, and the page said
    "Nothing to show for these filters" while the summary above it correctly
    reported 24 enrolled members. Nothing in the unit tests noticed, because
    both layers were individually right.
    """

    def _overview_with_grid(self):
        return _overview(
            members=[
                {
                    "user_id": "U1",
                    "real_name": "Ada",
                    "enrolled": True,
                    "expected": 2,
                    "completed": 1,
                    "responses": 1,
                    "days": [
                        {"date": "2026-08-30", "expected": 1, "completed": 1, "blocked": False},
                        {"date": "2026-08-31", "expected": 1, "completed": 0, "blocked": False},
                    ],
                }
            ],
            schedules=[{"schedule_id": 1, "name": "Morning", "series": [100, 0]}],
            window_days=["2026-08-30", "2026-08-31"],
        )

    def test_the_window_reaches_the_client(self, authed_client):
        _db_mock.get_participation_overview.return_value = self._overview_with_grid()
        data = authed_client.get("/dashboard/api/analytics?days=7").get_json()
        assert data["window_days"] == ["2026-08-30", "2026-08-31"]

    def test_each_member_keeps_its_per_day_grid(self, authed_client):
        _db_mock.get_participation_overview.return_value = self._overview_with_grid()
        data = authed_client.get("/dashboard/api/analytics?days=7").get_json()
        days = data["members"][0]["days"]
        assert [d["date"] for d in days] == data["window_days"]
        assert days[0]["completed"] == 1 and days[1]["completed"] == 0

    def test_schedule_series_reaches_the_client(self, authed_client):
        _db_mock.get_participation_overview.return_value = self._overview_with_grid()
        data = authed_client.get("/dashboard/api/analytics?days=7").get_json()
        assert data["schedules"][0]["series"] == [100, 0]

    def test_an_overview_without_a_window_does_not_break_the_endpoint(self, authed_client):
        """Older callers and the error path return no window_days."""
        _db_mock.get_participation_overview.return_value = _overview()
        resp = authed_client.get("/dashboard/api/analytics?days=7")
        assert resp.status_code == 200
        assert resp.get_json()["window_days"] == []

    def test_schedule_ids_still_reach_the_client(self, authed_client):
        """Guards the fix that made the standup filter work at all."""
        _db_mock.get_participation_overview.return_value = _overview(
            members=[{"user_id": "U1", "real_name": "Ada", "schedule_ids": [3, 7], "days": []}]
        )
        data = authed_client.get("/dashboard/api/analytics?days=7").get_json()
        assert data["members"][0]["schedule_ids"] == [3, 7]


class TestNextRunIsSurfaced:
    """#119 — a standup that never fires was indistinguishable from one that
    does. The next fire time follows from the schedule's own config, so it is
    correct in the dashboard's forked worker as well as in the scheduler."""

    def test_healthy_schedule_reports_its_next_run(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [
            _schedule_row(schedule_tz="Asia/Kolkata", schedule_time="16:45")
        ]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.status_code == 200
        assert resp.get_json()[0]["next_run"], "a firing standup must say when it next runs"

    def test_unusable_schedule_reports_no_next_run(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [_schedule_row(schedule_tz="Asia/Kolkatta")]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.get_json()[0]["next_run"] == ""

    def test_inactive_schedule_reports_no_next_run(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [_schedule_row(schedule_tz="Asia/Kolkata", active=False)]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.get_json()[0]["next_run"] == ""
