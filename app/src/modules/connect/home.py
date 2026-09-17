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
            opted_out = cdb.optout_user_ids(team_id, p["id"])
        except Exception:
            opted_out = set()
        paused = user_id in opted_out
        nxt = upcoming_round_date(p, today)
        when = nxt.strftime("%A, %d %B")
        cadence = cadence_phrase(p.get("interval_weeks"))

        line = f"<#{p['channel_id']}> · introductions {cadence}\n" + (
            "_You are paused, so you will not be matched._" if paused else f"Your next introduction is on *{when}*."
        )
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": line},
                "accessory": {
                    "type": "button",
                    "action_id": "connect:home_resume" if paused else "connect:home_pause",
                    "text": {
                        "type": "plain_text",
                        "text": "Resume" if paused else "Pause me",
                        "emoji": True,
                    },
                    "value": str(p["id"]),
                },
            }
        )

    blocks.append(_context("Pausing stops future introductions. It does not cancel one already sent."))
    return blocks
