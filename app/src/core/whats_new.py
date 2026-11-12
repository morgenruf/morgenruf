"""The "What's new" card at the top of the Slack App Home tab.

Every deploy reaches every workspace at once, but nobody notices a feature
that arrives silently. This shows the newest item to everyone until they
press "Got it", and drops it on its own after a month so the card never
turns into a stale banner. No messages are sent: people see it when they
open Home.

To announce a feature, add an Item at the top of ITEMS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DISMISS_ACTION = "whats_new:dismiss"
SHOW_FOR = timedelta(days=30)


@dataclass(frozen=True)
class Item:
    id: str  # stable, never reused: dismissals are stored against it
    published: date
    text: str  # mrkdwn
    module: str = ""  # shown only where this module is on; "" for everyone
    button_text: str = ""
    button_action: str = ""  # an existing action_id the button triggers


# Newest first.
ITEMS: tuple[Item, ...] = (
    Item(
        id="2026-11-give-kudos-button",
        published=date(2026, 11, 12),
        text="*Give kudos with one button.* Pick a teammate, say what they did, send. No command to type.",
        module="kudos",
        button_text="Give kudos",
        button_action="kudos:give",
    ),
)


def current(today: date, items: tuple[Item, ...] = ITEMS) -> Item | None:
    """The newest item still inside its showing window."""
    for item in items:
        if item.published <= today < item.published + SHOW_FOR:
            return item
    return None


def _dismissed(team_id: str, user_id: str, item_id: str) -> bool:
    from src.core.db import db_conn  # noqa: PLC0415

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM whats_new_seen WHERE team_id = %s AND user_id = %s AND item_id = %s",
                (team_id, user_id, item_id),
            )
            return cur.fetchone() is not None


def dismiss(team_id: str, user_id: str, item_id: str) -> None:
    from src.core.db import db_conn  # noqa: PLC0415

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO whats_new_seen (team_id, user_id, item_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (team_id, user_id, item_id),
            )


def home_blocks(team_id: str, user_id: str, today: date | None = None) -> list[dict]:
    """The card, or nothing when there is no news, it was dismissed, or the
    feature it points at is off in this workspace."""
    item = current(today or datetime.now(timezone.utc).date())
    if item is None:
        return []
    try:
        if item.module:
            from src.core.modules import is_active_for  # noqa: PLC0415

            if not is_active_for(team_id, item.module):
                return []
        if _dismissed(team_id, user_id, item.id):
            return []
    except Exception as exc:
        # A lookup that fails hides the card: news is never worth an error.
        logger.info("whats_new: skipped for %s: %s", user_id, exc)
        return []

    buttons = []
    if item.button_action:
        buttons.append(
            {
                "type": "button",
                "action_id": item.button_action,
                "style": "primary",
                "text": {"type": "plain_text", "text": item.button_text},
            }
        )
    buttons.append(
        {
            "type": "button",
            "action_id": DISMISS_ACTION,
            "value": item.id,
            "text": {"type": "plain_text", "text": "Got it"},
        }
    )
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f":sparkles: *What's new*\n{item.text}"}},
        {"type": "actions", "elements": buttons},
        {"type": "divider"},
    ]


def register_slack(app) -> None:
    """The "Got it" button. The feature button belongs to its module."""
    from src.core.home import refresh_home  # noqa: PLC0415

    @app.action(DISMISS_ACTION)
    def handle_dismiss(ack, body, client):  # noqa: ANN001
        ack()
        team_id = (body.get("team") or {}).get("id") or ""
        user_id = (body.get("user") or {}).get("id") or ""
        item_id = ((body.get("actions") or [{}])[0] or {}).get("value") or ""
        if not (team_id and user_id and item_id):
            return
        try:
            dismiss(team_id, user_id, item_id)
        except Exception:
            logger.exception("whats_new: could not save a dismissal for %s", user_id)
            return
        refresh_home(team_id, user_id, client)
