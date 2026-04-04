"""Standup bot — multi-workspace entry point."""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, jsonify

from installation_store import PostgresInstallationStore
from handlers import register_handlers
from scheduler import build_scheduler
from oauth import oauth_bp
from dashboard import dashboard_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_workspace_jobs() -> list[tuple[str, str, dict]]:
    """Load all active installations and their configs from DB."""
    try:
        import db  # noqa: PLC0415
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


def create_app() -> tuple[App, Flask]:
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    installation_store = PostgresInstallationStore()

    slack_app = App(
        signing_secret=signing_secret,
        installation_store=installation_store,
    )

    register_handlers(slack_app)

    workspace_jobs = _load_workspace_jobs()
    scheduler = build_scheduler(workspace_jobs)
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    flask_app = Flask(__name__)
    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key:
        logger.warning("FLASK_SECRET_KEY not set — using random key (sessions will not persist across restarts)")
        secret_key = os.urandom(32)
    flask_app.secret_key = secret_key
    flask_app.config["SESSION_COOKIE_SECURE"] = True
    flask_app.config["SESSION_COOKIE_HTTPONLY"] = True
    flask_app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    flask_app.register_blueprint(oauth_bp)
    flask_app.register_blueprint(dashboard_bp)

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
    flask_app.run(host="0.0.0.0", port=port)
