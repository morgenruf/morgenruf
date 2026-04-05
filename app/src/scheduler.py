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


def _send_standup_to_workspace(team_id: str, bot_token: str, channel_id: str, schedule_id: int | None = None) -> None:
    """DM participants of a standup schedule (or all active members if no schedule)."""
    try:
        import db  # noqa: PLC0415
        if schedule_id:
            schedule = db.get_standup_schedule(team_id, schedule_id)
            if not schedule or not schedule.get("active"):
                logger.info("Schedule %s inactive, skipping", schedule_id)
                return
            questions_raw = schedule.get("questions") or []
            if isinstance(questions_raw, str):
                import json as _json
                try:
                    questions_raw = _json.loads(questions_raw)
                except Exception:
                    questions_raw = []
            questions = questions_raw if questions_raw else None
            participants_filter = schedule.get("participants") or []
            channel_id = schedule.get("channel_id") or channel_id
        else:
            config = db.get_workspace_config(team_id) or {}
            qs = config.get("questions") or []
            if isinstance(qs, str):
                import json as _json
                try:
                    qs = _json.loads(qs)
                except Exception:
                    qs = []
            questions = qs if qs else None
            participants_filter = []

        members = db.get_active_members(team_id)
        if participants_filter:
            members = [m for m in members if m["user_id"] in participants_filter]
    except Exception as exc:
        logger.error("Could not load data for standup %s/%s: %s", team_id, schedule_id, exc)
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

    # Evaluate low_participation workflow rules
    try:
        import db  # noqa: PLC0415
        from workflow import evaluate_rules  # noqa: PLC0415
        stats = db.get_participation_stats(team_id, days=1)
        total = len(stats)
        responded = sum(1 for s in stats if (s.get("responses") or 0) > 0)
        pct = int((responded / total * 100) if total else 100)
        evaluate_rules(team_id, "low_participation", {"participation_pct": pct, "team": team_id}, client)
    except Exception as exc:
        logger.warning("Participation workflow rules failed for %s: %s", team_id, exc)


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


def _send_manager_digest(team_id: str) -> None:
    """Send today's standup digest to the configured manager email (if enabled)."""
    try:
        import db  # noqa: PLC0415
        from mailer import send_manager_digest  # noqa: PLC0415
        config = db.get_workspace_config(team_id)
        if not config:
            return
        if not config.get("manager_digest_enabled"):
            return
        manager_email = config.get("manager_email") or ""
        if not manager_email:
            return
        inst = db.get_installation(team_id)
        workspace_name = inst.get("team_name", team_id) if inst else team_id
        standups = db.get_standups(team_id, days=1)
        date_str = datetime.now().strftime("%Y-%m-%d")
        send_manager_digest(
            manager_email=manager_email,
            workspace_name=workspace_name,
            standups=standups,
            date_str=date_str,
        )
    except Exception as exc:
        logger.warning("Manager digest failed for %s: %s", team_id, exc)


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
        reminder_days = schedule_days
        if reminder_dt.date() < standup_dt.date():
            day_map = {"mon": "sun", "tue": "mon", "wed": "tue", "thu": "wed", "fri": "thu", "sat": "fri", "sun": "sat"}
            reminder_days = ",".join(day_map.get(d, d) for d in schedule_days.split(","))
        scheduler.add_job(
            _send_reminder_to_workspace,
            trigger=CronTrigger(
                hour=reminder_dt.hour,
                minute=reminder_dt.minute,
                day_of_week=reminder_days,
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

    # Manager digest job — runs daily at standup time (after standup completes)
    # Use a 30-minute offset after the standup time so responses are in by then
    standup_plus_30 = datetime(2000, 1, 1, int(hour), int(minute)) + timedelta(minutes=30)
    scheduler.add_job(
        _send_manager_digest,
        trigger=CronTrigger(
            hour=standup_plus_30.hour,
            minute=standup_plus_30.minute,
            day_of_week=schedule_days,
            timezone=tz,
        ),
        args=[team_id],
        id=f"manager_digest_{team_id}",
        name=f"Manager Digest — {team_id}",
        replace_existing=True,
    )


def register_schedule_job(scheduler: BackgroundScheduler, schedule: dict) -> None:
    """Register a cron job for a standup_schedules row."""
    team_id = schedule["team_id"]
    bot_token = schedule["bot_token"]
    schedule_id = schedule["id"]
    schedule_time = schedule.get("schedule_time", "09:00")
    schedule_tz = schedule.get("schedule_tz", "UTC")
    schedule_days = schedule.get("schedule_days", "mon,tue,wed,thu,fri")
    channel_id = schedule.get("channel_id") or ""
    reminder_minutes = int(schedule.get("reminder_minutes") or 0)

    try:
        hour, minute = schedule_time.split(":")
        tz = pytz.timezone(schedule_tz)
    except Exception as exc:
        logger.error("Invalid schedule config %s: %s", schedule_id, exc)
        return

    trigger = CronTrigger(hour=int(hour), minute=int(minute), day_of_week=schedule_days, timezone=tz)
    job_id = f"schedule_{team_id}_{schedule_id}"
    scheduler.add_job(
        _send_standup_to_workspace,
        trigger=trigger,
        args=[team_id, bot_token, channel_id, schedule_id],
        id=job_id,
        name=f"{schedule.get('name', 'Standup')} — {team_id}",
        replace_existing=True,
    )
    logger.info("Registered schedule job %s (%s) at %s %s", schedule_id, schedule.get("name"), schedule_time, schedule_tz)

    if reminder_minutes > 0:
        standup_dt = datetime(2000, 1, 1, int(hour), int(minute))
        reminder_dt = standup_dt - timedelta(minutes=reminder_minutes)
        reminder_days = schedule_days
        if reminder_dt.date() < standup_dt.date():
            day_map = {"mon": "sun", "tue": "mon", "wed": "tue", "thu": "wed", "fri": "thu", "sat": "fri", "sun": "sat"}
            reminder_days = ",".join(day_map.get(d, d) for d in schedule_days.split(","))
        scheduler.add_job(
            _send_reminder_to_workspace,
            trigger=CronTrigger(hour=reminder_dt.hour, minute=reminder_dt.minute, day_of_week=reminder_days, timezone=tz),
            args=[team_id, bot_token, reminder_minutes],
            id=f"reminder_schedule_{team_id}_{schedule_id}",
            replace_existing=True,
        )


def build_scheduler(installations: list[tuple[str, str, dict]]) -> BackgroundScheduler:
    """Build scheduler from a list of (team_id, bot_token, config) tuples."""
    global _scheduler
    scheduler = BackgroundScheduler()

    for team_id, bot_token, config in installations:
        register_workspace_job(scheduler, team_id, bot_token, config)

    # Register standup_schedules jobs
    try:
        import db  # noqa: PLC0415
        all_schedules = db.get_all_active_schedules()
        for sched in all_schedules:
            register_schedule_job(scheduler, sched)
    except Exception as exc:
        logger.warning("Could not load standup_schedules: %s", exc)

    _scheduler = scheduler
    return scheduler
