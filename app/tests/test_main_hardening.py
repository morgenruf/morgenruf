"""Startup and health checks in main.py.

LOG_LEVEL=DEBUG used to start Flask's debug server and let the app boot
without FLASK_SECRET_KEY. An empty SLACK_SIGNING_SECRET was accepted, which
made Slack signatures forgeable. /healthz returned 200 whatever state the
database and scheduler were in, and the status page trusted it.
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

for _name in [n for n in list(sys.modules) if n.split(".")[0] in {"slack_bolt", "slack_sdk", "apscheduler", "pytz"}]:
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

import main  # noqa: E402


class TestDebugIsNotALogLevel:
    def test_log_level_debug_is_not_dev_mode(self, monkeypatch):
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        assert main._is_dev_mode() is False

    def test_log_level_debug_still_needs_a_secret_key(self, monkeypatch):
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        with pytest.raises(RuntimeError):
            main._resolve_secret_key()

    def test_flask_debug_is_dev_mode(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "1")
        assert main._is_dev_mode() is True

    def test_slack_sdk_never_logs_below_info(self):
        import logging

        assert logging.getLogger("slack_sdk").level >= logging.INFO


class TestSigningSecret:
    def test_configured_secret_is_used(self, monkeypatch):
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "abc123")
        assert main._resolve_signing_secret() == "abc123"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_missing_secret_becomes_unguessable(self, monkeypatch, value):
        if value is None:
            monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
        else:
            monkeypatch.setenv("SLACK_SIGNING_SECRET", value)
        a = main._resolve_signing_secret()
        b = main._resolve_signing_secret()
        assert len(a) >= 32
        assert a != b


class _Scheduler:
    def __init__(self, running=True, thread_alive=True):
        self.running = running
        self._thread = MagicMock()
        self._thread.is_alive.return_value = thread_alive

    def get_jobs(self):
        return [1, 2, 3]


class TestSchedulerAlive:
    def test_running_scheduler(self):
        assert main._scheduler_alive(_Scheduler()) is True

    def test_stopped_scheduler(self):
        assert main._scheduler_alive(_Scheduler(running=False)) is False

    def test_dead_thread(self):
        assert main._scheduler_alive(_Scheduler(thread_alive=False)) is False


class TestSchedulerAliveFromForkedWorker:
    """Gunicorn forks the worker after the master started the scheduler."""

    @pytest.fixture(autouse=True)
    def forked(self, monkeypatch):
        monkeypatch.setattr(main, "_scheduler_pid", os.getpid() + 1)

    def test_fresh_beat_is_alive_though_local_thread_is_dead(self, monkeypatch):
        monkeypatch.setattr(main._SCHEDULER_BEAT, "value", time.time())
        assert main._scheduler_alive(_Scheduler(thread_alive=False)) is True

    def test_stale_beat_is_dead(self, monkeypatch):
        monkeypatch.setattr(main._SCHEDULER_BEAT, "value", time.time() - 3600)
        assert main._scheduler_alive(_Scheduler()) is False


def test_beat_is_shared_with_a_forked_child():
    main._SCHEDULER_BEAT.value = 0.0
    pid = os.fork()
    if pid == 0:
        main._SCHEDULER_BEAT.value = 123.0
        os._exit(0)
    os.waitpid(pid, 0)
    assert main._SCHEDULER_BEAT.value == 123.0


class TestDatabaseReachable:
    def test_reachable(self, monkeypatch):
        import src.core.db as db

        cur = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        @contextmanager
        def ok():
            yield conn

        monkeypatch.setattr(db, "db_conn", ok)
        assert main._database_reachable() is True
        cur.execute.assert_called_once_with("SELECT 1")

    def test_unreachable(self, monkeypatch):
        import src.core.db as db

        @contextmanager
        def down():
            raise RuntimeError("connection refused")
            yield

        monkeypatch.setattr(db, "db_conn", down)
        assert main._database_reachable() is False


class TestHealthRoutes:
    @pytest.fixture
    def app(self, monkeypatch):
        """create_app with the heavy parts replaced, returning its Flask app."""
        from flask import Flask

        flask_app = Flask(__name__)
        state = {"scheduler": _Scheduler(), "db": True}
        monkeypatch.setattr(main, "PostgresInstallationStore", MagicMock())
        monkeypatch.setattr(main, "App", MagicMock())
        monkeypatch.setattr(main, "SlackRequestHandler", MagicMock())
        monkeypatch.setattr(main, "_load_workspace_jobs", lambda: [])
        monkeypatch.setattr(main, "build_scheduler", lambda jobs: state["scheduler"])
        monkeypatch.setattr(main, "_resolve_secret_key", lambda: "k" * 32)
        monkeypatch.setattr(main, "register_slack_listeners", lambda *a: [])
        monkeypatch.setattr(main, "_database_reachable", lambda: state["db"])
        state["scheduler"].start = lambda: None
        import src.http_app as http_app

        monkeypatch.setattr(http_app, "create_http_app", lambda modules: flask_app)
        main.create_app()
        return flask_app.test_client(), state

    def test_healthy(self, app):
        client, _ = app
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json == {"status": "ok", "scheduler": True, "db": True, "jobs": 3}

    def test_database_down_fails_readiness_not_liveness(self, app):
        client, state = app
        state["db"] = False
        assert client.get("/healthz").status_code == 503
        assert client.get("/healthz").json["db"] is False
        assert client.get("/livez").status_code == 200

    def test_dead_scheduler_fails_both(self, app):
        client, state = app
        state["scheduler"]._thread.is_alive.return_value = False
        assert client.get("/healthz").status_code == 503
        assert client.get("/livez").status_code == 503
