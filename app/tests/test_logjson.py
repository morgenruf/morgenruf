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
