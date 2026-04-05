"""Standup message handlers — DM conversation and channel posting."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone, timedelta

import requests
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


def fire_webhooks(team_id: str, event_type: str, payload: dict) -> None:
    """POST payload to every registered webhook for team_id.

    Adds ``X-Morgenruf-Event`` and (when a secret is configured)
    ``X-Morgenruf-Signature`` headers to each request.
    Failures are logged but never raised so they can't break the main flow.
    """
    try:
        import db  # noqa: PLC0415
        webhooks = db.get_webhooks(team_id)
    except Exception as exc:
        logger.warning("Could not fetch webhooks for %s: %s", team_id, exc)
        return

    if not webhooks:
        return

    body = json.dumps(payload, default=str).encode()

    for hook in webhooks:
        events: list[str] = hook.get("events") or ["standup.completed"]
        if event_type not in events:
            continue

        headers = {
            "Content-Type": "application/json",
            "X-Morgenruf-Event": event_type,
        }

        secret: str | None = hook.get("secret")
        if secret:
            sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Morgenruf-Signature"] = f"sha256={sig}"

        try:
            resp = requests.post(hook["webhook_url"], data=body, headers=headers, timeout=10)
            logger.info(
                "Webhook %s fired for %s → HTTP %s",
                hook["webhook_url"], event_type, resp.status_code,
            )
        except Exception as exc:
            logger.warning("Webhook delivery failed for %s: %s", hook["webhook_url"], exc)


def can_edit_response(team_id: str, user_id: str, standup_id: int) -> bool:
    """Return True if the user is still within their edit window.

    The edit window is controlled by ``edit_window_hours`` in workspace_config:
      * ``0``    — editable until the report time (treated as no time limit here)
      * positive — that many hours after submission
      * ``None`` — no limit
    """
    try:
        import db  # noqa: PLC0415
        standup = db.get_standup_by_id(standup_id)
        if not standup:
            return False
        if standup["user_id"] != user_id or standup["team_id"] != team_id:
            return False

        config = db.get_workspace_config(team_id) or {}
        edit_window_hours = config.get("edit_window_hours", 4)

        if edit_window_hours is None:
            return True
        if edit_window_hours == 0:
            return True

        submitted_at: datetime = standup["submitted_at"]
        if submitted_at.tzinfo is None:
            submitted_at = submitted_at.replace(tzinfo=timezone.utc)
        cutoff = submitted_at + timedelta(hours=edit_window_hours)
        return datetime.now(tz=timezone.utc) <= cutoff

    except Exception as exc:
        logger.warning("can_edit_response check failed for %s/%s: %s", team_id, user_id, exc)
        return False


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

            # Fire standup.completed webhooks
            fire_webhooks(session.team_id, "standup.completed", {
                "team_id": session.team_id,
                "user_id": user_id,
                "answers": {
                    "yesterday": session.answers[0],
                    "today": session.answers[1],
                    "blockers": session.answers[2],
                },
                "timestamp": datetime.utcnow().isoformat(),
            })

    @app.event("app_home_opened")
    def handle_app_home(event, client):  # noqa: ANN001
        """Render the App Home tab when a user opens it."""
        user_id = event["user"]
        team_id = event.get("team", "")

        workspace_name = ""
        channel_name = ""
        standup_time = ""
        try:
            import db  # noqa: PLC0415
            config = db.get_workspace_config(team_id) or {}
            channel_name = config.get("channel_id", "")
            standup_time = config.get("standup_time", "")
            info = client.team_info()
            workspace_name = info.get("team", {}).get("name", "")
        except Exception:
            pass

        status_text = (
            f"✅ Active — posting to <#{channel_name}> at *{standup_time}*"
            if channel_name and standup_time
            else "⚠️ Not configured — visit the dashboard to set up your standup."
        )

        try:
            client.views_publish(
                user_id=user_id,
                view={
                    "type": "home",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "☀️ Morgenruf Standup Bot"},
                        },
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"*Workspace:* {workspace_name or team_id}\n"
                                    f"*Status:* {status_text}"
                                ),
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Quick actions*\nSend me `standup` in a DM to start your standup manually.",
                            },
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "🔧 Open Dashboard"},
                                    "url": "https://api.morgenruf.dev/dashboard",
                                    "action_id": "open_dashboard",
                                }
                            ],
                        },
                    ],
                },
            )
        except Exception as exc:
            logger.warning("Failed to publish App Home for %s: %s", user_id, exc)

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
            "1. What did you complete yesterday?\n"
            "2. What are you working on today?\n"
            "3. Any blockers?\n\n"
            "Type `standup` here anytime to start a standup manually. 🚀"
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

    @app.action("standup_edit")
    def handle_standup_edit(ack, body, say, client):  # noqa: ANN001
        """Handle 'Edit my standup' button — re-open DM session for edits."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body.get("team", {}).get("id", "")
        standup_id_str: str = body.get("actions", [{}])[0].get("value", "")

        try:
            standup_id = int(standup_id_str)
        except (ValueError, TypeError):
            say("⚠️ Could not identify your standup. Please try again.")
            return

        if not can_edit_response(team_id, user_id, standup_id):
            say("⏰ Sorry, the edit window for your standup has closed.")
            return

        cache_key = f"{team_id}:{user_id}"
        channel = ""
        try:
            import db  # noqa: PLC0415
            config = db.get_workspace_config(team_id) or {}
            channel = config.get("channel_id", "")
        except Exception:
            pass

        state_store.start(cache_key, channel, team_id=team_id)
        say(f"✏️ Let's update your standup!\n\n{QUESTIONS[0]}")
