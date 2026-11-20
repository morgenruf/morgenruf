"""Prometheus metrics, served on their own port (METRICS_PORT, default 9090).

The port is separate from the app port so /metrics is never reachable through
the frontend proxy or the public hostname.

The scheduler and Socket Mode run in gunicorn's master process and HTTP
requests in its forked worker, so the metrics use prometheus_client's
multiprocess mode: each process writes its samples to files in
PROMETHEUS_MULTIPROC_DIR and the server in the master reads them all. The
directory has to be set before prometheus_client is imported, which is why it
is set at the top of this module. A fresh directory per start means no stale
samples from an earlier process are ever read.

Labels stay low cardinality: route templates, never raw paths, and no team,
user or schedule ids.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import re
import tempfile
import time

if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = tempfile.mkdtemp(
        prefix="morgenruf-metrics-", dir="/dev/shm" if os.path.isdir("/dev/shm") else None
    )

from prometheus_client import (  # noqa: E402
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    multiprocess,
    start_http_server,
)
from prometheus_client.core import GaugeMetricFamily  # noqa: E402

from src.core.version import APP_VERSION  # noqa: E402

logger = logging.getLogger(__name__)

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests served", ["method", "route", "status"])
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ["method", "route"])

SLACK_EVENTS = Counter(
    "morgenruf_slack_events_total", "Slack events, commands and interactions received", ["type", "result"]
)
SLACK_API_CALLS = Counter("morgenruf_slack_api_calls_total", "Slack Web API calls", ["method", "result"])
SLACK_API_DURATION = Histogram(
    "morgenruf_slack_api_call_duration_seconds", "Slack Web API call duration, retries included", ["method"]
)

JOB_RUNS = Counter("morgenruf_job_runs_total", "Scheduler job runs", ["job", "result"])
JOB_DURATION = Histogram(
    "morgenruf_job_duration_seconds",
    "Scheduler job duration",
    ["job"],
    buckets=(0.1, 0.5, 1, 5, 15, 30, 60, 120, 300, 600, 1800),
)

MESSAGES_SENT = Counter("morgenruf_messages_sent_total", "Slack messages posted, by the job that sent them", ["kind"])
INSTALLS = Counter("morgenruf_installs_total", "OAuth install callbacks, by outcome", ["result"])

DB_POOL = Gauge("morgenruf_db_pool_connections", "Postgres pool connections", ["state"], multiprocess_mode="livesum")

BUILD_INFO = Gauge("morgenruf_build_info", "Running build", ["version", "commit"], multiprocess_mode="max")
BUILD_INFO.labels(version=APP_VERSION, commit=os.environ.get("GIT_COMMIT") or "unknown").set(1)

_MESSAGE_METHODS = {"chat.postMessage", "chat.postEphemeral", "chat.scheduleMessage"}
_current_job: contextvars.ContextVar[str] = contextvars.ContextVar("metrics_job", default="interactive")

# standup_T01ABC, report_schedule_T01ABC_7, standup_retry_T01ABC_7_1700000000
_TEAM_SUFFIX = re.compile(r"_[TE][A-Z0-9]{6,}(_.*)?$")


def job_name(job_id: str) -> str:
    """The stable name of a job, without the team, schedule or run ids in its id.

    Module jobs are module:team:key, and the key's first part names the job
    (connect:T01:round:7 is connect:round).
    """
    if ":" in job_id:
        parts = job_id.split(":")
        return f"{parts[0]}:{parts[2]}" if len(parts) > 2 else parts[0]
    return _TEAM_SUFFIX.sub("", job_id)


@contextlib.contextmanager
def job_context(name: str):
    """Attribute the Slack messages sent inside the block to this job."""
    token = _current_job.set(name)
    try:
        yield
    finally:
        _current_job.reset(token)


def record_job(name: str, results: list[str], seconds: float) -> None:
    for result in results:
        JOB_RUNS.labels(job=name, result=result).inc()
    if "success" in results or "error" in results:
        JOB_DURATION.labels(job=name).observe(seconds)


def record_slack_call(method: str, result: str, seconds: float) -> None:
    SLACK_API_CALLS.labels(method=method, result=result).inc()
    SLACK_API_DURATION.labels(method=method).observe(seconds)
    if result == "ok" and method in _MESSAGE_METHODS:
        MESSAGES_SENT.labels(kind=_current_job.get()).inc()


def set_db_pool(in_use: int, idle: int, max_size: int) -> None:
    DB_POOL.labels(state="in_use").set(in_use)
    DB_POOL.labels(state="idle").set(idle)
    DB_POOL.labels(state="max").set(max_size)


def install_flask(app) -> None:  # noqa: ANN001
    """Count and time every request by its route template."""
    from flask import g, request  # noqa: PLC0415

    @app.before_request
    def _start_timer():
        g._metrics_start = time.perf_counter()

    @app.after_request
    def _record(response):
        start = g.pop("_metrics_start", None)
        if start is not None:
            route = request.url_rule.rule if request.url_rule else "unmatched"
            HTTP_REQUESTS.labels(method=request.method, route=route, status=str(response.status_code)).inc()
            HTTP_DURATION.labels(method=request.method, route=route).observe(time.perf_counter() - start)
        return response


def _slack_event_type(body: dict) -> str:
    if body.get("command"):
        return "command"
    kind = body.get("type") or "unknown"
    if kind == "event_callback":
        return f"event:{(body.get('event') or {}).get('type') or 'unknown'}"
    return kind


def install_bolt(bolt_app) -> None:  # noqa: ANN001
    """Count every event, command and interaction Bolt receives, with its outcome."""

    @bolt_app.middleware
    def _count_slack_events(body, next):  # noqa: A002, ANN001
        kind = _slack_event_type(body or {})
        try:
            resp = next()
        except Exception:
            SLACK_EVENTS.labels(type=kind, result="error").inc()
            raise
        status = getattr(resp, "status", 200)
        SLACK_EVENTS.labels(type=kind, result="ok" if status < 400 else "error").inc()
        return resp


def install_slack_sdk() -> None:
    """Time every Slack Web API call, whatever client or module makes it."""
    from slack_sdk.errors import SlackApiError  # noqa: PLC0415
    from slack_sdk.web.base_client import BaseClient  # noqa: PLC0415

    if getattr(BaseClient.api_call, "_metered", False):
        return
    original = BaseClient.api_call

    def api_call(self, api_method, *args, **kwargs):  # noqa: ANN001
        start = time.perf_counter()
        result = "ok"
        try:
            return original(self, api_method, *args, **kwargs)
        except SlackApiError as exc:
            status = getattr(exc.response, "status_code", 0)
            error = exc.response.get("error") if hasattr(exc.response, "get") else ""
            result = "rate_limited" if status == 429 or error == "ratelimited" else "error"
            raise
        except Exception:
            result = "error"
            raise
        finally:
            record_slack_call(api_method, result, time.perf_counter() - start)

    api_call._metered = True
    BaseClient.api_call = api_call


def _count_active_workspaces() -> int:
    import src.core.db as db  # noqa: PLC0415

    return db.count_installations()


class _ActiveWorkspaces:
    """Read the active install count from the database at scrape time."""

    def collect(self):
        # The scrape has no request span, so without this the query became a
        # root "SELECT" trace on every scrape.
        from opentelemetry.instrumentation.utils import suppress_instrumentation  # noqa: PLC0415

        try:
            with suppress_instrumentation():
                count = _count_active_workspaces()
        except Exception as exc:
            logger.warning("metrics: could not count active workspaces: %s", exc)
            return
        yield GaugeMetricFamily("morgenruf_active_workspaces", "Workspaces with the app installed", value=count)


def registry() -> CollectorRegistry:
    reg = CollectorRegistry()
    multiprocess.MultiProcessCollector(reg)
    reg.register(_ActiveWorkspaces())
    return reg


def start_server(port: int | None = None):  # noqa: ANN201
    """Serve /metrics on its own port. METRICS_PORT=0 turns it off."""
    port = int(os.environ.get("METRICS_PORT", "9090")) if port is None else port
    if not port:
        return None
    server, _ = start_http_server(port, registry=registry())
    logger.info("Prometheus metrics on port %d", port)
    return server


def mark_process_dead(pid: int) -> None:
    """gunicorn child_exit hook: drop a dead worker's live gauges."""
    multiprocess.mark_process_dead(pid)
