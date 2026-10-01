"""One nudge for workspaces that installed and never started a standup.

Of the outside workspaces that removed the app, nearly all had never set one
up. Two days after install, the installer gets one Slack DM with the quick
start button. Once, recorded before sending, never by email, and never to
anyone but the installer.
"""

from __future__ import annotations

import logging

from slack_sdk import WebClient

logger = logging.getLogger(__name__)

KIND = "nudge:day2"
AFTER_HOURS = 48
TEXT = "Morgenruf is installed but no standup is running yet. It takes two fields: pick your team's channel and a time."


def _bot_token(team_id: str, stored: str) -> str:
    """The stored token, refreshed first when it is a rotating one near expiry."""
    from src.core.scheduler import _fresh_bot_token  # noqa: PLC0415

    return _fresh_bot_token(team_id, stored)


def send_day2_nudges() -> tuple[int, int]:
    """DM each eligible installer once. Returns (sent, skipped)."""
    import src.core.db as db  # noqa: PLC0415
    from src.core.quickstart_button import button_block  # noqa: PLC0415
    from src.core.usage_report import internal_teams  # noqa: PLC0415

    internal = internal_teams()
    sent = skipped = 0
    for row in db.workspaces_without_standup(hours=AFTER_HOURS):
        team_id = row["team_id"]
        user_id = row.get("installed_by_user_id")
        # The operator's own workspaces are not prospects.
        if team_id in internal:
            skipped += 1
            continue
        # Recorded before sending: a crash after this line loses one nudge,
        # it never sends two.
        if not user_id or not row.get("bot_token") or not db.record_install_email(team_id, KIND):
            skipped += 1
            continue
        try:
            client = WebClient(token=_bot_token(team_id, row["bot_token"]))
            dm = client.conversations_open(users=user_id)["channel"]["id"]
            client.chat_postMessage(
                channel=dm,
                text=TEXT,
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": TEXT}}, button_block()],
            )
            sent += 1
        except Exception as exc:
            # Most often the workspace removed the app since the scan.
            logger.info("day-2 nudge not delivered for %s: %s", team_id, exc)
            skipped += 1
    if sent or skipped:
        logger.info("Day-2 nudges: %d sent, %d skipped", sent, skipped)
    return sent, skipped
