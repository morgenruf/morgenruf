"""The OAuth state and login-token secret must never be a known constant.

`_state_secret` used to fall back to the literal string "fallback-insecure-key"
when FLASK_SECRET_KEY was unset. That value signs both the OAuth state (CSRF on
install) and the dashboard login token, so a deployment missing the env var had
a forgeable login for any team_id. app/.env.example ships the variable empty,
so a self-hoster following it would land in exactly that state.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# slack_sdk is a real dependency and oauth.py imports a submodule from it, so a
# MagicMock stub breaks the import. Drop any stub an earlier test module left.
for _n in ("slack_sdk", "slack_bolt", "pytz"):
    if isinstance(sys.modules.get(_n), MagicMock):
        del sys.modules[_n]


def _fresh_oauth(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("FLASK_SECRET_KEY", key)
    sys.modules.pop("oauth", None)
    return importlib.import_module("oauth")


class TestStateSecret:
    def test_no_hardcoded_fallback(self, monkeypatch):
        oauth = _fresh_oauth(monkeypatch, None)
        assert oauth._state_secret() != b"fallback-insecure-key"

    def test_fallback_is_unguessable_length(self, monkeypatch):
        oauth = _fresh_oauth(monkeypatch, None)
        assert len(oauth._state_secret()) >= 32

    def test_configured_key_is_used(self, monkeypatch):
        oauth = _fresh_oauth(monkeypatch, "a-real-configured-secret-value-32b")
        assert oauth._state_secret() == b"a-real-configured-secret-value-32b"

    def test_two_processes_do_not_share_the_fallback(self, monkeypatch):
        """Distinct processes must not converge on the same signing key."""
        a = _fresh_oauth(monkeypatch, None)._state_secret()
        sys.modules.pop("oauth", None)
        b = _fresh_oauth(monkeypatch, None)._state_secret()
        assert a != b

    def test_a_forged_login_token_is_rejected(self, monkeypatch):
        """The old constant must not verify against a running instance."""
        import hashlib
        import hmac
        import time

        oauth = _fresh_oauth(monkeypatch, "the-real-secret-for-this-instance")
        payload = f"{int(time.time())}.T_ATTACKER|U_ATTACKER"
        sig = hmac.new(b"fallback-insecure-key", payload.encode(), hashlib.sha256).hexdigest()
        import base64

        forged = base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()
        assert oauth.verify_login_token(forged) is None

    def test_a_genuine_login_token_still_works(self, monkeypatch):
        oauth = _fresh_oauth(monkeypatch, "the-real-secret-for-this-instance")
        good = oauth._make_login_token("T_REAL", "U_REAL")
        assert oauth.verify_login_token(good) == ("T_REAL", "U_REAL")
