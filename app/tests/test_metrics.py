"""Prometheus metrics: the /metrics server, route templates, Slack and job counters."""

from __future__ import annotations

import threading
import time
import urllib.request

import pytest
from prometheus_client import start_http_server
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.web.base_client import BaseClient
from slack_sdk.web.slack_response import SlackResponse
from src.core import metrics


def _value(name: str, **labels) -> float:
    return metrics.registry().get_sample_value(name, labels) or 0.0


@pytest.fixture
def scrape(monkeypatch):
    monkeypatch.setattr(metrics, "_count_active_workspaces", lambda: 7)
    server, thread = start_http_server(0, addr="127.0.0.1", registry=metrics.registry())
    yield lambda: urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/metrics").read().decode()
    server.shutdown()
    thread.join()


def test_metrics_endpoint_serves_http_and_build_info(scrape):
    from src.http_app import create_http_app

    app = create_http_app(modules=[], schema_only=True)

    @app.get("/__metrics_test__/<item_id>")
    def item(item_id):
        return "ok"

    client = app.test_client()
    assert client.get("/__metrics_test__/T0SECRET1").status_code == 200
    client.get("/no-such-page")

    body = scrape()
    assert "http_requests_total" in body
    assert "morgenruf_build_info" in body
    assert 'route="/__metrics_test__/<item_id>"' in body
    assert 'route="unmatched"' in body
    assert "T0SECRET1" not in body
    assert "morgenruf_active_workspaces 7.0" in body


@pytest.mark.parametrize(
    ("job_id", "name"),
    [
        ("member_sync", "member_sync"),
        ("standup_T01ABCDEF", "standup"),
        ("report_schedule_T01ABCDEF_7", "report_schedule"),
        ("standup_retry_T01ABCDEF_7_1700000000", "standup_retry"),
        ("connect:T01ABCDEF:round:42", "connect:round"),
        ("watercooler:T01ABCDEF:post:C01:0930:UTC:mon", "watercooler:post"),
    ],
)
def test_job_names_drop_ids(job_id, name):
    assert metrics.job_name(job_id) == name


def test_slack_calls_are_counted_and_messages_attributed_to_the_job(monkeypatch):
    metrics.install_slack_sdk()
    ok = SlackResponse(
        client=None, http_verb="POST", api_url="", req_args={}, data={"ok": True}, headers={}, status_code=200
    )
    limited = SlackResponse(
        client=None,
        http_verb="POST",
        api_url="",
        req_args={},
        data={"ok": False, "error": "ratelimited"},
        headers={},
        status_code=429,
    )

    before_sent = _value("morgenruf_messages_sent_total", kind="connect:round")
    before_limited = _value("morgenruf_slack_api_calls_total", method="users.list", result="rate_limited")

    monkeypatch.setattr(BaseClient, "_sync_send", lambda self, api_url, req_args: ok)
    with metrics.job_context("connect:round"):
        WebClient(token="xoxb-test").chat_postMessage(channel="C1", text="hi")

    def rate_limited(self, api_url, req_args):
        raise SlackApiError("ratelimited", limited)

    monkeypatch.setattr(BaseClient, "_sync_send", rate_limited)
    with pytest.raises(SlackApiError):
        WebClient(token="xoxb-test").users_list()

    assert _value("morgenruf_messages_sent_total", kind="connect:round") == before_sent + 1
    assert _value("morgenruf_slack_api_calls_total", method="users.list", result="rate_limited") == before_limited + 1


def test_scheduler_counts_job_runs():
    from apscheduler.schedulers.background import BackgroundScheduler
    from src.core.scheduler import ClaimingExecutor

    done = threading.Event()
    before = _value("morgenruf_job_runs_total", job="metrics_probe", result="success")
    scheduler = BackgroundScheduler(executors={"default": ClaimingExecutor()})
    scheduler.add_job(done.set, id="metrics_probe")
    scheduler.start()
    try:
        assert done.wait(5)
        for _ in range(50):
            if _value("morgenruf_job_runs_total", job="metrics_probe", result="success") > before:
                break
            time.sleep(0.05)
    finally:
        scheduler.shutdown()
    assert _value("morgenruf_job_runs_total", job="metrics_probe", result="success") == before + 1
