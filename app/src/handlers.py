"""Standup message handlers — DM conversation and channel posting."""

from __future__ import annotations

import logging
from datetime import datetime

from slack_bolt import App

from state import QUESTIONS, state_store

logger = logging.getLogger(__name__)


def _format_standup(user_id: str, answers: list[str]) -> str:
    """Format collected answers into a structured standup post."""
    date_str = datetime.utcnow().strftime("%B %d, %Y")
    yesterday, today, blockers = answers[0], answers[1], answers[2]

    blocker_text = (
        "_None_ ✅"
        if blockers.strip().lower() in ("none", "no", "nope", "-", "n/a", "")
        else blockers
    )

    return (
        f"📋 *Standup from <@{user_id}>* — {date_str}\n\n"
        f"*✅ Yesterday:*\n{yesterday}\n\n"
        f"*🎯 Today:*\n{today}\n\n"
        f"*🚧 Blockers:*\n{blocker_text}"
    )


def register_handlers(app: App, teams: list[dict]) -> None:
    """Register all Slack event handlers."""

    # Build user_id → team channel map for quick lookup
    user_team_map: dict[str, str] = {}
    for team in teams:
        for member in team.get("members", []):
            user_team_map[member["slack_id"]] = team["channel"]

    @app.event("message")
    def handle_dm(event, say, client, logger):
        """Handle incoming DMs — collect standup answers step by step."""
        # Only handle DMs (channel_type == "im")
        if event.get("channel_type") != "im":
            return
        if event.get("subtype"):
            return  # ignore bot messages, edits, etc.

        user_id = event["user"]
        text = event.get("text", "").strip()

        session = state_store.get(user_id)
        if not session:
            return  # not in an active standup session

        session = state_store.record_answer(user_id, text)

        if session.step < len(QUESTIONS):
            # Ask next question
            say(QUESTIONS[session.step])
        else:
            # All 3 answers collected — post to team channel
            say("✅ Thanks! Your standup has been posted.")

            channel = user_team_map.get(user_id, session.team)
            formatted = _format_standup(user_id, session.answers)

            try:
                client.chat_postMessage(channel=channel, text=formatted)
                logger.info("Posted standup for %s to %s", user_id, channel)
            except Exception as e:
                logger.error("Failed to post standup for %s: %s", user_id, e)
                say(f"⚠️ Could not post to channel — please paste manually:\n\n{formatted}")

            state_store.clear(user_id)

    @app.event("app_mention")
    def handle_mention(event, say):
        say("👋 I'm the standup bot! I'll DM you at your team's standup time. Type `help` in a DM to me for more info.")

    @app.message("help")
    def handle_help(message, say):
        if message.get("channel_type") != "im":
            return
        say(
            "🤖 *Standup Bot Help*\n\n"
            "I'll DM you at your scheduled standup time with 3 questions:\n"
            "1. What did you complete yesterday? _(list by project)_\n"
            "2. What are you working on today? _(list by project)_\n"
            "3. Any blockers?\n\n"
            "*Format tip:* prefix each item with your project name:\n"
            "> `Proj-Bridj: deployed Terraform module`\n"
            "> `Proj-Isec: reviewed IAM policies`\n\n"
            "This lets Jarvis generate per-project reports automatically. 🚀"
        )

    @app.message("standup")
    def handle_manual_standup(message, say, client):
        """Allow team members to trigger their own standup manually."""
        if message.get("channel_type") != "im":
            return
        user_id = message["user"]

        if state_store.is_active(user_id):
            say("You already have an active standup session. Answer the current question or wait for it to reset.")
            return

        team_channel = user_team_map.get(user_id, "")
        session = state_store.start(user_id, team_channel)
        say(f"📋 Starting your standup!\n\n{QUESTIONS[0]}")
