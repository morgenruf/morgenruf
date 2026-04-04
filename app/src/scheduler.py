"""Scheduler — per-workspace standup cron jobs backed by PostgreSQL config."""

from __future__ import annotations

import logging
from typing import Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from slack_sdk import WebClient

from state import QUESTIONS, state_store

logger = logging.getLogger(__name__)

# Module-level scheduler reference so oauth.py can access it after startup
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler


def _send_standup_to_workspace(team_id: str, bot_token: str, channel_id: str) -> None:
    """DM every active member of a workspace to start their standup."""
    try:
        import db  # noqa: PLC0415
        members = db.get_active_members(team_id)
    except Exception as exc:
        logger.error("Could not load members for %s: %s", team_id, exc)
        return

    logger.info("Triggering standup for team %s (%d members)", team_id, len(members))
    client = WebClient(token=bot_token)

    for member in members:
        user_id = member["user_id"]
        cache_key = f"{team_id}:{user_id}"
        try:
            if state_store.is_active(cache_key):
                logger.debug("Skipping %s — already has active session", user_id)
                continue

            state_store.start(cache_key, channel_id, team_id=team_id)

            dm = client.conversations_open(users=user_id)
            dm_channel = dm["channel"]["id"]

            client.chat_postMessage(
                channel=dm_channel,
                text=f"👋 *Good morning!* Time for your daily standup.\n\n{QUESTIONS[0]}",
            )
            logger.info("Sent standup DM to %s / %s", team_id, user_id)
        except Exception as exc:
            logger.error("Failed to DM %s / %s: %s", team_id, user_id, exc)


def register_workspace_job(
    scheduler: BackgroundScheduler,
    team_id: str,
    bot_token: str,
    config: dict,
) -> None:
    """Add or replace a cron job for a single workspace."""
    schedule_time: str = config.get("schedule_time", "09:00")
    schedule_tz: str = config.get("schedule_tz", "UTC")
    schedule_days: str = config.get("schedule_days", "mon,tue,wed,thu,fri")
    channel_id: str = config.get("channel_id") or ""

    try:
        hour, minute = schedule_time.split(":")
        tz = pytz.timezone(schedule_tz)
    except Exception as exc:
        logger.error("Invalid schedule config for %s: %s", team_id, exc)
        return

    trigger = CronTrigger(
        hour=int(hour),
        minute=int(minute),
        day_of_week=schedule_days,
        timezone=tz,
    )

    scheduler.add_job(
        _send_standup_to_workspace,
        trigger=trigger,
        args=[team_id, bot_token, channel_id],
        id=f"standup_{team_id}",
        name=f"Standup — {team_id}",
        replace_existing=True,
    )
    logger.info(
        "Registered standup job for %s at %s %s (%s)",
        team_id, schedule_time, schedule_tz, schedule_days,
    )


def build_scheduler(installations: list[tuple[str, str, dict]]) -> BackgroundScheduler:
    """Build scheduler from a list of (team_id, bot_token, config) tuples."""
    global _scheduler
    scheduler = BackgroundScheduler()

    for team_id, bot_token, config in installations:
        register_workspace_job(scheduler, team_id, bot_token, config)

    _scheduler = scheduler
    return scheduler
