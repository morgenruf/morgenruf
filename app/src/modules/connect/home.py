"""What Connect contributes to the Slack App Home.

Someone in a coffee chat programme should be able to see, without leaving
Slack, when their next introduction is and how to step out of it. Those were
only reachable from the buttons on a round message, which is no use between
rounds.
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def _context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def home_blocks(team_id: str, user_id: str) -> list[dict]:
    """Blocks for this person's coffee chats, or nothing if they are in none."""
    import src.modules.connect.db as cdb  # noqa: PLC0415
    from src.modules.connect.rounds import cadence_phrase, upcoming_round_date  # noqa: PLC0415

    try:
        programs = [p for p in cdb.get_programs(team_id) if p.get("enabled")]
    except Exception:
        logger.exception("connect: could not read programmes for the App Home")
        return []
    if not programs:
        return []

    today = date.today()
    blocks: list[dict] = [
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*☕ Coffee chats*"}},
    ]

    for p in programs:
        try:
            personal = cdb.personal_state(team_id, p["id"], user_id)
        except Exception:
            personal = {"state": "in", "until": None}
        state = personal["state"]
        nxt = upcoming_round_date(p, today)
        when = nxt.strftime("%A, %d %B")
        cadence = cadence_phrase(p.get("interval_weeks"))

        if state == "out":
            status = "_You are out of this one, so you will not be matched._"
        elif state == "snoozed":
            status = f"_Snoozed until {personal['until'].strftime('%d %B')}._"
        else:
            status = f"Your next introduction is on *{when}*."
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"<#{p['channel_id']}> \u00b7 introductions {cadence}\n{status}"},
            }
        )
        if state == "in":
            # Snooze is what people actually want: a fortnight off, not a
            # decision to never do this again.
            elements = [
                {
                    "type": "button",
                    "action_id": "connect:home_snooze",
                    "text": {"type": "plain_text", "text": "Snooze 2 weeks"},
                    "value": str(p["id"]),
                },
                {
                    "type": "button",
                    "action_id": "connect:home_pause",
                    "text": {"type": "plain_text", "text": "Leave this one"},
                    "value": str(p["id"]),
                },
            ]
        else:
            elements = [
                {
                    "type": "button",
                    "action_id": "connect:home_resume",
                    "text": {"type": "plain_text", "text": "Count me back in"},
                    "style": "primary",
                    "value": str(p["id"]),
                }
            ]
        blocks.append({"type": "actions", "elements": elements})

    blocks.append(_context("Snoozing or leaving stops future introductions. Neither cancels one already sent."))
    return blocks
