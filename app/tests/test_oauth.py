"""Tests for oauth.py — state token generation and verification."""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Stub heavy dependencies before importing oauth
sys.modules.setdefault("flask", MagicMock())
sys.modules.setdefault("markupsafe", MagicMock())
sys.modules.setdefault("slack_sdk", MagicMock())
sys.modules.setdefault("slack_sdk.oauth", MagicMock())
sys.modules.setdefault("db", MagicMock())
sys.modules.setdefault("mailer", MagicMock())


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key-for-unit-tests")
    monkeypatch.setenv("SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("APP_URL", "http://localhost:3000")


class TestOAuthStateToken:
    def test_make_state_returns_string(self):
        from oauth import _make_state
        state = _make_state()
        assert isinstance(state, str)
        assert len(state) > 0

    def test_state_has_three_parts(self):
        from oauth import _make_state
        state = _make_state()
        parts = state.split(".")
        assert len(parts) == 3  # ts.nonce.sig

    def test_valid_state_verifies(self):
        from oauth import _make_state, _verify_state
        state = _make_state()
        assert _verify_state(state) is True

    def test_tampered_signature_rejected(self):
        from oauth import _make_state, _verify_state
        state = _make_state()
        parts = state.rsplit(".", 1)
        tampered = parts[0] + ".badsignature"
        assert _verify_state(tampered) is False

    def test_tampered_timestamp_rejected(self):
        from oauth import _make_state, _verify_state
        state = _make_state()
        ts, nonce, sig = state.split(".")
        tampered = f"9999999999.{nonce}.{sig}"
        assert _verify_state(tampered) is False

    def test_expired_state_rejected(self):
        from oauth import _make_state, _verify_state
        state = _make_state()
        # Simulate 11 minutes in the future
        with patch("time.time", return_value=time.time() + 660):
            assert _verify_state(state) is False

    def test_fresh_state_within_window(self):
        from oauth import _make_state, _verify_state
        state = _make_state()
        # 9 minutes later — still valid
        with patch("time.time", return_value=time.time() + 540):
            assert _verify_state(state) is True

    def test_garbage_state_rejected(self):
        from oauth import _verify_state
        assert _verify_state("notavalidstate") is False
        assert _verify_state("") is False
        assert _verify_state("a.b") is False

    def test_different_secret_rejected(self, monkeypatch):
        from oauth import _make_state
        state = _make_state()
        monkeypatch.setenv("FLASK_SECRET_KEY", "different-secret")
        # Reimport to pick up new secret
        import importlib

        import oauth as oauth_mod
        importlib.reload(oauth_mod)
        assert oauth_mod._verify_state(state) is False

    def test_two_states_are_unique(self):
        from oauth import _make_state
        s1 = _make_state()
        s2 = _make_state()
        assert s1 != s2


class TestLoginToken:
    def test_make_and_verify_login_token(self):
        from oauth import _make_login_token, verify_login_token
        token = _make_login_token("T123", "U456")
        result = verify_login_token(token)
        assert result == ("T123", "U456")

    def test_expired_login_token_rejected(self):
        from oauth import _make_login_token, verify_login_token
        token = _make_login_token("T123", "U456")
        with patch("time.time", return_value=time.time() + 400):  # 6+ min later
            result = verify_login_token(token)
        assert result is None

    def test_tampered_login_token_rejected(self):
        from oauth import verify_login_token
        assert verify_login_token("garbage.token.value") is None
        assert verify_login_token("") is None

    def test_login_token_fresh_within_window(self):
        from oauth import _make_login_token, verify_login_token
        token = _make_login_token("T123", "U456")
        with patch("time.time", return_value=time.time() + 250):  # ~4 min later
            result = verify_login_token(token)
        assert result == ("T123", "U456")
