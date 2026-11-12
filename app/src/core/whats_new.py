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
REINSTALL_ACTION = "whats_new:reinstall"
SHOW_FOR = timedelta(days=30)


@dataclass(frozen=True)
class Item:
    id: str  # stable, never reused: dismissals are stored against it
    published: date
    text: str  # mrkdwn
    module: str = ""  # shown only where this module is on; "" for everyone
    button_text: str = ""
    button_action: str = ""  # an existing action_id the button triggers
    scope: str = ""  # a Slack scope the feature needs; older installs must reinstall


# Newest first.
ITEMS: tuple[Item, ...] = (
    Item(
        id="2026-11-kudos-reactions",
        published=date(2026, 11, 12),
        text="*Give kudos with an emoji.* React to a teammate's message with your kudos emoji "
        "(\N{MAPLE LEAF} or :morgenruf:) and they get a kudos for it. Works in channels Morgenruf is in.",
        module="kudos",
        scope="reactions:read",
    ),
    Item(
        id="2026-11-give-kudos-button",
        published=date(2026, 11, 12),
        text="*Give kudos with one button.* Pick a teammate, say what they did, send. No command to type.",
        module="kudos",
        button_text="Give kudos",
        button_action="kudos:give",
    ),
)


def current(today: date, items: tuple[Item, ...] | None = None) -> list[Item]:
    """Items still inside their showing window, newest first."""
    return [i for i in (ITEMS if items is None else items) if i.published <= today < i.published + SHOW_FOR]


def _dismissed(team_id: str, user_id: str, item_id: str) -> bool:
    from src.core.db import db_conn  # noqa: PLC0415

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM whats_new_seen WHERE team_id = %s AND user_id = %s AND item_id = %s",
                (team_id, user_id, item_id),
            )
            return cur.fetchone() is not None


def _has_scope(team_id: str, scope: str) -> bool:
    try:
        import src.core.db as db  # noqa: PLC0415

        return scope in set(db.granted_scopes(team_id) or ())
    except Exception:
        return True  # unknown: show the feature, not a reinstall nobody needs


def _is_admin(team_id: str, user_id: str) -> bool:
    try:
        import src.core.db as db  # noqa: PLC0415

        return db.can_administer(team_id, user_id) is True
    except Exception:
        return False


def _app_url() -> str:
    import os  # noqa: PLC0415

    return os.environ.get("APP_URL", "https://api.morgenruf.dev").rstrip("/")


def dismiss(team_id: str, user_id: str, item_id: str) -> None:
    from src.core.db import db_conn  # noqa: PLC0415

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO whats_new_seen (team_id, user_id, item_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (team_id, user_id, item_id),
            )


def home_blocks(team_id: str, user_id: str, today: date | None = None) -> list[dict]:
    """The newest item this person has not dismissed, skipping any whose
    feature is off in this workspace. Nothing when no news is left."""
    item = None
    try:
        for candidate in current(today or datetime.now(timezone.utc).date()):
            if candidate.module:
                from src.core.modules import is_active_for  # noqa: PLC0415

                if not is_active_for(team_id, candidate.module):
                    continue
            if not _dismissed(team_id, user_id, candidate.id):
                item = candidate
                break
    except Exception as exc:
        # A lookup that fails hides the card: news is never worth an error.
        logger.info("whats_new: skipped for %s: %s", user_id, exc)
        return []
    if item is None:
        return []

    text = item.text
    buttons = []
    if item.scope and not _has_scope(team_id, item.scope):
        if _is_admin(team_id, user_id):
            text += "\n_Reinstall Morgenruf once to turn this on for your workspace._"
            buttons.append(
                {
                    "type": "button",
                    "action_id": REINSTALL_ACTION,
                    "style": "primary",
                    "url": f"{_app_url()}/install",
                    "text": {"type": "plain_text", "text": "Reinstall Morgenruf"},
                }
            )
        else:
            text += "\n_Ask a workspace admin to reinstall Morgenruf to turn this on._"
    elif item.button_action:
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
        {"type": "section", "text": {"type": "mrkdwn", "text": f":sparkles: *What's new*\n{text}"}},
        {"type": "actions", "elements": buttons},
        {"type": "divider"},
    ]


def register_slack(app) -> None:
    """The "Got it" button. The feature button belongs to its module."""
    from src.core.home import refresh_home  # noqa: PLC0415

    @app.action(REINSTALL_ACTION)
    def handle_reinstall(ack):  # noqa: ANN001
        ack()  # a link button: Slack opens the URL, this only acknowledges the click

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
