"""Exercise every browser operation through its real Flask/Marshmallow boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.browser_fixtures import create_test_app

APP = Path(__file__).resolve().parents[1]


@pytest.fixture
def browser(monkeypatch):
    app = create_test_app(monkeypatch)
    client = app.test_client()
    token = client.post("/__test__/session?role=admin").json["csrf_token"]
    return app, client, {"X-CSRF-Token": token}


def assert_contract(app, response, method, path):
    endpoint, _ = app.url_map.bind("localhost").match(path, method=method)
    view = app.view_functions[endpoint]
    contract = view._apidoc["response"]["responses"][response.status_code][0]["schema"]
    if response.mimetype == "text/csv":
        assert response.data.startswith(b"standup_date,user_id,")
        return
    assert response.is_json, response.data
    contract.load(response.json)


GET_PATHS = [
    "/dashboard/api/me",
    "/dashboard/api/standups",
    "/dashboard/api/members",
    "/dashboard/api/channels",
    "/dashboard/api/stats",
    "/dashboard/api/reports",
    "/dashboard/api/webhooks",
    "/dashboard/api/webhooks/events",
    "/dashboard/api/webhooks/1/deliveries",
    "/dashboard/api/analytics",
    "/dashboard/api/export/csv",
    "/dashboard/api/templates",
    "/dashboard/api/rules",
    "/dashboard/api/mcp/keys",
    "/dashboard/api/modules",
    "/dashboard/api/kudos",
    "/dashboard/api/kudos/leaderboard",
    "/dashboard/api/kudos/givers",
    "/dashboard/api/kudos/config",
    "/dashboard/api/connect/programs",
    "/dashboard/api/connect/programs/1/rounds",
    "/dashboard/api/connect/rounds/1/matches",
    "/dashboard/api/connect/programs/1/members",
    "/dashboard/api/connect/zoom",
    "/dashboard/api/connect/programs/1/participation",
    "/dashboard/api/insights",
    "/dashboard/api/today",
    "/api/public/feed/public-browser-feed",
]


@pytest.mark.parametrize("path", GET_PATHS)
def test_every_read_serializes_a_realistic_response(browser, path):
    app, client, _ = browser
    response = client.get(path)
    assert response.status_code == 200, response.data
    assert_contract(app, response, "GET", path)
    assert response.headers["Cache-Control"] == "no-store"


MUTATIONS = [
    ("POST", "/dashboard/api/standups", {"name": "New daily", "channel_id": "C_ENGINEERING"}),
    ("PUT", "/dashboard/api/standups/1", {"name": "Updated daily", "reminder_minutes": -1}),
    ("DELETE", "/dashboard/api/standups/1", None),
    ("PUT", "/dashboard/api/members/U_MEMBER/role", {"role": "admin"}),
    ("PUT", "/dashboard/api/members/U_MEMBER/modules/standup", None),
    ("DELETE", "/dashboard/api/members/U_LEAD/modules/standup", None),
    ("POST", "/dashboard/api/members/invite", {"user_id": "U_MEMBER"}),
    ("POST", "/dashboard/api/webhooks", {"url": "https://hooks.example.test/new", "events": ["standup.completed"]}),
    ("PATCH", "/dashboard/api/webhooks/1", {"events": ["blocker.detected"]}),
    ("POST", "/dashboard/api/webhooks/1/rotate", None),
    ("POST", "/dashboard/api/webhooks/1/test", None),
    ("DELETE", "/dashboard/api/webhooks/1", None),
    (
        "POST",
        "/dashboard/api/rules",
        {"name": "Notify", "trigger": "blocker_detected", "action": "dm_user", "action_target": "U_LEAD"},
    ),
    ("DELETE", "/dashboard/api/rules/1", None),
    ("POST", "/dashboard/api/feed-token", None),
    ("DELETE", "/dashboard/api/feed-token", None),
    ("POST", "/dashboard/api/mcp/keys", {"name": "Browser assistant"}),
    ("DELETE", "/dashboard/api/mcp/keys/1", None),
    ("POST", "/dashboard/api/modules/connect", {"enabled": False}),
    ("POST", "/dashboard/api/kudos/config", {"emoji": "☕", "daily_allowance": 7}),
    ("POST", "/dashboard/api/connect/programs", {"channel_id": "C_ENGINEERING", "name": "Design chats"}),
    ("POST", "/dashboard/api/connect/programs/1", {"enabled": False}),
    ("DELETE", "/dashboard/api/connect/programs/1", None),
    ("POST", "/dashboard/api/connect/programs/1/run", None),
    ("POST", "/dashboard/api/connect/programs/1/members/U_MEMBER", {"state": "snoozed", "weeks": 2}),
    ("POST", "/dashboard/api/logout", None),
]


@pytest.mark.parametrize("method,path,body", MUTATIONS)
def test_every_mutation_serializes_its_contract(browser, method, path, body):
    app, client, headers = browser
    response = client.open(path, method=method, json=body, headers=headers)
    assert response.status_code in (200, 201), response.data
    assert_contract(app, response, method, path)


def test_contract_cases_cover_every_browser_operation(browser):
    app, _, _ = browser
    expected = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith(("/dashboard/api/", "/api/public/"))
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    actual = set()
    for method, path in [("GET", path) for path in GET_PATHS] + [(method, path) for method, path, _ in MUTATIONS]:
        rule, _ = app.url_map.bind("localhost").match(path, method=method, return_rule=True)
        actual.add((rule.rule, method))
    assert actual == expected


def test_csrf_authentication_and_logout(browser):
    app, client, headers = browser
    state = app.extensions["browser_test_data"]
    before = len(state.schedules)
    response = client.post("/dashboard/api/standups", json={"name": "Must not save"})
    assert response.status_code == 403
    assert len(state.schedules) == before
    assert response.json["error"] == "Invalid or missing CSRF token"
    assert client.post("/dashboard/api/logout", headers=headers).status_code == 200
    assert client.get("/dashboard/api/me").status_code == 401
    assert client.post("/dashboard/api/standups", json={}).status_code == 401


def test_feature_admin_can_save_standups_but_not_workspace_secrets(browser):
    _, client, _ = browser
    token = client.post("/__test__/session?role=standup-admin").json["csrf_token"]
    headers = {"X-CSRF-Token": token}
    assert client.put("/dashboard/api/standups/1", json={"name": "Lead update"}, headers=headers).status_code == 200
    assert client.post("/dashboard/api/mcp/keys", json={"name": "Forbidden"}, headers=headers).status_code == 403
    assert client.post("/dashboard/api/feed-token", headers=headers).status_code == 403


def test_input_errors_are_json_before_side_effects(browser):
    app, client, headers = browser
    response = client.post(
        "/dashboard/api/connect/programs", json={"channel_id": "C_GENERAL", "hour": "noon"}, headers=headers
    )
    assert response.status_code == 400 and response.json["error"]
    assert response.json["details"] == {"hour": ["Not a valid integer."]}
    assert len(app.extensions["browser_test_data"].programs) == 1
    assert client.get("/dashboard/api/analytics?days=wrong").status_code == 400
    assert client.post(
        "/dashboard/api/standups", data="{broken", content_type="application/json", headers=headers
    ).is_json


def test_validation_details_use_field_paths_for_query_and_nested_body_errors(browser):
    _, client, headers = browser
    response = client.get("/dashboard/api/analytics?days=wrong")
    assert response.status_code == 400
    assert response.json["details"] == {"days": ["Not a valid integer."]}
    response = client.post("/dashboard/api/standups", json={"questions": ["A valid question", 42]}, headers=headers)
    assert response.status_code == 400
    assert response.json["details"] == {"questions.1": ["Not a valid string."]}


def test_schema_level_validation_errors_map_to_the_form_root():
    from src.core.api import _validation_details

    assert _validation_details({"json": {"_schema": ["Expected an object."]}}) == {
        "root.server": ["Expected an object."]
    }


def test_all_supported_settings_survive_create_and_reload(browser):
    _, client, headers = browser
    payload = {
        "name": "Full settings",
        "channel_id": "C_ENGINEERING",
        "report_channel": "C_GENERAL",
        "report_time": "16:00",
        "digest_email": "lead@example.test",
        "digest_enabled": True,
        "nudge_missing": True,
        "nudge_minutes_before": 35,
        "group_by": "question",
        "ai_summary_enabled": True,
        "ai_provider": "anthropic",
        "reminder_minutes": -1,
    }
    response = client.post("/dashboard/api/standups", json=payload, headers=headers)
    assert response.status_code == 201
    stored = next(row for row in client.get("/dashboard/api/standups").json if row["id"] == response.json["id"])
    for key, value in payload.items():
        assert stored[key] == value, key
    program = {
        "suggest_times": False,
        "use_icebreaker": False,
        "post_stats": True,
        "group_size": 3,
        "strict_group_size": True,
        "intro_tone": "remote",
        "video_mode": "zoom",
        "next_round_date": "2027-02-02",
    }
    response = client.post("/dashboard/api/connect/programs/1", json=program, headers=headers)
    assert response.status_code == 200
    for key, value in program.items():
        assert response.json[key] == value, key


def test_public_feed_is_capability_guarded_and_allowlisted(browser):
    _, client, _ = browser
    client.post("/dashboard/api/logout", headers={"X-CSRF-Token": client.get("/dashboard/api/me").json["csrf_token"]})
    response = client.get("/api/public/feed/public-browser-feed")
    assert response.status_code == 200
    assert set(response.json) == {"title", "date", "standups"}
    assert "manager@example.test" not in response.text and "must-never-be-public" not in response.text
    assert client.get("/api/public/feed/bad-token").status_code == 404


def test_legacy_token_redirect_never_renders_or_leaks_the_token(browser):
    _, client, _ = browser
    link = client.get("/__test__/login-link").json["url"]
    response = client.get(link)
    assert response.status_code == 303
    assert response.location == "/dashboard/"
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/dashboard?t=invalid").location == "/dashboard/login?error=invalid-link"
    assert client.get("/dashboard/").status_code == 404  # owned by the frontend service


def test_oauth_and_zoom_result_routes_redirect_to_react(browser):
    _, client, _ = browser
    assert client.get("/oauth/callback?state=invalid").location == "/auth/result?status=invalid"
    assert client.get("/oauth/callback?error=access_denied").location == "/auth/result?status=denied"
    assert client.get("/connect/zoom/start?t=invalid").location == "/connect/zoom/result?status=expired"
    assert client.get("/connect/zoom/callback?error=access_denied").location == "/connect/zoom/result?status=denied"


def test_offline_export_has_no_services_and_matches_checked_artifact(tmp_path):
    script = """
import json, socket
calls = []
def reject(*args, **kwargs):
    calls.append(args)
    raise AssertionError("schema export attempted network access")
socket.socket.connect = reject
from src.openapi import specification
spec = specification()
assert not calls
from src.core import db
assert db._pool is None
assert "src.main" not in __import__("sys").modules
print(json.dumps(spec, sort_keys=True))
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(APP),
        "DATABASE_URL": "postgresql://unavailable.invalid/database",
        "REDIS_URL": "redis://unavailable.invalid",
        "MORGENRUF_MODULES": "standup",
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=APP, env=env, capture_output=True, text=True, check=True, timeout=20
    )
    exported = json.loads(result.stdout)
    assert exported == json.loads((APP / "openapi.json").read_text())
    operations = [
        operation
        for path in exported["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operations) == 54
    assert len({operation["operationId"] for operation in operations}) == len(operations)
    assert all(operation["responses"] for operation in operations)


def test_connect_programmes_carry_the_round_the_job_will_run(browser):
    """The dashboard names the same day as the scheduler: the programme's
    weekday (Friday here), and no earlier than a pinned date."""
    from datetime import date

    _, client, headers = browser
    program = client.get("/dashboard/api/connect/programs").json[0]
    upcoming = date.fromisoformat(program["upcoming_round"])

    assert upcoming.weekday() == program["day_of_week"]
    assert upcoming >= date.fromisoformat(program["next_round_date"])

    client.post("/dashboard/api/connect/programs/1", json={"enabled": False}, headers=headers)
    assert client.get("/dashboard/api/connect/programs").json[0]["upcoming_round"] is None
