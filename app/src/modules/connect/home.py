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
    blocks.extend(_zoom_blocks(team_id, user_id))
    return blocks


def _zoom_blocks(team_id: str, user_id: str) -> list[dict]:
    """Zoom connection state, and the way to undo it.

    Somebody who connects an account must be able to disconnect it from the
    same place they see it, without asking an admin. This is the only surface
    where that is true: the linking prompt is ephemeral and gone by the next
    day, and the dashboard belongs to admins.
    """
    from src.modules.connect import zoom  # noqa: PLC0415

    if not zoom.configured():
        return []

    try:
        import src.modules.connect.db as cdb  # noqa: PLC0415

        link = cdb.zoom_link(team_id, user_id)
    except Exception:
        logger.exception("connect: could not read the Zoom link for the App Home")
        return []

    if link:
        who = link.get("zoom_email") or "your Zoom account"
        return [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Zoom*\n{who} is connected. Meetings are created on it."},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Disconnect"},
                    "action_id": "connect:zoom_unlink",
                    "value": "unlink",
                    "style": "danger",
                },
            },
        ]

    # Never linked, or linked and since expired. The two need different words:
    # "connect" reads as a new decision, which is wrong for somebody who
    # already made it and whose token merely aged out.
    import os  # noqa: PLC0415

    from src.modules.connect.zoom_routes import mint_link_token  # noqa: PLC0415

    base = (os.environ.get("APP_URL") or "").rstrip("/")
    if not base:
        return []
    url = f"{base}/connect/zoom/start?t={mint_link_token(team_id, user_id)}"
    return [
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Zoom*\nConnect your account and your coffee chats come with a meeting, "
                "scheduled for the time you agree.",
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Connect Zoom"},
                "url": url,
                "action_id": "connect:zoom_link",
            },
        },
    ]
