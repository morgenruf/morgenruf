"""A dashboard session ends within minutes of the person leaving Slack.

The members table is reconciled with Slack every few hours, so the session
check also asks Slack directly, at most every ten minutes per session.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask, session

from tests.test_dashboard import dashboard

_db_mock = MagicMock()


class SlackError(Exception):
    def __init__(self, error):
        super().__init__(error)
        self.response = {"ok": False, "error": error}


@pytest.fixture
def ctx(monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    _db_mock.reset_mock()
    # Patched on the module itself: another test may have imported dashboard
    # first with the real db bound.
    monkeypatch.setattr(dashboard, "db", _db_mock)
    _db_mock.session_member_active.return_value = True
    _db_mock.get_installation.return_value = {"bot_token": "xoxb-test"}
    client = MagicMock()
    sdk = MagicMock()
    sdk.WebClient.return_value = client
    monkeypatch.setitem(__import__("sys").modules, "slack_sdk", sdk)
    with app.test_request_context("/dashboard/api/me"):
        session.update(team_id="T1", user_id="U1")
        yield client


def test_an_active_slack_user_keeps_the_session(ctx):
    ctx.users_info.return_value = {"user": {"id": "U1", "deleted": False}}
    assert dashboard._session_revoked() is None
    assert session["team_id"] == "T1"


@pytest.mark.parametrize("user", [{"id": "U1", "deleted": True}, {"id": "U1", "is_bot": True}])
def test_deactivated_in_slack_ends_the_session_and_the_membership(ctx, user):
    ctx.users_info.return_value = {"user": user}
    response = dashboard._session_revoked()
    assert response[1] == 401
    assert "team_id" not in session
    _db_mock.set_members_active.assert_called_once_with("T1", ["U1"], False)


def test_unknown_to_slack_ends_the_session(ctx):
    ctx.users_info.side_effect = SlackError("user_not_found")
    assert dashboard._session_revoked()[1] == 401


def test_a_slack_outage_does_not_sign_anyone_out(ctx):
    ctx.users_info.side_effect = SlackError("ratelimited")
    assert dashboard._session_revoked() is None
    _db_mock.set_members_active.assert_not_called()


def test_slack_is_asked_at_most_every_ten_minutes(ctx, monkeypatch):
    import time

    ctx.users_info.return_value = {"user": {"id": "U1"}}
    start = 1_000_000
    monkeypatch.setattr(time, "time", lambda: start)
    dashboard._session_revoked()
    monkeypatch.setattr(time, "time", lambda: start + 61)
    dashboard._session_revoked()
    assert ctx.users_info.call_count == 1
    monkeypatch.setattr(time, "time", lambda: start + 601)
    dashboard._session_revoked()
    assert ctx.users_info.call_count == 2
