"""Morgenruf Slack app entry point."""

from __future__ import annotations

import logging
import os

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from .handlers import register_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

register_handlers(app)

handler = SlackRequestHandler(app)
