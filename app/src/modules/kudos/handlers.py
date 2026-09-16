"""Kudos Slack handlers: the /kudos command and the `kudos @user ...` message.

Both patterns are anchored, so kudos needs no catch-all and never goes through
the DM router. Moved out of standup unchanged apart from the db import, which
now points at this module's own persistence.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def register_handlers(app) -> None:
    """Register the kudos command and message listeners."""
    @app.command("/kudos")
    def handle_kudos_command(ack, body, client):  # noqa: ANN001
        """Slash command to give kudos to a teammate."""
        ack()
        user_id: str = body["user_id"]
        team_id: str = body["team_id"]
        text: str = (body.get("text") or "").strip()

        if not text:
            client.chat_postMessage(
                channel=user_id,
                text="Usage: `/kudos @teammate Great job on the release! 🚀`",
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

            # Persist kudos to database
            if to_user:
                db.save_kudos(team_id, user_id, to_user, kudos_message, channel_id)

            if channel_id:
                client.chat_postMessage(
                    channel=channel_id,
                    text=f"🏆 <@{user_id}> gives kudos: {text}",
                )
            client.chat_postMessage(channel=user_id, text=f"✅ Kudos sent: {text}")
        except Exception as exc:
            logger.warning("kudos command error: %s", exc)
            client.chat_postMessage(channel=user_id, text="❌ Couldn't send kudos. Please try again.")
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
            say("😄 Nice try, but you can't give kudos to yourself!")
            return

        try:
            import src.modules.kudos.db as db  # noqa: PLC0415

            db.save_kudos(team_id, from_user, to_user, kudos_message, channel_id)
        except Exception as exc:
            logger.warning("Could not save kudos: %s", exc)

        kudos_card = f"🏆 *Kudos!*\n\n<@{from_user}> gave kudos to <@{to_user}>\n\n> {kudos_message}"

        try:
            if channel_type == "im":
                try:
                    import src.core.db as db  # noqa: PLC0415

                    config = db.get_workspace_config(team_id) or {}
                    post_channel = config.get("channel_id", "")
                    if post_channel:
                        client.chat_postMessage(channel=post_channel, text=kudos_card)
                        say(f"✅ Kudos posted to <#{post_channel}>! 🎉")
                    else:
                        say(kudos_card + "\n\n_(Configure a standup channel in the dashboard to post kudos there)_")
                except Exception:
                    say(kudos_card)
            else:
                client.chat_postMessage(channel=channel_id, text=kudos_card)
        except Exception as exc:
            logger.error("Failed to post kudos: %s", exc)
            say(f"✅ Kudos saved! <@{to_user}> has been recognised. 🎉")
