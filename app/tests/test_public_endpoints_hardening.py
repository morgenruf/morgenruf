"""The endpoints anyone can call: the public feed, email links, the OAuth
callback and MCP. They show only what is already public, are rate limited,
and a request body has a ceiling."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import slack_sdk
import src.core.dashboard as dashboard
from src.core import rate_limit
from src.core.rate_limit import RateLimiter

from tests.browser_fixtures import create_test_app

FEED = "/api/public/feed/public-browser-feed"


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setattr(dashboard, "_CHANNEL_PUBLIC_CACHE", {})
    app = create_test_app(monkeypatch)
    return app, app.test_client(), app.extensions["browser_test_data"]


# The feed.


def test_the_feed_leaves_out_private_channel_standups(browser):
    _, client, state = browser
    state.channels.append({"id": "C_SECRET", "name": "leadership", "is_private": True})
    state.schedules.append({**state.schedules[0], "id": 2, "channel_id": "C_SECRET"})
    state.responses.append({**state.responses[0], "id": 2, "today": "Confidential reorg", "schedule_id": 2})
    state.responses.append({**state.responses[0], "id": 3, "today": "Legacy row", "schedule_id": None})
    body = client.get(FEED).get_data(as_text=True)
    assert "Finish the API contract" in body
    assert "Confidential reorg" not in body
    assert "Legacy row" not in body


def test_a_channel_that_cannot_be_checked_counts_as_private(browser, monkeypatch):
    _, client, _ = browser

    def broken(self, channel):
        raise RuntimeError("slack down")

    monkeypatch.setattr(slack_sdk.WebClient, "conversations_info", broken)
    assert client.get(FEED).json["standups"] == []


def test_the_feed_token_is_for_workspace_admins_only(browser):
    _, client, _ = browser
    client.post("/__test__/session?role=member")
    assert client.get("/dashboard/api/standups").json[0]["feed_token"] == ""
    client.post("/__test__/session?role=standup-admin")
    assert client.get("/dashboard/api/standups").json[0]["feed_token"] == ""
    client.post("/__test__/session?role=admin")
    assert client.get("/dashboard/api/standups").json[0]["feed_token"] == "public-browser-feed"


def test_a_workspace_admin_cannot_choose_the_feed_token(browser):
    app, client, state = browser
    csrf = client.post("/__test__/session?role=admin").json["csrf_token"]
    standup = client.get("/dashboard/api/standups").json[0]
    client.put(
        f"/dashboard/api/standups/{standup['id']}",
        json={**{k: standup[k] for k in ("name", "channel_id", "questions")}, "feed_token": "abc"},
        headers={"X-CSRF-Token": csrf},
    )
    assert state.workspace["feed_token"] == "public-browser-feed"


def test_the_feed_is_rate_limited(browser):
    _, client, _ = browser
    for _ in range(rate_limit.FEED.limit):
        assert client.get("/api/public/feed/bad-token").status_code == 404
    response = client.get("/api/public/feed/bad-token")
    assert response.status_code == 429
    assert response.headers["Retry-After"]


# Other unauthenticated endpoints.


def test_email_links_are_rate_limited(browser):
    _, client, _ = browser
    for _ in range(rate_limit.EMAIL_LINKS.limit):
        assert client.get("/email/unsubscribe?e=a@example.com&t=bad").status_code == 303
    assert client.get("/email/unsubscribe?e=a@example.com&t=bad").status_code == 429
    assert client.get("/email/subscribe?e=a@example.com&t=bad").status_code == 429


def test_the_oauth_callback_is_rate_limited(browser):
    _, client, _ = browser
    for _ in range(rate_limit.OAUTH_CALLBACK.limit):
        assert client.get("/oauth/callback?state=bad").status_code == 303
    assert client.get("/oauth/callback?state=bad").status_code == 429


def _mcp_app():
    from flask import Flask
    from src.modules.mcp.http import mcp_bp

    app = Flask(__name__)
    app.register_blueprint(mcp_bp)
    return app.test_client()


def test_mcp_auth_failures_are_rate_limited_and_good_keys_are_not():
    import src.modules.mcp.http as mcp_http

    client = _mcp_app()
    with patch.object(mcp_http.db, "verify_mcp_key", side_effect=lambda k: "T1" if k == "good" else None) as verify:
        for _ in range(rate_limit.MCP_AUTH_FAILURES.limit + 5):
            assert (
                client.post("/mcp", json={"method": "ping"}, headers={"Authorization": "Bearer good"}).status_code
                == 200
            )
        for _ in range(rate_limit.MCP_AUTH_FAILURES.limit):
            assert client.post("/mcp", json={}, headers={"Authorization": "Bearer bad"}).status_code == 401
        looked_up = verify.call_count
        assert client.post("/mcp", json={}, headers={"Authorization": "Bearer bad"}).status_code == 429
        # Refused before the database is asked.
        assert verify.call_count == looked_up


def test_a_request_body_has_a_ceiling(browser):
    app, client, _ = browser
    assert app.config["MAX_CONTENT_LENGTH"] == 4 * 1024 * 1024
    csrf = client.post("/__test__/session?role=admin").json["csrf_token"]
    response = client.post(
        "/dashboard/api/profiles/import",
        data=b'{"csv": "' + b"a" * (5 * 1024 * 1024) + b'"}',
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    )
    assert response.status_code == 413


# The limiter itself.


def test_the_limiter_forgets_old_hits(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    limiter = RateLimiter(limit=2, window=60)
    assert limiter.hit("a") and limiter.hit("a")
    assert not limiter.hit("a")
    assert limiter.hit("b")
    now[0] += 61
    assert limiter.hit("a")


def test_the_limiter_bounds_its_memory(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX_KEYS", 5)
    limiter = RateLimiter(limit=1, window=60)
    for i in range(50):
        limiter.hit(f"k{i}")
    assert len(limiter._hits) <= 5
