"""OAuth callback: who becomes admin, state bound to the browser, one-time login links.

Dashboard sign-in runs through the same OAuth flow as install. The callback
used to call ensure_admin for whoever finished it and overwrite the recorded
installer, so any member of a workspace that lets members install apps became
an admin by clicking Sign in.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

for _n in ("slack_sdk", "slack_sdk.oauth", "flask", "markupsafe"):
    if isinstance(sys.modules.get(_n), MagicMock):
        del sys.modules[_n]


@pytest.fixture
def oauth(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "callback-security-test-secret-0123456789")
    sys.modules.pop("src.core.oauth", None)
    mod = importlib.import_module("src.core.oauth")
    fake_db = MagicMock()
    fake_db.save_installation.return_value = False
    fake_db.claim_login_token.return_value = True
    monkeypatch.setattr(mod, "db", fake_db)
    monkeypatch.setattr(mod, "_schedule_workspace", lambda *a: None)
    monkeypatch.setattr(mod, "_try_send_welcome_email", lambda *a: None)
    return mod


@pytest.fixture
def client(oauth):
    from flask import Flask

    app = Flask(__name__)
    app.secret_key = "callback-security-test-secret-0123456789"
    app.register_blueprint(oauth.oauth_bp)
    return app.test_client()


def _start_install(client) -> str:
    resp = client.get("/install")
    assert resp.status_code == 302
    return parse_qs(urlparse(resp.location).query)["state"][0]


def _slack(user: dict):
    web = MagicMock()
    web.oauth_v2_access.return_value = {
        "team": {"id": "T1", "name": "Acme"},
        "access_token": "xoxb-new",
        "bot_user_id": "B1",
        "app_id": "A1",
        "authed_user": {"id": "U_CALLER"},
        "scope": "chat:write",
    }
    web.users_info.return_value = {"user": user}
    web.conversations_open.return_value = {"channel": {"id": "D1"}}
    return web


def _callback(client, oauth, *, new_install: bool, slack_user: dict):
    state = _start_install(client)
    oauth.db.save_installation.return_value = new_install
    with patch.object(oauth, "WebClient", return_value=_slack(slack_user)):
        return client.get(f"/oauth/callback?code=c&state={state}")


class TestAdminGrant:
    def test_first_installer_becomes_admin(self, client, oauth):
        _callback(client, oauth, new_install=True, slack_user={})
        oauth.db.ensure_admin.assert_called_once_with("T1", "U_CALLER")

    def test_plain_member_signing_in_does_not_become_admin(self, client, oauth):
        resp = _callback(client, oauth, new_install=False, slack_user={"is_admin": False})
        oauth.db.ensure_admin.assert_not_called()
        assert "/dashboard?t=" in resp.location

    @pytest.mark.parametrize("flag", ["is_admin", "is_owner", "is_primary_owner"])
    def test_slack_admins_and_owners_become_admin(self, client, oauth, flag):
        _callback(client, oauth, new_install=False, slack_user={flag: True})
        oauth.db.ensure_admin.assert_called_once_with("T1", "U_CALLER")

    def test_slack_lookup_failure_grants_nothing(self, client, oauth):
        state = _start_install(client)
        web = _slack({})
        web.users_info.side_effect = RuntimeError("slack down")
        with patch.object(oauth, "WebClient", return_value=web):
            client.get(f"/oauth/callback?code=c&state={state}")
        oauth.db.ensure_admin.assert_not_called()

    def test_reinstall_keeps_the_original_installer(self):
        src = (Path(__file__).resolve().parents[1] / "src" / "core" / "db.py").read_text()
        assert (
            "installed_by_user_id = COALESCE(installations.installed_by_user_id, EXCLUDED.installed_by_user_id)" in src
        )


class TestStateBinding:
    def test_state_from_another_browser_is_rejected(self, client, oauth, monkeypatch):
        from flask import Flask

        attacker_state = _start_install(client)
        other = Flask(__name__)
        other.secret_key = "callback-security-test-secret-0123456789"
        other.register_blueprint(oauth.oauth_bp)
        victim = other.test_client()
        with patch.object(oauth, "WebClient", return_value=_slack({})) as web:
            resp = victim.get(f"/oauth/callback?code=attacker&state={attacker_state}")
        assert resp.location == "/auth/result?status=invalid"
        web.return_value.oauth_v2_access.assert_not_called()

    def test_state_cannot_be_used_twice(self, client, oauth):
        state = _start_install(client)
        with patch.object(oauth, "WebClient", return_value=_slack({})):
            client.get(f"/oauth/callback?code=c&state={state}")
            resp = client.get(f"/oauth/callback?code=c&state={state}")
        assert resp.location == "/auth/result?status=invalid"

    def test_missing_state_restarts_through_install(self, client, oauth):
        with patch.object(oauth, "WebClient") as web:
            resp = client.get("/oauth/callback?code=c")
        assert resp.location.endswith("/install")
        web.return_value.oauth_v2_access.assert_not_called()


class TestTokenSeparation:
    def test_state_is_not_a_login_token(self, oauth):
        import base64

        state = oauth._make_state()
        assert oauth.verify_login_token(base64.urlsafe_b64encode(state.encode()).decode()) is None

    def test_login_token_is_not_a_state(self, oauth):
        assert oauth._verify_state(oauth._make_login_token("T1", "U1")) is False


class TestOneTimeLoginToken:
    def test_second_use_is_refused(self, oauth):
        used: set[str] = set()

        def claim(nonce):
            if nonce in used:
                return False
            used.add(nonce)
            return True

        oauth.db.claim_login_token.side_effect = claim
        token = oauth._make_login_token("T1", "U1")
        assert oauth.consume_login_token(token) == ("T1", "U1")
        assert oauth.consume_login_token(token) is None

    def test_database_error_refuses_the_token(self, oauth):
        oauth.db.claim_login_token.side_effect = RuntimeError("db down")
        assert oauth.consume_login_token(oauth._make_login_token("T1", "U1")) is None
