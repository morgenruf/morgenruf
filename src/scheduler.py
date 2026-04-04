"""Scheduler — sends standup DMs to team members at configured times."""

from __future__ import annotations

import logging

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from state import QUESTIONS, state_store

logger = logging.getLogger(__name__)


def _send_standup_to_team(client, team: dict) -> None:
    """DM every member of a team to start their standup."""
    channel = team["channel"]
    members = team.get("members", [])
    logger.info("Triggering standup for team %s (%d members)", channel, len(members))

    for member in members:
        user_id = member["slack_id"]
        try:
            if state_store.is_active(user_id):
                logger.debug("Skipping %s — already has active session", user_id)
                continue

            state_store.start(user_id, channel)

            # Open DM channel
            dm = client.conversations_open(users=user_id)
            dm_channel = dm["channel"]["id"]

            client.chat_postMessage(
                channel=dm_channel,
                text=f"👋 *Good morning!* Time for your daily standup.\n\n{QUESTIONS[0]}",
            )
            logger.info("Sent standup DM to %s", user_id)
        except Exception as e:
            logger.error("Failed to DM %s: %s", user_id, e)


def build_scheduler(client, teams: list[dict]) -> BackgroundScheduler:
    """Build and return a configured APScheduler."""
    scheduler = BackgroundScheduler()

    for team in teams:
        standup_time = team.get("standup_time", "09:00")
        timezone = team.get("timezone", "Asia/Kolkata")
        hour, minute = standup_time.split(":")

        # Skip weekends by default unless overridden
        days = team.get("days", "mon-fri")

        tz = pytz.timezone(timezone)
        trigger = CronTrigger(
            hour=int(hour),
            minute=int(minute),
            day_of_week=days,
            timezone=tz,
        )

        scheduler.add_job(
            _send_standup_to_team,
            trigger=trigger,
            args=[client, team],
            id=f"standup_{team['channel']}",
            name=f"Standup — {team['channel']}",
            replace_existing=True,
        )
        logger.info(
            "Scheduled standup for %s at %s %s (%s)",
            team["channel"], standup_time, timezone, days,
        )

    return scheduler
