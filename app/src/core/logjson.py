"""One-line JSON log records for log shippers (Axiom, Loki, CloudWatch).

Enabled with LOG_FORMAT=json. Anything else keeps the plain text format,
which is easier to read in a local terminal. Standard library only.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

# Attributes every LogRecord carries. Anything else on a record came from
# `extra=` and is worth shipping.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}

TEXT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def json_enabled() -> bool:
    return os.environ.get("LOG_FORMAT", "").strip().lower() == "json"


class JsonFormatter(logging.Formatter):
    """Render a record as a single JSON object on one line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exc_info"] = record.exc_text
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED or key in payload:
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def make_formatter() -> logging.Formatter:
    return JsonFormatter() if json_enabled() else logging.Formatter(TEXT_FORMAT)


def configure(level: int) -> None:
    """Set up the root logger the way basicConfig did, with the chosen format."""
    handler = logging.StreamHandler()
    handler.setFormatter(make_formatter())
    logging.basicConfig(level=level, handlers=[handler])


def gunicorn_logger_class():
    """Gunicorn's logger with its handlers switched to our formatter.

    Gunicorn attaches its own handlers to gunicorn.error and gunicorn.access
    and stops them propagating, so the root formatter never sees those
    records. With LOG_FORMAT=json this swaps their formatter after gunicorn's
    own setup, so access and error lines come out as JSON too. In text mode
    gunicorn's usual format is kept.
    """
    from gunicorn import glogging

    class Logger(glogging.Logger):
        def setup(self, cfg):
            super().setup(cfg)
            if not json_enabled():
                return
            formatter = JsonFormatter()
            for log in (self.error_log, self.access_log):
                for handler in log.handlers:
                    handler.setFormatter(formatter)

    return Logger
