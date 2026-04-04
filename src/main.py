"""Standup bot — entry point."""

from __future__ import annotations

import logging
import os
import sys

# Add src to path when running directly
sys.path.insert(0, os.path.dirname(__file__))

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

from config import get_slack_tokens, get_port, load_teams
from handlers import register_handlers
from scheduler import build_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> tuple[App, Flask]:
    bot_token, signing_secret = get_slack_tokens()

    slack_app = App(token=bot_token, signing_secret=signing_secret)
    teams = load_teams()

    register_handlers(slack_app, teams)

    # Start scheduler
    scheduler = build_scheduler(slack_app.client, teams)
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    # Flask adapter for Slack HTTP events
    flask_app = Flask(__name__)
    handler = SlackRequestHandler(slack_app)

    @flask_app.route("/slack/events", methods=["POST"])
    def slack_events():
        return handler.handle(request)

    @flask_app.route("/healthz", methods=["GET"])
    def healthz():
        return {"status": "ok", "jobs": len(scheduler.get_jobs())}, 200

    return slack_app, flask_app


if __name__ == "__main__":
    _, flask_app = create_app()
    port = get_port()
    logger.info("Starting standup bot on port %d", port)
    flask_app.run(host="0.0.0.0", port=port)
