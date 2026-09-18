"""Kudos Slack handlers: the /kudos command and the `kudos @user ...` message.

Both patterns are anchored, so kudos needs no catch-all and never goes through
the DM router. Moved out of standup unchanged apart from the db import, which
now points at this module's own persistence.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _giver_timezone(team_id: str, user_id: str) -> str:
    """The giver's timezone, so their day resets at their own midnight."""
    try:
        import src.core.db as core_db  # noqa: PLC0415

        for row in core_db.get_all_members(team_id):
            if row.get("user_id") == user_id:
                return row.get("tz") or "UTC"
    except Exception:
        pass
    return "UTC"


def _check_allowance(team_id: str, from_user: str):
    """Returns (state, refusal_message). refusal_message is None when allowed.

    A database problem must not block recognition, so an unreadable allowance
    lets the kudos through rather than refusing it.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    import src.modules.kudos.db as kdb  # noqa: PLC0415

    try:
        state = kdb.allowance_state(team_id, from_user, _giver_timezone(team_id, from_user), datetime.now(timezone.utc))
    except Exception as exc:
        logger.warning("allowance lookup failed for %s: %s", from_user, exc)
        return {"emoji": kdb.DEFAULT_EMOJI, "remaining": 1, "allowance": 0}, None

    if state["allowance"] == 0:
        return state, "Kudos are switched off for this workspace. An admin can turn them on in the dashboard."
    if not state["can_give"]:
        return state, (
            f"That was all {state['allowance']} of your {state['emoji']} for today. "
            "You get a fresh set at midnight where you are."
        )
    return state, None


def _remaining_note(state) -> str:
    """A quiet reminder of what is left, so the budget is visible."""
    left = max(0, state.get("remaining", 0) - 1)
    emoji = state.get("emoji", "")
    if state.get("allowance", 0) <= 0:
        return ""
    if left == 0:
        return f"That was your last {emoji} for today. A fresh set arrives at midnight."
    return f"{left} {emoji} left today."


def _context(*lines: str) -> list[dict]:
    """A context block per line, skipping the ones that came back empty."""
    return [{"type": "context", "elements": [{"type": "mrkdwn", "text": line}]} for line in lines if line]


def _quote(message: str) -> str:
    """Every line prefixed, so a multi-line reason stays inside the quote."""
    lines = (message or "").strip().splitlines()
    return "\n".join(f"> {line}" if line.strip() else ">" for line in lines) or "> "


def kudos_card(from_user: str, to_user: str, message: str, emoji: str | None = None) -> tuple[str, list[dict]]:
    """The card that lands in the channel.

    The person being recognised is named first and in bold, because they are
    the point of the message. The reason is quoted so it reads as their words
    being passed on, and the last line tells everyone else how to join in.
    """
    if emoji is None:
        from src.modules.kudos.db import DEFAULT_EMOJI  # noqa: PLC0415

        emoji = DEFAULT_EMOJI
    if to_user:
        headline = f"{emoji} *<@{to_user}>* got a {emoji} from <@{from_user}>"
        text = f"{emoji} <@{from_user}> gave <@{to_user}> a {emoji}"
    else:
        headline = f"{emoji} *<@{from_user}>* wants to recognise someone"
        text = f"{emoji} <@{from_user}> gave a {emoji}"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": headline}},
        {"type": "section", "text": {"type": "mrkdwn", "text": _quote(message)}},
        *_context("Pass one on with `kudos @someone` and a reason, or `/kudos`"),
    ]
    return text, blocks


def register_handlers(app) -> None:
    """Register the kudos command and message listeners."""

    @app.command("/kudos")
    @app.command("/morgenruf-kudos")
    def handle_kudos_command(ack, body, client):  # noqa: ANN001
        """Slash command to give kudos to a teammate."""
        ack()
        user_id: str = body["user_id"]
        team_id: str = body["team_id"]
        text: str = (body.get("text") or "").strip()

        if not text:
            client.chat_postMessage(
                channel=user_id,
                text="Name someone and say why. For example: `/kudos @sam caught the migration bug before it shipped`",
            )
            return

        # Parse @mention and message from text (e.g. "@user Great job!")
        mention_match = re.match(r"<@([A-Z0-9]+)(?:\|[^>]*)?>\s+(.+)", text)
        to_user = mention_match.group(1) if mention_match else ""
        kudos_message = mention_match.group(2).strip() if mention_match else text

        try:
            import src.core.db as core_db  # noqa: PLC0415
            import src.modules.kudos.db as db  # noqa: PLC0415

            config = core_db.get_workspace_config(team_id) or {}
            channel_id = config.get("channel_id", "")
            emoji = db.get_config(team_id).get("emoji") or db.DEFAULT_EMOJI

            # Persist kudos to database
            if to_user:
                db.save_kudos(team_id, user_id, to_user, kudos_message, channel_id, emoji)

            card_text, card_blocks = kudos_card(user_id, to_user, kudos_message, emoji)
            if channel_id:
                client.chat_postMessage(channel=channel_id, text=card_text, blocks=card_blocks)
                client.chat_postMessage(channel=user_id, text=f"Sent, and it is up in <#{channel_id}>.")
            else:
                client.chat_postMessage(
                    channel=user_id,
                    text=card_text,
                    blocks=[
                        *card_blocks,
                        *_context("Pick a channel in the dashboard to post these where the team can see them."),
                    ],
                )
        except Exception as exc:
            logger.warning("kudos command error: %s", exc)
            client.chat_postMessage(channel=user_id, text="That kudos did not go through. Try it once more.")

    @app.message(re.compile(r"^kudos\s+<@([A-Z0-9]+)>\s+(.+)$", re.IGNORECASE))
    def handle_kudos(message, say, client, context, logger):
        """Handle kudos messages: kudos <@USER> Great work!"""
        from_user = message["user"]
        team_id = message.get("team", "")
        to_user = context["matches"][0]
        kudos_message = context["matches"][1].strip()
        channel_type = message.get("channel_type", "")
        channel_id = message.get("channel", "")

        if from_user == to_user:
            say("Kudos are for other people. Pick a teammate.")
            return

        state, refusal = _check_allowance(team_id, from_user)
        if refusal:
            say(refusal)
            return

        try:
            import src.modules.kudos.db as db  # noqa: PLC0415

            db.save_kudos(team_id, from_user, to_user, kudos_message, channel_id, state["emoji"])
        except Exception as exc:
            logger.warning("Could not save kudos: %s", exc)

        emoji = state["emoji"]
        card_text, card_blocks = kudos_card(from_user, to_user, kudos_message, emoji)
        left = _remaining_note(state)

        try:
            if channel_type == "im":
                try:
                    import src.core.db as db  # noqa: PLC0415

                    config = db.get_workspace_config(team_id) or {}
                    post_channel = config.get("channel_id", "")
                    if post_channel:
                        client.chat_postMessage(channel=post_channel, text=card_text, blocks=card_blocks)
                        say(
                            text=f"Sent, and it is up in <#{post_channel}>.",
                            blocks=[
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"Sent, and it is up in <#{post_channel}>.",
                                    },
                                },
                                *_context(left),
                            ],
                        )
                    else:
                        say(
                            text=card_text,
                            blocks=[
                                *card_blocks,
                                *_context(
                                    "Pick a channel in the dashboard and the next one posts where the team can see it.",
                                    left,
                                ),
                            ],
                        )
                except Exception:
                    say(text=card_text, blocks=[*card_blocks, *_context(left)])
            else:
                client.chat_postMessage(channel=channel_id, text=card_text, blocks=card_blocks)
        except Exception as exc:
            logger.error("Failed to post kudos: %s", exc)
            say(text=f"Saved. <@{to_user}> has been recognised. {left}".strip())
