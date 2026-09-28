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


def _describe_install(bot_token: str, team_id: str, installed_by: str) -> tuple[str, str]:
    """Workspace and installer details, looked up with the new install's bot token.

    The alert lands in the operator's workspace, where a mention of the
    installer's user id renders as an empty pill: that id only means something
    inside the installing workspace. So the name, email and domain are fetched
    here and written out as plain text. Any lookup that fails is left out.
    """
    workspace = ""
    person = ""
    if not bot_token:
        return workspace, person
    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=bot_token, timeout=TIMEOUT)
    except Exception:
        return workspace, person

    try:
        team = client.team_info(team=team_id).get("team") or {}
        domain = team.get("domain") or ""
        parts = [f"{domain}.slack.com" if domain else "", team_id]
        enterprise = team.get("enterprise_name") or team.get("enterprise_id") or ""
        if enterprise:
            parts.append(f"Enterprise Grid: {enterprise}")
        workspace = " · ".join(p for p in parts if p)
    except Exception as exc:
        logger.info("Install alert: team.info failed for %s: %s", team_id, exc)

    if installed_by:
        try:
            user = client.users_info(user=installed_by).get("user") or {}
            profile = user.get("profile") or {}
            name = profile.get("real_name") or user.get("real_name") or user.get("name") or ""
            parts = [
                name,
                profile.get("email") or "",
                profile.get("title") or "",
                user.get("tz") or "",
                installed_by,
            ]
            if user.get("is_admin") or user.get("is_owner"):
                parts.insert(4, "workspace admin")
            person = " · ".join(p for p in parts if p)
        except Exception as exc:
            logger.info("Install alert: users.info failed for %s: %s", installed_by, exc)
    return workspace, person


def installed(team_id: str, team_name: str, installed_by: str = "", bot_token: str = "") -> bool:
    """Somebody installed the app."""
    try:
        import src.core.db as db  # noqa: PLC0415

        total = db.count_installations()
    except Exception:
        total = 0

    workspace, person = _describe_install(bot_token, team_id, installed_by)

    name = team_name or team_id
    lines = [f":tada: *{name}* installed Morgenruf"]
    lines.append(f"Workspace: {workspace or team_id}")
    if person:
        lines.append(f"Installed by: {person}")
    elif installed_by:
        lines.append(f"Installed by: {installed_by}")
    if total:
        lines.append(f"{total} active workspace{'s' if total != 1 else ''} now.")
    return notify("\n".join(lines))


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
