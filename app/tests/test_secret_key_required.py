"""The app must not start in production without a signing key.

FLASK_SECRET_KEY signs the Flask session, the Slack OAuth state parameter and
the dashboard login token. It used to fall back to a random value with only a
warning, so a deployment could reach production having never set it, and
app/.env.example ships the variable empty.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# slack_bolt and apscheduler are real dependencies and main.py imports submodules
# from both, so a MagicMock stub breaks the import. Drop any an earlier test
# module left behind instead.
for _n in ("slack_bolt", "apscheduler", "pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_n), MagicMock):
        del sys.modules[_n]

import main  # noqa: E402


class TestSecretKeyRequired:
    def test_refuses_to_start_without_one(self, monkeypatch):
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
            main._resolve_secret_key()

    def test_an_empty_value_counts_as_missing(self, monkeypatch):
        """.env.example ships the variable present but blank."""
        monkeypatch.setenv("FLASK_SECRET_KEY", "   ")
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        with pytest.raises(RuntimeError):
            main._resolve_secret_key()

    def test_a_configured_key_is_used_verbatim(self, monkeypatch):
        monkeypatch.setenv("FLASK_SECRET_KEY", "x" * 40)
        assert main._resolve_secret_key() == "x" * 40

    def test_dev_still_runs_with_no_setup(self, monkeypatch):
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        monkeypatch.setenv("FLASK_DEBUG", "1")
        key = main._resolve_secret_key()
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_a_short_key_is_accepted_but_warned_about(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("FLASK_SECRET_KEY", "tooshort")
        with caplog.at_level(logging.WARNING):
            assert main._resolve_secret_key() == "tooshort"
        assert "32" in caplog.text

    def test_two_dev_processes_get_different_keys(self, monkeypatch):
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        monkeypatch.setenv("FLASK_DEBUG", "1")
        assert main._resolve_secret_key() != main._resolve_secret_key()
