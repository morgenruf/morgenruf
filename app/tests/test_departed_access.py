"""People who leave lose access: the dashboard session, installer admin
rights, and the MCP keys they created all stop working when they are
deactivated in Slack or the workspace removes the app."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import src.core.dashboard as dashboard
import src.core.db as db

from tests.browser_fixtures import create_test_app


def _cursor(*rows):
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = list(rows)
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def db_conn():
        yield conn

    return cur, db_conn


# The dashboard session.


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setattr(dashboard, "_ACTIVE_CHECK_SECONDS", 0)
    app = create_test_app(monkeypatch)
    return app, app.test_client(), app.extensions["browser_test_data"]


def _deactivate(state, user):
    next(m for m in state.members if m["user_id"] == user)["active"] = False


def test_an_active_member_keeps_their_session(browser):
    _, client, _ = browser
    client.post("/__test__/session?role=member")
    assert client.get("/dashboard/api/me").status_code == 200


def test_a_deactivated_member_is_signed_out(browser):
    _, client, state = browser
    client.post("/__test__/session?role=member")
    assert client.get("/dashboard/api/me").status_code == 200
    _deactivate(state, "U_MEMBER")
    assert client.get("/dashboard/api/me").status_code == 401
    # The session is gone, not just refused once.
    next(m for m in state.members if m["user_id"] == "U_MEMBER")["active"] = True
    assert client.get("/dashboard/api/me").status_code == 401


def test_a_deactivated_admin_cannot_use_admin_routes(browser):
    _, client, state = browser
    csrf = client.post("/__test__/session?role=admin").json["csrf_token"]
    _deactivate(state, "U_ADMIN")
    response = client.post("/dashboard/api/mcp/keys", json={"name": "x"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 401


def test_the_session_check_is_cached_briefly(monkeypatch):
    """One roster read a minute, not one per request."""
    app = create_test_app(monkeypatch)
    client = app.test_client()
    calls = []
    monkeypatch.setattr(dashboard.db, "session_member_active", lambda team, user: calls.append(user) or True)
    client.post("/__test__/session?role=member")
    for _ in range(3):
        assert client.get("/dashboard/api/me").status_code == 200
    assert calls == ["U_MEMBER"]


def test_sessions_expire_after_a_week_idle(monkeypatch):
    app = create_test_app(monkeypatch)
    assert app.permanent_session_lifetime == timedelta(days=7)


@pytest.mark.parametrize(
    ("row", "expected"),
    [((True, True), True), ((True, None), True), ((True, False), False), ((False, True), False), (None, False)],
)
def test_session_member_active(monkeypatch, row, expected):
    _, db_conn = _cursor(row)
    monkeypatch.setattr(db, "db_conn", db_conn)
    assert db.session_member_active("T1", "U1") is expected


# Installer admin.


def test_the_installer_is_admin_while_active(monkeypatch):
    _, db_conn = _cursor(("member", True), ("U1",))
    monkeypatch.setattr(db, "db_conn", db_conn)
    assert db.get_member_role("T1", "U1") == "admin"


def test_a_deactivated_installer_is_not_admin(monkeypatch):
    _, db_conn = _cursor(("member", False), ("U1",))
    monkeypatch.setattr(db, "db_conn", db_conn)
    assert db.get_member_role("T1", "U1") == "member"


def test_a_deactivated_admin_row_is_not_admin(monkeypatch):
    _, db_conn = _cursor(("admin", False))
    monkeypatch.setattr(db, "db_conn", db_conn)
    assert db.get_member_role("T1", "U1") == "member"


# MCP keys.


def test_a_new_key_records_who_made_it(monkeypatch):
    app = create_test_app(monkeypatch)
    client = app.test_client()
    made = []
    monkeypatch.setattr(
        dashboard.db, "generate_mcp_key", lambda team, name, created_by=None: made.append(created_by) or "k"
    )
    csrf = client.post("/__test__/session?role=admin").json["csrf_token"]
    assert client.post("/dashboard/api/mcp/keys", json={"name": "x"}, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert made == ["U_ADMIN"]


def test_generate_mcp_key_stores_the_creator(monkeypatch):
    cur, db_conn = _cursor()
    monkeypatch.setattr(db, "db_conn", db_conn)
    db.generate_mcp_key("T1", "n", created_by="U1")
    sql, params = cur.execute.call_args.args
    assert "created_by" in sql and params[-1] == "U1"


def test_a_key_from_an_active_admin_works_and_is_stamped(monkeypatch):
    cur, db_conn = _cursor((7, "T1", "U1"))
    monkeypatch.setattr(db, "db_conn", db_conn)
    with patch.object(db, "get_member_role", return_value="admin"):
        assert db.verify_mcp_key("mrn_x") == "T1"
    assert "last_used_at" in cur.execute.call_args.args[0]


@pytest.mark.parametrize("role", ["member"])
def test_a_key_whose_creator_left_or_was_demoted_is_refused(monkeypatch, role):
    cur, db_conn = _cursor((7, "T1", "U1"))
    monkeypatch.setattr(db, "db_conn", db_conn)
    with patch.object(db, "get_member_role", return_value=role):
        assert db.verify_mcp_key("mrn_x") is None
    assert all("UPDATE" not in c.args[0] for c in cur.execute.call_args_list)


def test_a_key_from_before_creators_were_recorded_still_works(monkeypatch):
    _, db_conn = _cursor((7, "T1", None))
    monkeypatch.setattr(db, "db_conn", db_conn)
    assert db.verify_mcp_key("mrn_x") == "T1"


def test_a_bogus_key_writes_nothing(monkeypatch):
    cur, db_conn = _cursor(None)
    monkeypatch.setattr(db, "db_conn", db_conn)
    assert db.verify_mcp_key("mrn_bogus") is None
    assert cur.execute.call_count == 1
    assert cur.execute.call_args.args[0].lstrip().startswith("SELECT")
