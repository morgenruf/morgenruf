"""Standup bot — multi-workspace entry point."""

from __future__ import annotations

import logging
import os
import threading
import time
from multiprocessing.sharedctypes import RawValue

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
# slack_sdk logs every API request and response at DEBUG, including OAuth
# token exchanges and refreshes, so LOG_LEVEL=DEBUG would write live bot and
# refresh tokens into the logs.
logging.getLogger("slack_sdk").setLevel(max(log_level, logging.INFO))


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
    """Only FLASK_DEBUG means development.

    LOG_LEVEL=DEBUG used to count too, and the chart suggests it for verbose
    logs during an incident. That turned a production pod into Flask's debug
    server and let it boot without FLASK_SECRET_KEY.
    """
    return bool(os.environ.get("FLASK_DEBUG"))


def _resolve_signing_secret() -> str:
    """Return SLACK_SIGNING_SECRET, or a random one when it is unset.

    Bolt accepts an empty signing secret, and a signature computed with an
    empty key is one anyone can compute, so every request to /slack/events
    could be forged. A random secret makes every signature fail instead:
    Slack features stay off until the variable is set, and nothing is
    forgeable meanwhile.
    """
    secret = os.environ.get("SLACK_SIGNING_SECRET", "").strip()
    if secret:
        return secret
    logger.error("SLACK_SIGNING_SECRET is not set. Slack requests will be rejected until it is.")
    return os.urandom(32).hex()


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


def register_slack_listeners(flask_app, bolt_app, modules) -> list[str]:
    """Core's DM listener first, then every module's routes and listeners.

    The order is load bearing: Bolt runs only the first listener matching an
    event, so registering the DM listener first is what makes it the one owner
    of message events. Tests register through here to get the same order.
    """
    register_dm_listener(bolt_app)
    register_channel_join_listener(bolt_app)

    # Core's own Slack surface: /morgenruf and the member profile modal.
    from src.core.profile_slack import register_slack as register_profile_slack

    register_profile_slack(bolt_app)
    return register_modules(flask_app, bolt_app, modules)


def _enabled_modules():
    """Registry members this deployment permits, before per-workspace gating."""
    allowlist = deploy_allowlist()
    return [s for s in REGISTRY if allowlist is None or s.name in allowlist]


def register_dm_listener(bolt_app) -> None:
    """Own the single catch-all message.im listener for every module.

    Bolt runs only the first listener matching an event, and this one matches
    every message, so it must be the only message listener that does real
    work. Modules expose claim_dm_command and claim_dm instead, and this offers
    each DM to them in registry order (see core.dm_router).
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


def dispatch_channel_join(modules, event: dict, client) -> list[str]:
    """Offer one member_joined_channel event to every module hook, in order.

    One hook failing must not stop the next. Returns the names called, for
    tests and logs.
    """
    called: list[str] = []
    for spec in modules:
        hook = getattr(spec, "on_channel_join", None)
        if hook is None:
            continue
        try:
            hook(event, client)
            called.append(spec.name)
        except Exception:
            logger.exception("module %s failed to handle a channel join", spec.name)
    return called


def register_channel_join_listener(bolt_app) -> None:
    """Own the single member_joined_channel listener for every module.

    Bolt runs only the first listener that matches an event. Standup and
    Connect each registered one, so Connect's welcome never ran; a third from
    Celebrations would not have either. Modules expose on_channel_join and
    this calls each of them.

    Every module the deployment permits is offered the event, not only those
    active for the workspace, because standup's welcome has always run
    regardless of the workspace's module toggles and must keep doing so. Each
    hook checks for itself whether the channel matters to it.
    """

    @bolt_app.event("member_joined_channel")
    def handle_member_joined_channel(event, client):  # noqa: ANN001
        dispatch_channel_join(_enabled_modules(), event, client)


def create_app() -> tuple[App, Flask]:
    signing_secret = _resolve_signing_secret()
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

    workspace_jobs = _load_workspace_jobs()
    scheduler = build_scheduler(workspace_jobs)
    scheduler.start()
    _start_scheduler_beat(scheduler)
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    from src.http_app import create_http_app

    flask_app = create_http_app(modules=[])
    flask_app.secret_key = _resolve_secret_key()
    registered = register_slack_listeners(flask_app, slack_app, _enabled_modules())
    logger.info("Modules registered: %s", ", ".join(registered) or "none")

    handler = SlackRequestHandler(slack_app)

    @flask_app.route("/slack/events", methods=["POST"])
    def slack_events():
        return handler.handle(request)

    @flask_app.route("/slack/interactions", methods=["POST"])
    def slack_interactions():
        return handler.handle(request)

    @flask_app.route("/livez", methods=["GET"])
    def livez():
        # Liveness restarts the pod, so it checks only what a restart fixes: a
        # dead scheduler thread. A database outage must not crash-loop the pod.
        ok = _scheduler_alive(scheduler)
        return jsonify({"status": "ok" if ok else "error", "scheduler": ok}), 200 if ok else 503

    @flask_app.route("/healthz", methods=["GET"])
    def healthz():
        # Readiness and the status page. It used to return 200 unconditionally,
        # so the status page showed the database and scheduler green while
        # either was down.
        sched_ok = _scheduler_alive(scheduler)
        db_ok = _database_reachable()
        ok = sched_ok and db_ok
        body = {
            "status": "ok" if ok else "error",
            "scheduler": sched_ok,
            "db": db_ok,
            "jobs": len(scheduler.get_jobs()) if sched_ok else 0,
        }
        return jsonify(body), 200 if ok else 503

    return slack_app, flask_app


# The scheduler starts in gunicorn's master process, before the worker is
# forked, and its jobs run there. The worker that answers /livez holds only a
# forked copy whose thread never existed in that process, so checking the
# thread from the worker always reported it dead. The master instead writes a
# timestamp into memory shared with the worker, and the worker checks its age.
_SCHEDULER_BEAT = RawValue("d", 0.0)
_BEAT_EVERY_SECONDS = 5
_BEAT_STALE_AFTER_SECONDS = 60
_scheduler_pid: int | None = None


def _scheduler_thread_alive(scheduler) -> bool:  # noqa: ANN001
    if not scheduler.running:
        return False
    thread = getattr(scheduler, "_thread", None)
    return thread is None or thread.is_alive()


def _start_scheduler_beat(scheduler) -> None:  # noqa: ANN001
    global _scheduler_pid
    _scheduler_pid = os.getpid()

    def beat() -> None:
        while _scheduler_thread_alive(scheduler):
            _SCHEDULER_BEAT.value = time.time()
            time.sleep(_BEAT_EVERY_SECONDS)

    _SCHEDULER_BEAT.value = time.time()
    threading.Thread(target=beat, name="scheduler-beat", daemon=True).start()


def _scheduler_alive(scheduler) -> bool:  # noqa: ANN001
    """True while the scheduler is running and its thread has not died."""
    if _scheduler_pid is None or _scheduler_pid == os.getpid():
        return _scheduler_thread_alive(scheduler)
    # A forked worker: trust the master's beat instead of the local copy.
    return time.time() - _SCHEDULER_BEAT.value < _BEAT_STALE_AFTER_SECONDS


def _database_reachable() -> bool:
    try:
        import src.core.db as db  # noqa: PLC0415

        with db.db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception as exc:
        logger.warning("Health check could not reach the database: %s", exc)
        return False


if __name__ == "__main__":
    _, flask_app = create_app()
    port = int(os.environ.get("PORT", "3000"))
    logger.info("Starting standup bot on port %d", port)

    # Use gunicorn in production, Flask dev server only with FLASK_DEBUG
    if _is_dev_mode():
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
