"""The browser has its own application; Flask owns only data and actions.

Rendered layout, navigation, permissions, themes, forms, and downloads are
exercised in frontend/e2e/application.spec.ts against the real HTTP contract.
"""

from pathlib import Path

from tests.browser_fixtures import create_test_app

APP = Path(__file__).resolve().parents[1]


def test_backend_no_longer_ships_the_legacy_browser_application():
    assert not (APP / "src/core/templates").exists()
    assert not (APP / "src/static").exists()


def test_spa_routes_and_assets_are_not_served_by_flask(monkeypatch):
    app = create_test_app(monkeypatch)
    client = app.test_client()
    for path in (
        "/dashboard/",
        "/dashboard/login",
        "/dashboard/standups",
        "/feed/public-browser-feed",
        "/auth/result",
        "/static/logo.png",
    ):
        assert client.get(path).status_code == 404


def test_bootstrap_uses_the_configured_deployment_for_mcp(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://team.example.test/")
    app = create_test_app(monkeypatch)
    client = app.test_client()
    client.post("/__test__/session")
    assert client.get("/dashboard/api/me").json["mcp_endpoint"] == "https://team.example.test/mcp"


def test_frontend_preserves_public_asset_urls():
    assets = APP.parent / "frontend/public/static"
    for name in ("favicon.ico", "favicon.png", "icon-192.png", "icon-512.png", "kudos-token-128.png", "logo.png"):
        assert (assets / name).stat().st_size > 0
