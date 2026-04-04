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


def _persist_standup(team_id: str, user_id: str, answers: list[str]) -> None:
    """Best-effort persist to DB; log and continue on failure."""
    try:
        import db  # noqa: PLC0415
        db.save_standup(
            team_id=team_id,
            user_id=user_id,
            yesterday=answers[0],
            today=answers[1],
            blockers=answers[2],
        )
    except Exception as exc:
        logger.warning("Could not persist standup for %s/%s: %s", team_id, user_id, exc)


def register_handlers(app: App) -> None:
    """Register all Slack event handlers."""

    @app.event("message")
    def handle_dm(event, say, client, logger):  # noqa: ANN001
        """Handle incoming DMs — collect standup answers step by step."""
        if event.get("channel_type") != "im":
            return
        if event.get("subtype"):
            return

        user_id: str = event["user"]
        team_id: str = event.get("team", "")
        text: str = event.get("text", "").strip()
        cache_key = f"{team_id}:{user_id}"

        session = state_store.get(cache_key)
        if not session:
            return

        session = state_store.record_answer(cache_key, text)

        if session.step < len(QUESTIONS):
            say(QUESTIONS[session.step])
        else:
            say("✅ Thanks! Your standup has been posted.")

            formatted = _format_standup(user_id, session.answers)
            channel = session.channel

            if channel:
                try:
                    client.chat_postMessage(channel=channel, text=formatted)
                    logger.info("Posted standup for %s to %s", user_id, channel)
                except Exception as exc:
                    logger.error("Failed to post standup for %s: %s", user_id, exc)
                    say(f"⚠️ Could not post to channel — please paste manually:\n\n{formatted}")

            _persist_standup(session.team_id, user_id, session.answers)
            state_store.clear(cache_key)

    @app.event("app_mention")
    def handle_mention(event, say):  # noqa: ANN001
        say("👋 I'm the standup bot! I'll DM you at your team's standup time. Type `help` in a DM to me for more info.")

    @app.message("help")
    def handle_help(message, say):  # noqa: ANN001
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
    def handle_manual_standup(message, say, client):  # noqa: ANN001
        """Allow team members to trigger their own standup manually."""
        if message.get("channel_type") != "im":
            return
        user_id: str = message["user"]
        team_id: str = message.get("team", "")
        cache_key = f"{team_id}:{user_id}"

        if state_store.is_active(cache_key):
            say("You already have an active standup session. Answer the current question or wait for it to reset.")
            return

        # Look up the configured channel for this workspace
        channel = ""
        try:
            import db  # noqa: PLC0415
            config = db.get_workspace_config(team_id) or {}
            channel = config.get("channel_id", "")
        except Exception:
            pass

        state_store.start(cache_key, channel, team_id=team_id)
        say(f"📋 Starting your standup!\n\n{QUESTIONS[0]}")
