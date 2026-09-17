"""Button handlers for the coffee chat messages.

Opt-out is a button rather than a DM keyword on purpose: standup registers
@app.message("skip") as a substring match, so any Connect command containing
"skip" would fire standup's handler instead. Action ids are namespaced so two
modules cannot collide.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_handlers(app) -> None:
    @app.action("connect:skip_round")
    def handle_skip_round(ack, body, client):  # noqa: ANN001
        """Sit out this round only. The pairing already happened, so this is
        an apology to the other person as much as anything."""
        ack()
        user_id = body["user"]["id"]
        try:
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_id,
                text="No problem, you are out for this round. You will be matched again next time.",
            )
        except Exception:
            logger.exception("connect: could not confirm skip for %s", user_id)

    @app.action("connect:pause")
    def handle_pause(ack, body, client):  # noqa: ANN001
        """Stop matching this person until they say otherwise."""
        ack()
        user_id = body["user"]["id"]
        team_id = body.get("team", {}).get("id", "")
        program_id = int(body["actions"][0]["value"])
        try:
            import src.modules.connect.db as cdb  # noqa: PLC0415

            cdb.opt_out(team_id, program_id, user_id, mode="off")
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_id,
                text="You are paused. Ask an admin to turn coffee chats back on for you whenever you like.",
            )
        except Exception:
            logger.exception("connect: could not pause %s", user_id)

    @app.action("connect:met_yes")
    def handle_met_yes(ack, body, client):  # noqa: ANN001
        ack()
        _record_met(body, client, True, "Good to hear. See you next round.")

    @app.action("connect:met_no")
    def handle_met_no(ack, body, client):  # noqa: ANN001
        ack()
        _record_met(body, client, False, "No problem, there is always the next one.")


def _record_met(body, client, met: bool, reply: str) -> None:
    match_id = int(body["actions"][0]["value"])
    try:
        import src.modules.connect.db as cdb  # noqa: PLC0415

        cdb.set_met(match_id, met)
        client.chat_postMessage(channel=body["channel"]["id"], text=reply)
    except Exception:
        logger.exception("connect: could not record met=%s for match %s", met, match_id)
