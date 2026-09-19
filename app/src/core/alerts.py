"""Operator alerts: the handful of things worth interrupting a person for.

Not user-facing. These go to one Slack channel that the person running the
instance watches, and they exist because the first twenty workspaces came and
went without anyone noticing on the day it happened. An install is the only
signal that arrives without being asked for, and it is worth knowing about
within the minute rather than at the end of the month.

Configured by MORGENRUF_ALERT_WEBHOOK, a Slack incoming-webhook URL. Unset
means no alerts, which is what a self-hosted install gets by default: the
webhook points at the operator's own workspace, not the customer's.
"""

from __future__ import annotations

import logging
import os

from src.core.url_guard import is_safe_webhook_url

logger = logging.getLogger(__name__)

TIMEOUT = 5


def _webhook() -> str:
    return os.environ.get("MORGENRUF_ALERT_WEBHOOK", "").strip()


def notify(text: str) -> bool:
    """Post one line to the operator's alert channel. Never raises.

    An alert that breaks the thing it is reporting on is worse than no alert,
    so every failure here is a log line and a False.
    """
    url = _webhook()
    if not url:
        return False
    if not is_safe_webhook_url(url):
        logger.warning("MORGENRUF_ALERT_WEBHOOK is not a safe outbound URL; alert dropped")
        return False

    try:
        import requests  # noqa: PLC0415

        resp = requests.post(url, json={"text": text}, timeout=TIMEOUT)
        if resp.status_code >= 400:
            logger.warning("Alert webhook returned %s", resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.warning("Could not post alert: %s", exc)
        return False


def installed(team_id: str, team_name: str, installed_by: str = "") -> bool:
    """Somebody installed the app."""
    try:
        import src.core.db as db  # noqa: PLC0415

        total = db.count_installations()
    except Exception:
        total = 0

    name = team_name or team_id
    line = f":tada: *{name}* installed Morgenruf"
    if installed_by:
        line += f" (by <@{installed_by}>)"
    if total:
        line += f"\n{total} workspace{'s' if total != 1 else ''} now."
    return notify(line)


def uninstalled(team_id: str, team_name: str, days: int = 0, standups: int = 0) -> bool:
    """Somebody removed the app. Sent before the rows are deleted.

    The numbers are the whole point: a workspace that ran zero standups in
    three weeks left for a different reason than one that ran forty.
    """
    name = team_name or team_id
    line = f":wave: *{name}* removed Morgenruf"
    if days:
        line += f" after {days} day{'s' if days != 1 else ''}"
    line += f"\n{standups} standup{'s' if standups != 1 else ''} run."
    if standups == 0:
        line += " Never got set up."
    return notify(line)


def departed(team_id: str) -> bool:
    """Gather what a leaving workspace was, then alert. Call before the delete.

    Same constraint as the farewell email: the row this reads is the row about
    to be removed.
    """
    try:
        import src.core.db as db  # noqa: PLC0415

        install = db.get_installation(team_id)
        if not install:
            return False
        days = 0
        installed_at = install.get("installed_at") or install.get("created_at")
        if installed_at:
            from datetime import datetime, timezone  # noqa: PLC0415

            days = max(0, (datetime.now(timezone.utc) - installed_at).days)
        return uninstalled(
            team_id,
            install.get("team_name", ""),
            days=days,
            standups=db.count_standups(team_id),
        )
    except Exception as exc:
        logger.warning("Could not post uninstall alert for %s: %s", team_id, exc)
        return False
