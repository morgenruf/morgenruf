"""JSON log formatter used when LOG_FORMAT=json."""

from __future__ import annotations

import json
import logging
import sys
from types import SimpleNamespace

from src.core import logjson


def _record(msg="hello %s", args=("world",), level=logging.INFO, exc_info=None, extra=None):
    logger = logging.getLogger("morgenruf.test")
    return logger.makeRecord(logger.name, level, __file__, 10, msg, args, exc_info, extra=extra)


def test_basic_fields():
    out = json.loads(logjson.JsonFormatter().format(_record()))
    assert out["level"] == "INFO"
    assert out["logger"] == "morgenruf.test"
    assert out["message"] == "hello world"
    assert out["time"].endswith("+00:00")
    assert "exc_info" not in out


def test_output_is_one_line():
    line = logjson.JsonFormatter().format(_record(msg="a\nb", args=()))
    assert "\n" not in line
    assert json.loads(line)["message"] == "a\nb"


def test_exception_is_a_string():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record(level=logging.ERROR, exc_info=sys.exc_info())
    out = json.loads(logjson.JsonFormatter().format(record))
    assert isinstance(out["exc_info"], str)
    assert "ValueError: boom" in out["exc_info"]


def test_serialisable_extra_is_kept_and_the_rest_dropped():
    record = _record(extra={"team_id": "T123", "count": 3, "obj": object()})
    out = json.loads(logjson.JsonFormatter().format(record))
    assert out["team_id"] == "T123"
    assert out["count"] == 3
    assert "obj" not in out
    # Standard record attributes are not repeated.
    assert "lineno" not in out
    assert "args" not in out


def test_extra_cannot_overwrite_core_fields():
    record = _record()
    record.level = "spoofed"
    out = json.loads(logjson.JsonFormatter().format(record))
    assert out["level"] == "INFO"


def test_format_follows_env(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    assert not isinstance(logjson.make_formatter(), logjson.JsonFormatter)
    monkeypatch.setenv("LOG_FORMAT", "JSON")
    assert isinstance(logjson.make_formatter(), logjson.JsonFormatter)
    monkeypatch.setenv("LOG_FORMAT", "text")
    assert not isinstance(logjson.make_formatter(), logjson.JsonFormatter)


def _gunicorn_cfg():
    return SimpleNamespace(
        loglevel="info",
        errorlog="-",
        accesslog="-",
        syslog=False,
        capture_output=False,
        logconfig=None,
        logconfig_dict={},
        logconfig_json=None,
        access_log_format='%(h)s "%(r)s" %(s)s',
    )


def test_gunicorn_logs_use_json(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    log = logjson.gunicorn_logger_class()(_gunicorn_cfg())
    for logger in (log.error_log, log.access_log):
        assert logger.handlers
        assert all(isinstance(h.formatter, logjson.JsonFormatter) for h in logger.handlers)


def test_gunicorn_logs_stay_text_by_default(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    log = logjson.gunicorn_logger_class()(_gunicorn_cfg())
    assert not any(isinstance(h.formatter, logjson.JsonFormatter) for h in log.error_log.handlers)


def test_safe_path_drops_the_query_and_feed_tokens():
    assert logjson.safe_path("/dashboard/api/kudos?code=abc") == "/dashboard/api/kudos"
    assert logjson.safe_path("/feed/s3cr3t-token") == "/feed/:token"
    assert logjson.safe_path("/api/public/feed/s3cr3t-token") == "/api/public/feed/:token"
    assert logjson.safe_path("/api/public/feed/s3cr3t/extra") == "/api/public/feed/:token/extra"
    assert logjson.safe_path("/feedback") == "/feedback"


def _call(app, headers=None):
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/x", **(headers or {})}
    seen = {}

    def start_response(status, response_headers, exc_info=None):
        seen["headers"] = dict(response_headers)

    body = b"".join(app(environ, start_response))
    return environ, seen["headers"], body


def _inner(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain"), ("X-Request-ID", "from-the-app")])
    return [(logjson.request_id() or "").encode()]


def test_middleware_keeps_a_valid_incoming_id():
    environ, headers, body = _call(logjson.RequestIdMiddleware(_inner), {"HTTP_X_REQUEST_ID": "abcdef0123456789"})
    assert environ[logjson.REQUEST_ID_ENVIRON] == "abcdef0123456789"
    assert headers["X-Request-ID"] == "abcdef0123456789"
    assert body == b"abcdef0123456789"
    assert logjson.request_id() is None


def test_middleware_replaces_a_missing_or_hostile_id():
    for value in (None, "short", 'bad"id\nwith newline', "x" * 300):
        extra = {} if value is None else {"HTTP_X_REQUEST_ID": value}
        environ, headers, _ = _call(logjson.RequestIdMiddleware(_inner), extra)
        rid = environ[logjson.REQUEST_ID_ENVIRON]
        assert rid != value and len(rid) == 32
        assert headers["X-Request-ID"] == rid


def test_lines_logged_during_a_request_carry_its_id():
    record = _record()
    token = logjson._request_id.set("req-00000001")
    try:
        logjson.RequestIdFilter().filter(record)
    finally:
        logjson._request_id.reset(token)
    assert json.loads(logjson.JsonFormatter().format(record))["request_id"] == "req-00000001"
    outside = _record()
    logjson.RequestIdFilter().filter(outside)
    assert "request_id" not in json.loads(logjson.JsonFormatter().format(outside))


def _access(monkeypatch, status, path="/dashboard/api/kudos", query="code=secret"):
    from datetime import timedelta

    monkeypatch.setenv("LOG_FORMAT", "json")
    log = logjson.gunicorn_logger_class()(_gunicorn_cfg())
    records = []
    # gunicorn's own handler, not one pytest shares with the root logger
    handler = next(h for h in log.access_log.handlers if h not in logging.getLogger().handlers)
    monkeypatch.setattr(handler, "emit", records.append)
    resp = SimpleNamespace(status=f"{status} WHATEVER", sent=42)
    req = SimpleNamespace(method="GET", path=path, query=query, uri=f"{path}?{query}")
    environ = {
        logjson.REQUEST_ID_ENVIRON: "abcdef0123456789",
        "HTTP_USER_AGENT": "kube-probe/1.36",
        "REMOTE_ADDR": "203.0.113.9",
    }
    log.access(resp, req, environ, timedelta(milliseconds=12.34))
    assert len(records) == 1
    return records[0], json.loads(handler.formatter.format(records[0]))


def test_access_line_has_fields_and_no_client_address(monkeypatch):
    record, out = _access(monkeypatch, 200)
    assert out["method"] == "GET"
    assert out["path"] == "/dashboard/api/kudos"
    assert out["status"] == 200
    assert out["duration_ms"] == 12.3
    assert out["bytes"] == 42
    assert out["request_id"] == "abcdef0123456789"
    assert out["user_agent"] == "kube-probe/1.36"
    assert out["message"] == "GET /dashboard/api/kudos 200 12ms"
    assert out["level"] == "INFO"
    line = json.dumps(out)
    assert "203.0.113.9" not in line and "secret" not in line


def test_access_level_follows_status(monkeypatch):
    assert _access(monkeypatch, 404)[1]["level"] == "WARNING"
    assert _access(monkeypatch, 503)[1]["level"] == "ERROR"


def test_access_line_hides_the_feed_token(monkeypatch):
    _, out = _access(monkeypatch, 200, path="/api/public/feed/s3cr3t-token", query="")
    assert out["path"] == "/api/public/feed/:token"
    assert "s3cr3t" not in json.dumps(out)
