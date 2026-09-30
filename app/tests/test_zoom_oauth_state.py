"""The Zoom OAuth state is bound to the browser that started the flow and
works once. A signed state alone let someone finish another person's flow
with their own code (linking their Zoom to the victim), or replay it."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from tests.browser_fixtures import create_test_app


@pytest.fixture
def app(monkeypatch):
    import src.modules.connect.zoom as zoom

    app = create_test_app(monkeypatch)
    monkeypatch.setattr(zoom, "authorize_url", lambda state: "https://zoom.example.test/auth?state=" + state)
    stored = []
    monkeypatch.setattr(zoom, "exchange_code", lambda code: {"refresh_token": "r", "access_token": "a"})
    monkeypatch.setattr(zoom, "store_from_token_response", lambda *args: stored.append(args))
    monkeypatch.setattr(zoom, "whoami", lambda token: None)
    app.stored = stored
    return app


def _start(client):
    from src.modules.connect.zoom_routes import mint_link_token

    with client.application.test_request_context():
        link = mint_link_token("T_BROWSER", "U_MEMBER")
    location = client.get(f"/connect/zoom/start?t={link}").location
    return parse_qs(urlparse(location).query)["state"][0]


def test_the_browser_that_started_can_finish_once(app):
    client = app.test_client()
    state = _start(client)
    first = client.get(f"/connect/zoom/callback?state={state}&code=c1")
    assert first.location == "/connect/zoom/result?status=connected"
    assert len(app.stored) == 1
    again = client.get(f"/connect/zoom/callback?state={state}&code=c2")
    assert again.location == "/connect/zoom/result?status=invalid"
    assert len(app.stored) == 1


def test_another_browser_cannot_finish_it(app):
    state = _start(app.test_client())
    other = app.test_client()
    response = other.get(f"/connect/zoom/callback?state={state}&code=attacker")
    assert response.location == "/connect/zoom/result?status=invalid"
    assert app.stored == []


def test_a_link_token_is_not_a_callback_state(app):
    """The Slack button's token is signed the same way but has no nonce."""
    from src.modules.connect.zoom_routes import mint_link_token

    client = app.test_client()
    _start(client)
    with app.test_request_context():
        link = mint_link_token("T_BROWSER", "U_MEMBER")
    response = client.get(f"/connect/zoom/callback?state={link}&code=c")
    assert response.location == "/connect/zoom/result?status=invalid"
    assert app.stored == []
