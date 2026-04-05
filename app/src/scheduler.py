"""Scheduler — per-workspace standup cron jobs backed by PostgreSQL config."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
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

    # Load custom questions from workspace config
    questions = None
    try:
        import db  # noqa: PLC0415
        config = db.get_workspace_config(team_id) or {}
        qs = config.get("questions") or []
        if isinstance(qs, str):
            import json as _json
            try:
                qs = _json.loads(qs)
            except Exception:
                qs = []
        if qs:
            questions = qs
    except Exception as exc:
        logger.warning("Could not load questions for %s: %s", team_id, exc)

    logger.info("Triggering standup for team %s (%d members)", team_id, len(members))
    client = WebClient(token=bot_token)

    for member in members:
        user_id = member["user_id"]
        cache_key = f"{team_id}:{user_id}"
        try:
            if state_store.is_active(cache_key):
                logger.debug("Skipping %s — already has active session", user_id)
                continue

            # Check if user skipped today
            try:
                import db  # noqa: PLC0415
                if db.is_skipped_today(team_id, user_id):
                    logger.debug("Skipping %s — user opted out today", user_id)
                    continue
            except Exception:
                pass

            session = state_store.start(cache_key, channel_id, team_id=team_id, questions=questions)

            dm = client.conversations_open(users=user_id)
            dm_channel = dm["channel"]["id"]

            client.chat_postMessage(
                channel=dm_channel,
                text=f"👋 *Good morning!* Time for your daily standup.\n\n{session.questions[0]}",
            )
            logger.info("Sent standup DM to %s / %s", team_id, user_id)
        except Exception as exc:
            logger.error("Failed to DM %s / %s: %s", team_id, user_id, exc)


def _send_reminder_to_workspace(team_id: str, bot_token: str, reminder_minutes: int) -> None:
    """DM active members a heads-up before standup time."""
    try:
        import db  # noqa: PLC0415
        members = db.get_active_members(team_id)
    except Exception as exc:
        logger.error("Could not load members for reminder %s: %s", team_id, exc)
        return
    client = WebClient(token=bot_token)
    for member in members:
        user_id = member["user_id"]
        try:
            import db  # noqa: PLC0415
            if db.is_skipped_today(team_id, user_id):
                continue
            dm = client.conversations_open(users=user_id)
            dm_channel = dm["channel"]["id"]
            client.chat_postMessage(
                channel=dm_channel,
                text=f"⏰ Your standup starts in *{reminder_minutes} minutes*. Get ready! 🚀",
            )
        except Exception as exc:
            logger.warning("Failed reminder DM to %s / %s: %s", team_id, user_id, exc)


def _send_weekly_digest(team_id: str, bot_token: str) -> None:
    """Send a weekly summary email to the workspace admin."""
    try:
        import db  # noqa: PLC0415
        from mailer import send_weekly_digest  # noqa: PLC0415
        inst = db.get_installation(team_id)
        if not inst:
            return
        stats = db.get_dashboard_stats(team_id)
        participation = db.get_participation_stats(team_id, days=7)
        email = db.get_member_email(team_id, inst.get("installed_by_user_id", "")) or ""
        send_weekly_digest(
            to_email=email,
            team_name=inst.get("team_name", team_id),
            stats=stats,
            participation=participation,
        )
    except Exception as exc:
        logger.warning("Weekly digest failed for %s: %s", team_id, exc)


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

    # Reminder job
    reminder_minutes = int(config.get("reminder_minutes") or 0)
    if reminder_minutes > 0:
        standup_dt = datetime(2000, 1, 1, int(hour), int(minute))
        reminder_dt = standup_dt - timedelta(minutes=reminder_minutes)
        scheduler.add_job(
            _send_reminder_to_workspace,
            trigger=CronTrigger(
                hour=reminder_dt.hour,
                minute=reminder_dt.minute,
                day_of_week=schedule_days,
                timezone=tz,
            ),
            args=[team_id, bot_token, reminder_minutes],
            id=f"reminder_{team_id}",
            name=f"Reminder — {team_id}",
            replace_existing=True,
        )
        logger.info("Registered reminder job for %s (%d min before)", team_id, reminder_minutes)

    # Weekly digest job (Sunday 18:00 in workspace tz)
    scheduler.add_job(
        _send_weekly_digest,
        trigger=CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=tz),
        args=[team_id, bot_token],
        id=f"digest_{team_id}",
        name=f"Weekly Digest — {team_id}",
        replace_existing=True,
    )


def build_scheduler(installations: list[tuple[str, str, dict]]) -> BackgroundScheduler:
    """Build scheduler from a list of (team_id, bot_token, config) tuples."""
    global _scheduler
    scheduler = BackgroundScheduler()

    for team_id, bot_token, config in installations:
        register_workspace_job(scheduler, team_id, bot_token, config)

    _scheduler = scheduler
    return scheduler
