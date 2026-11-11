"""One-line JSON log records for log shippers (Axiom, Loki, CloudWatch).

Enabled with LOG_FORMAT=json. Anything else keeps the plain text format,
which is easier to read in a local terminal. Standard library only.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import uuid
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


# The id of the request this thread is serving, so every line logged while
# handling it can be tied back to its access line.
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

REQUEST_ID_ENVIRON = "morgenruf.request_id"
REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")

# Path segments that are credentials. The public feed URL is its own token,
# so logging the raw path would hand the feed to anyone who can read logs.
_SECRET_PATHS = re.compile(r"^(/api/public)?/feed/[^/]+")


def request_id() -> str | None:
    return _request_id.get()


def safe_path(path: str) -> str:
    """The path as it is safe to log: never the query string, never a token."""
    return _SECRET_PATHS.sub(r"\1/feed/:token", path.split("?", 1)[0])


class RequestIdFilter(logging.Filter):
    """Add the current request id to records logged while serving a request."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _request_id.get()
        if rid and not hasattr(record, "request_id"):
            record.request_id = rid
        return True


class RequestIdMiddleware:
    """Give each request an id and send it back as X-Request-ID.

    A well-formed id from the proxy in front (nginx sets one) is kept, so one
    request has the same id in the frontend and backend logs. Anything else is
    replaced, since the header comes from outside.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        incoming = environ.get("HTTP_X_REQUEST_ID", "")
        rid = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        environ[REQUEST_ID_ENVIRON] = rid
        token = _request_id.set(rid)

        def start(status, headers, exc_info=None):
            headers = [(k, v) for k, v in headers if k.lower() != "x-request-id"]
            headers.append((REQUEST_ID_HEADER, rid))
            return start_response(status, headers, exc_info)

        try:
            return self.app(environ, start)
        finally:
            _request_id.reset(token)


def access_fields(method: str, path: str, status: int, duration_ms: float, size, rid, user_agent) -> dict:
    """The fields of one access log line, without the client address."""
    return {
        "method": method,
        "path": safe_path(path),
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "bytes": size,
        "request_id": rid,
        "user_agent": (user_agent or "")[:200],
    }


def access_level(status: int) -> int:
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO


def configure(level: int) -> None:
    """Set up the root logger the way basicConfig did, with the chosen format."""
    handler = logging.StreamHandler()
    handler.setFormatter(make_formatter())
    handler.addFilter(RequestIdFilter())
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
            # Only gunicorn's own handlers. A handler shared with the root
            # logger (a test harness, an operator's logging config) belongs to
            # someone else and keeps its format.
            shared = set(logging.getLogger().handlers)
            for log in (self.error_log, self.access_log):
                for handler in log.handlers:
                    if handler in shared:
                        continue
                    handler.setFormatter(formatter)
                    if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
                        handler.addFilter(RequestIdFilter())

        def access(self, resp, req, environ, request_time):
            # In JSON mode an access line carries its parts as fields
            # (method, path, status, duration_ms, request_id) instead of one
            # Apache-style string, so Loki can chart latency and status
            # without parsing text. It also leaves out the client address.
            if not json_enabled():
                return super().access(resp, req, environ, request_time)
            if not self.access_log_enabled:
                return
            try:
                status = int(str(resp.status).split(None, 1)[0])
                ms = request_time.total_seconds() * 1000
                fields = access_fields(
                    req.method,
                    req.path,
                    status,
                    ms,
                    getattr(resp, "sent", None),
                    environ.get(REQUEST_ID_ENVIRON),
                    environ.get("HTTP_USER_AGENT"),
                )
                self.access_log.log(
                    access_level(status),
                    "%s %s %s %.0fms",
                    fields["method"],
                    fields["path"],
                    status,
                    ms,
                    extra=fields,
                )
            except Exception:
                self.error("access log failed", exc_info=True)

    return Logger
