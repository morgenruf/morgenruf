"""The weekly pulse round and the hourly tick.

The round job carries only the team id; the bot token is read when it runs.
The (team_id, sent_on) unique key makes send_round safe to run twice, on two
pods, or after a misfire: only the call that created the day's round sends.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.core.scheduler import JobSpec
from src.core.timezones import canonical_tz

logger = logging.getLogger(__name__)

MODULE_NAME = "pulse"
ROUND_HOURS = 72
DM_PAUSE_SECONDS = 0.5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _zone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def plan_jobs(ctx: dict) -> list[JobSpec]:
    import src.modules.pulse.db as pdb  # noqa: PLC0415

    team_id = ctx["team_id"]
    # Raises on a failed read: module job sync then keeps the live jobs, where
    # an empty plan would delete them.
    program = pdb.get_program(team_id)
    tick_job = JobSpec(key="tick", trigger=IntervalTrigger(hours=1), func=tick, args=(team_id,))
    if not program.get("enabled"):
        # Switched off with a round still holding who answered: keep the tick
        # until that round has closed and been scrubbed.
        return [tick_job] if pdb.unscrubbed_count(team_id) > 0 else []
    tz = canonical_tz(program.get("timezone") or "UTC")
    if _zone(tz) is None:
        # No weekly round without a usable clock, but the tick stays: it is
        # what closes and scrubs the rounds already sent.
        logger.warning("pulse: unusable timezone for %s", team_id)
        return [tick_job]
    dow, hour, minute = int(program["day_of_week"]), int(program["hour"]), int(program["minute"])
    return [
        JobSpec(
            # The schedule is in the key, so changing it replaces the job.
            key=f"round:{dow}:{hour}:{minute}:{tz}",
            trigger=CronTrigger(day_of_week=dow, hour=hour, minute=minute, timezone=tz),
            func=send_round,
            args=(team_id,),
        ),
        tick_job,
    ]


def bot_client(team_id: str):
    """A WebClient on the workspace's current bot token, or None."""
    from slack_sdk import WebClient  # noqa: PLC0415

    try:
        from src.core.scheduler import _fresh_bot_token  # noqa: PLC0415

        token = _fresh_bot_token(team_id, "")
    except Exception:
        token = ""
    return WebClient(token=token) if token else None


def _active(team_id: str) -> bool:
    from src.core.modules import is_active_for  # noqa: PLC0415

    return is_active_for(team_id, MODULE_NAME)


def _audience(client, team_id: str, channel_id: str | None) -> list[str]:  # noqa: ANN001
    """The people to ask: a channel's humans, or every active member. Raises on a failed read."""
    import src.core.db as db  # noqa: PLC0415
    from src.core.standup_invites import channel_humans  # noqa: PLC0415

    if channel_id:
        return channel_humans(client, channel_id)
    return [m["user_id"] for m in db.get_active_members(team_id) if m.get("user_id")]


def send_round(team_id: str) -> int:
    """Start this week's round and DM everyone the first question. Returns how many were asked."""
    import src.core.analytics as analytics  # noqa: PLC0415
    import src.modules.pulse.db as pdb  # noqa: PLC0415
    from src.core.timezones import local_today  # noqa: PLC0415
    from src.modules.pulse import blocks  # noqa: PLC0415

    if not _active(team_id):
        return 0
    program = pdb.get_program(team_id)
    if not program.get("enabled"):
        return 0
    client = bot_client(team_id)
    if client is None:
        return 0
    try:
        audience = _audience(client, team_id, program.get("audience_channel_id"))
    except Exception as exc:
        logger.warning("pulse: could not read the audience for %s: %s", team_id, exc)
        return 0

    now = _now()
    created = pdb.create_round(
        team_id, local_today(program.get("timezone") or "UTC"), now + timedelta(hours=ROUND_HOURS)
    )
    if created is None:
        return 0
    round_id = created["id"]

    # Someone is invited only once their DM arrived, so the response rate
    # counts people who could answer. A failed DM is a count in the log.
    invited, failed = 0, 0
    for user_id in audience:
        try:
            client.chat_postMessage(channel=user_id, text=blocks.INTRO, blocks=blocks.mood_question(round_id))
        except Exception as exc:
            failed += 1
            logger.info("pulse: a round %s DM failed: %s", round_id, exc)
        else:
            try:
                invited = pdb.record_invites(round_id, [user_id])
            except Exception as exc:
                logger.warning("pulse: could not record an invite on round %s: %s", round_id, exc)
        if DM_PAUSE_SECONDS:
            time.sleep(DM_PAUSE_SECONDS)
    analytics.capture("pulse_round_sent", team_id, invited=invited)
    logger.info("pulse: round %s for %s sent to %d, %d DM(s) failed", round_id, team_id, invited, failed)
    return invited


def tick(team_id: str) -> int:
    """Close rounds that are due, then remind, once, the people who have not
    answered a round that closes within two days.

    A round past closes_at refuses answers on its own. Closing it here deletes
    who answered and keeps only the counts, and runs whether or not the module
    is still on, so switching Pulse off never leaves that list behind.
    """
    import src.modules.pulse.db as pdb  # noqa: PLC0415
    from src.modules.pulse import blocks  # noqa: PLC0415

    try:
        closed = pdb.close_due_rounds(team_id)
        if closed:
            logger.info("pulse: closed %d round(s) for %s", len(closed), team_id)
    except Exception:
        logger.exception("pulse: could not close due rounds for %s", team_id)
    if not _active(team_id):
        return 0
    due = pdb.rounds_to_remind(team_id)
    if not due:
        return 0
    client = bot_client(team_id)
    if client is None:
        return 0
    reminded = 0
    for row in due:
        if not pdb.claim_reminder(row["id"]):
            continue
        for user_id in pdb.non_respondents(row["id"]):
            try:
                client.chat_postMessage(channel=user_id, text=blocks.REMINDER)
                reminded += 1
            except Exception as exc:
                logger.info("pulse: a reminder for round %s failed: %s", row["id"], exc)
            if DM_PAUSE_SECONDS:
                time.sleep(DM_PAUSE_SECONDS)
        logger.info("pulse: reminded %d people for round %s", reminded, row["id"])
    return reminded
