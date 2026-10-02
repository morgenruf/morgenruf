"""Signing in to the dashboard from Slack, for people who did not install the app."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.core import dashboard_signin, oauth


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://api.example.com")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")


def _token(url: str) -> str:
    assert url.startswith("https://api.example.com/dashboard?t=")
    return url.split("?t=", 1)[1]


def _link(blocks: list[dict]) -> dict:
    return next(
        el
        for b in blocks
        if b["type"] == "actions"
        for el in b["elements"]
        if el["action_id"] == dashboard_signin.LINK_ACTION
    )


class TestTheLink:
    def test_signs_in_the_person_who_asked(self):
        url = dashboard_signin.signin_url("T1", "U_DEEPAK")
        assert oauth.verify_login_token(_token(url)) == ("T1", "U_DEEPAK")

    def test_every_link_is_new(self):
        assert dashboard_signin.signin_url("T1", "U1") != dashboard_signin.signin_url("T1", "U1")

    def test_works_once(self, monkeypatch):
        used: set[str] = set()

        def claim(nonce):
            if nonce in used:
                return False
            used.add(nonce)
            return True

        monkeypatch.setattr(oauth.db, "claim_login_token", claim)
        token = _token(dashboard_signin.signin_url("T1", "U1"))
        assert oauth.consume_login_token(token) == ("T1", "U1")
        assert oauth.consume_login_token(token) is None

    def test_expires_after_five_minutes(self, monkeypatch):
        import time

        token = _token(dashboard_signin.signin_url("T1", "U1"))
        real = time.time
        monkeypatch.setattr(time, "time", lambda: real() + 301)
        assert oauth.verify_login_token(token) is None


class TestWhereItIsShown:
    def test_the_modal_has_the_link_and_says_how_long_it_lasts(self):
        view = dashboard_signin.signin_modal("T1", "U1")
        assert view["type"] == "modal"
        assert oauth.verify_login_token(_token(_link(view["blocks"])["url"])) == ("T1", "U1")
        assert "5 minutes" in dashboard_signin.EXPLAINER

    def test_the_command_reply_is_ephemeral(self):
        message = dashboard_signin.signin_message("T1", "U1")
        assert message["response_type"] == "ephemeral"
        assert _link(message["blocks"])["url"].startswith("https://api.example.com/dashboard?t=")


def _capture_handlers(register):
    app = MagicMock()
    handlers: dict = {}

    def deco(kind):
        def outer(name):
            def inner(fn):
                handlers[(kind, name)] = fn
                return fn

            return inner

        return outer

    app.action.side_effect = deco("action")
    app.command.side_effect = deco("command")
    app.view.side_effect = deco("view")
    app.event.side_effect = deco("event")
    app.options.side_effect = deco("options")
    app.shortcut.side_effect = deco("shortcut")
    register(app)
    return handlers


class TestSlack:
    def test_home_dashboard_button_opens_a_sign_in_for_the_clicker(self):
        from src.modules.standup import handlers as standup_handlers

        handlers = _capture_handlers(standup_handlers.register_handlers)
        client = MagicMock()
        ack = MagicMock()
        handlers[("action", "open_dashboard")](
            ack=ack,
            body={"user": {"id": "U9", "team_id": "T1"}, "team": {"id": "T1"}, "trigger_id": "trig"},
            client=client,
        )
        ack.assert_called_once()
        view = client.views_open.call_args.kwargs["view"]
        assert client.views_open.call_args.kwargs["trigger_id"] == "trig"
        assert oauth.verify_login_token(_token(_link(view["blocks"])["url"])) == ("T1", "U9")

    def test_morgenruf_dashboard_replies_only_to_the_person(self):
        from src.core import profile_slack

        handlers = _capture_handlers(profile_slack.register_slack)
        respond = MagicMock()
        client = MagicMock()
        handlers[("command", "/morgenruf")](
            ack=MagicMock(),
            body={"user_id": "U9", "team_id": "T1", "text": "dashboard"},
            client=client,
            respond=respond,
        )
        sent = respond.call_args.kwargs
        assert sent["response_type"] == "ephemeral"
        assert oauth.verify_login_token(_token(_link(sent["blocks"])["url"])) == ("T1", "U9")
        client.chat_postMessage.assert_not_called()
