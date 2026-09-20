"""HTTP application construction without Slack clients, jobs, or network I/O."""

from __future__ import annotations

import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from src.core.api import init_api, install_browser_security, register_api_blueprint


def create_http_app(*, modules=None, schema_only=False):
    app = Flask(__name__, static_folder=None)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY")
        or ("schema-export-does-not-serve-requests" if schema_only else None),
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "true").lower() not in {"false", "0", "no"},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    init_api(app)
    install_browser_security(app)
    from src.core.dashboard import browser_bp, dashboard_bp
    from src.core.oauth import oauth_bp

    register_api_blueprint(app, dashboard_bp)
    app.register_blueprint(browser_bp)
    app.register_blueprint(oauth_bp)
    if modules is None:
        from src.core.modules import deploy_allowlist
        from src.modules import REGISTRY

        allowlist = None if schema_only else deploy_allowlist()
        modules = [spec for spec in REGISTRY if allowlist is None or spec.name in allowlist]
    for spec in modules:
        if spec.register_routes is not None:
            spec.register_routes(app)
    return app
