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

    def _confirm(client, body, text: str) -> None:
        """Say what happened, wherever the button was pressed.

        The App Home has no channel to reply in, so a DM is the only place the
        person will see it. Clicking a button and getting nothing back reads as
        a broken button.
        """
        user_id = body["user"]["id"]
        channel = (body.get("channel") or {}).get("id")
        try:
            if channel:
                client.chat_postEphemeral(channel=channel, user=user_id, text=text)
            else:
                client.chat_postMessage(channel=user_id, text=text)
        except Exception:
            logger.info("connect: could not confirm to %s", user_id)

    @app.action("connect:home_snooze")
    def handle_home_snooze(ack, body, client):  # noqa: ANN001
        """A fortnight off, which is what most people want rather than leaving."""
        ack()
        from datetime import date, timedelta  # noqa: PLC0415

        user_id = body["user"]["id"]
        team_id = body.get("team", {}).get("id", "")
        program_id = int(body["actions"][0]["value"])
        until = date.today() + timedelta(weeks=2)
        try:
            import src.modules.connect.db as cdb  # noqa: PLC0415

            cdb.snooze(team_id, program_id, user_id, until)
            _confirm(client, body, f"Snoozed until {until.strftime('%d %B')}. You will be matched again after that.")
        except Exception:
            logger.exception("connect: could not snooze %s", user_id)

    @app.action("connect:home_pause")
    def handle_home_pause(ack, body, client):  # noqa: ANN001
        """Pause from the App Home, where there is no channel to reply in."""
        ack()
        user_id = body["user"]["id"]
        team_id = body.get("team", {}).get("id", "")
        program_id = int(body["actions"][0]["value"])
        try:
            import src.modules.connect.db as cdb  # noqa: PLC0415

            cdb.opt_out(team_id, program_id, user_id, mode="off")
            _confirm(
                client,
                body,
                "Paused. You will not be matched until you resume, and the App Home will say so next time you open it.",
            )
        except Exception:
            logger.exception("connect: could not pause %s from the App Home", user_id)

    @app.action("connect:home_resume")
    def handle_home_resume(ack, body, client):  # noqa: ANN001
        """And back in again, without needing an admin."""
        ack()
        user_id = body["user"]["id"]
        team_id = body.get("team", {}).get("id", "")
        program_id = int(body["actions"][0]["value"])
        try:
            import src.modules.connect.db as cdb  # noqa: PLC0415

            cdb.opt_in(team_id, program_id, user_id)
            _confirm(client, body, "You are back in. You will be matched in the next round.")
        except Exception:
            logger.exception("connect: could not resume %s from the App Home", user_id)

    @app.event("member_joined_channel")
    def handle_joined_coffee_channel(event, client):  # noqa: ANN001
        """Tell someone joining a coffee chat channel what they just signed up for.

        Slack shows nothing about a bot's schedule, so without this a person
        joins and waits, with no idea whether anything is coming or when.
        """
        from datetime import date  # noqa: PLC0415

        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        team_id = event.get("team", "") or ""
        if not user_id or not channel_id:
            return
        try:
            import src.modules.connect.db as cdb  # noqa: PLC0415
            from src.modules.connect.rounds import cadence_phrase, upcoming_round_date  # noqa: PLC0415

            program = cdb.program_for_channel(team_id, channel_id)
            if not program:
                return
            nxt = upcoming_round_date(program, date.today())
            message = (
                f"Thanks for joining <#{channel_id}>. "
                f"I introduce you to someone else from this channel {cadence_phrase(program.get('interval_weeks'))}.\n"
                f"Your next introduction is on *{nxt.strftime('%A, %d %B')}*."
            )
            # Both, and for different reasons. The channel message is the one
            # that reaches someone in the moment they joined; the DM is the one
            # still there next week when they wonder what they signed up for.
            try:
                client.chat_postEphemeral(channel=channel_id, user=user_id, text=message)
            except Exception:
                logger.info("connect: no channel welcome for %s", user_id)
            client.chat_postMessage(
                channel=user_id,
                text=message,
                blocks=[
                    {"type": "section", "text": {"type": "mrkdwn", "text": message}},
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "Snooze yourself or check the date any time on the *Home* tab of this app.",
                            }
                        ],
                    },
                ],
            )
        except Exception:
            logger.info("connect: no welcome sent for %s in %s", user_id, channel_id)

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
