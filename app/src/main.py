"""Standup bot — multi-workspace entry point."""

from __future__ import annotations

import logging
import os

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            FlaskIntegration(),
            LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
        ],
        traces_sample_rate=0.1,
        environment=os.environ.get("SENTRY_ENV", "production"),
    )
    logging.getLogger(__name__).info("Sentry error monitoring enabled")

from flask import Flask, jsonify, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_bolt.oauth.oauth_settings import OAuthSettings

from src.core.dm_router import DMContext, route_dm
from src.core.installation_store import PostgresInstallationStore
from src.core.modules import active_modules, deploy_allowlist
from src.core.scheduler import build_scheduler
from src.modules import REGISTRY

log_level = logging.DEBUG if os.environ.get("LOG_LEVEL", "").upper() == "DEBUG" else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_workspace_jobs() -> list[tuple[str, str, dict]]:
    """Load all active installations and their configs from DB."""
    try:
        import src.core.db as db  # noqa: PLC0415

        installations = db.get_all_installations()
        jobs = []
        for inst in installations:
            config = db.get_workspace_config(inst["team_id"]) or {}
            if config.get("active", True):
                jobs.append((inst["team_id"], inst["bot_token"], config))
        return jobs
    except Exception as exc:
        logger.warning("Could not load workspace jobs from DB: %s", exc)
        return []


def _is_dev_mode() -> bool:
    return bool(os.environ.get("FLASK_DEBUG")) or os.environ.get("LOG_LEVEL", "").upper() == "DEBUG"


def _resolve_secret_key() -> bytes | str:
    """Return the signing key, or refuse to start.

    FLASK_SECRET_KEY signs the Flask session, the Slack OAuth state parameter
    and the dashboard login token. Running without it used to log a warning and
    carry on with a random key, which is safe for the session but meant a
    restart silently invalidated every in-flight login, and it let a deployment
    reach production with nobody noticing the variable was never set.

    app/.env.example ships the variable empty, so the path of least resistance
    for a self-hoster was to leave it that way. Refusing to boot makes that
    impossible to miss. Dev keeps the old behaviour so a local checkout still
    runs with no setup.
    """
    key = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if key:
        if len(key) < 32:
            logger.warning(
                "FLASK_SECRET_KEY is %d characters. Use at least 32: openssl rand -hex 32",
                len(key),
            )
        return key

    if _is_dev_mode():
        logger.warning("FLASK_SECRET_KEY not set, using a random key for this process (development only)")
        return os.urandom(32)

    raise RuntimeError(
        "FLASK_SECRET_KEY is not set. It signs dashboard login tokens, so the app "
        "will not start without it. Generate one with: openssl rand -hex 32"
    )


def register_modules(flask_app, bolt_app, registry) -> list[str]:
    """Wire each module's routes and Slack listeners. Returns registered names.

    A module that raises during registration is logged and skipped, so one bad
    module cannot stop the process from starting.
    """
    registered: list[str] = []
    for spec in registry:
        try:
            if spec.register_routes is not None:
                spec.register_routes(flask_app)
            if spec.register_slack is not None:
                spec.register_slack(bolt_app)
        except Exception:
            logger.exception("failed to register module %s", spec.name)
            continue
        registered.append(spec.name)
    return registered


def _enabled_modules():
    """Registry members this deployment permits, before per-workspace gating."""
    allowlist = deploy_allowlist()
    return [s for s in REGISTRY if allowlist is None or s.name in allowlist]


def register_dm_listener(bolt_app) -> None:
    """Own the single catch-all message.im listener for every module.

    Bolt fires every matching listener, so two modules registering their own
    catch-all would both process the same DM. Modules expose claim_dm instead
    and this offers each message to them in registry order.
    """

    @bolt_app.event("message")
    def handle_dm(event, client, logger):  # noqa: ANN001
        if event.get("channel_type") != "im" or event.get("bot_id"):
            return
        team_id = event.get("team") or ""
        ctx = DMContext(
            team_id=team_id,
            user_id=event.get("user", ""),
            channel_id=event.get("channel", ""),
            text=(event.get("text") or "").strip(),
            event=event,
            client=client,
        )
        import src.core.db as db  # noqa: PLC0415

        modules = active_modules(
            _enabled_modules(),
            granted_scopes=db.granted_scopes(team_id),
            settings=db.module_settings(team_id),
            allowlist=None,
        )
        route_dm(modules, ctx, fallback=None)


def create_app() -> tuple[App, Flask]:
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    client_id = os.environ.get("SLACK_CLIENT_ID", "")
    client_secret = os.environ.get("SLACK_CLIENT_SECRET", "")
    installation_store = PostgresInstallationStore()

    oauth_settings = None
    if client_id and client_secret:
        oauth_settings = OAuthSettings(
            client_id=client_id,
            client_secret=client_secret,
            installation_store=installation_store,
        )

    slack_app = App(
        signing_secret=signing_secret,
        installation_store=installation_store,
        oauth_settings=oauth_settings,
    )

    register_dm_listener(slack_app)

    workspace_jobs = _load_workspace_jobs()
    scheduler = build_scheduler(workspace_jobs)
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    from src.http_app import create_http_app

    flask_app = create_http_app(modules=[])
    flask_app.secret_key = _resolve_secret_key()
    registered = register_modules(flask_app, slack_app, _enabled_modules())
    logger.info("Modules registered: %s", ", ".join(registered) or "none")

    handler = SlackRequestHandler(slack_app)

    @flask_app.route("/slack/events", methods=["POST"])
    def slack_events():
        return handler.handle(request)

    @flask_app.route("/slack/interactions", methods=["POST"])
    def slack_interactions():
        return handler.handle(request)

    @flask_app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok", "jobs": len(scheduler.get_jobs())}), 200

    return slack_app, flask_app


if __name__ == "__main__":
    _, flask_app = create_app()
    port = int(os.environ.get("PORT", "3000"))
    logger.info("Starting standup bot on port %d", port)

    # Use gunicorn in production, Flask dev server only when DEBUG
    if os.environ.get("FLASK_DEBUG") or os.environ.get("LOG_LEVEL", "").upper() == "DEBUG":
        flask_app.run(host="0.0.0.0", port=port, debug=True)
    else:
        from gunicorn.app.base import BaseApplication

        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        StandaloneApplication(
            flask_app,
            {
                "bind": f"0.0.0.0:{port}",
                "workers": 1,
                "threads": 4,
                "timeout": 120,
                "accesslog": "-",
                "errorlog": "-",
                "loglevel": "info",
            },
        ).run()
