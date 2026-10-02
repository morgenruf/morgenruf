"""Posting the questions: one cron job per active channel.

Planned through plan_jobs, so module job reconciliation adds, replaces and
removes the jobs as channels change. Each job fires at the channel's time on
its days, then once an hour for a few hours, so a pod that was down at post
time still posts that day. watercooler_posts makes every firing after the
first a no-op, on any number of pods.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from src.core.scheduler import JobSpec
from src.core.timezones import canonical_tz

logger = logging.getLogger(__name__)

MODULE_NAME = "watercooler"
CATCH_UP_HOURS = 3
REACTION_SCOPE = "reactions:write"
# Slack errors that mean "this channel cannot take posts from us": pause it
# and tell whoever set it up, rather than failing every firing.
_GONE = ("not_in_channel", "channel_not_found", "is_archived")
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_time(value: str) -> tuple[int, int] | None:
    try:
        hour, minute = (int(part) for part in (value or "").split(":"))
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _zone(name: str | None) -> ZoneInfo | None:
    try:
        return ZoneInfo(canonical_tz(name)) if name else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _days(spec: str | None) -> list[str]:
    return [d for d in (spec or "").split(",") if d in _WEEKDAYS]


def plan_jobs(ctx: dict) -> list[JobSpec]:
    """One job per active channel with a usable time, timezone and at least one day.

    Time, timezone and days are in the key, so changing any of them replaces
    the job on the next reconcile. A failed read raises, which keeps the live
    jobs instead of deleting them.
    """
    import src.modules.watercooler.db as wdb  # noqa: PLC0415

    team_id = ctx["team_id"]
    specs: list[JobSpec] = []
    for ch in wdb.list_channels(team_id):
        if not ch.get("active", True):
            continue
        at = _parse_time(ch.get("post_time") or "")
        tz = canonical_tz(ch.get("timezone"))
        days = _days(ch.get("days"))
        if at is None or _zone(tz) is None or not days:
            logger.warning("watercooler: unusable schedule for %s in %s", ch.get("channel_id"), team_id)
            continue
        hour, minute = at
        last = min(hour + CATCH_UP_HOURS, 23)
        day_spec = ",".join(days)
        specs.append(
            JobSpec(
                key=f"post:{ch['channel_id']}:{hour:02d}{minute:02d}:{tz}:{day_spec}",
                trigger=CronTrigger(day_of_week=day_spec, hour=f"{hour}-{last}", minute=minute, timezone=tz),
                func=run_post,
                args=(team_id, ch["channel_id"]),
            )
        )
    return specs


def bot_client(team_id: str):
    """A WebClient on the workspace's current bot token, or None."""
    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        import src.core.db as db  # noqa: PLC0415

        inst = db.get_installation(team_id)
        token = inst.get("bot_token") if inst else None
        return WebClient(token=token) if token else None
    except Exception:
        logger.exception("watercooler: no Slack client for %s", team_id)
        return None


def can_react(team_id: str) -> bool:
    """Whether this installation granted reactions:write. Without it the post goes out bare."""
    import src.core.db as db  # noqa: PLC0415

    try:
        return REACTION_SCOPE in db.granted_scopes(team_id)
    except Exception:
        return False


def local_today(tz_name: str, now: datetime | None = None) -> date | None:
    zone = _zone(tz_name)
    if zone is None:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(zone).date()


def _slack_error(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    error = response.get("error") if hasattr(response, "get") else None
    return error if isinstance(error, str) else str(exc)


def _dm(client, user_id: str, text: str) -> None:
    if not user_id:
        return
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception as exc:
        logger.info("watercooler: could not DM %s: %s", user_id, exc)


def question_for(team_id: str, ch: dict) -> tuple[str, str] | None:
    """The next (ref, text) for this channel, or None when it has nothing left to ask."""
    import src.modules.watercooler.db as wdb  # noqa: PLC0415
    from src.modules.watercooler import bank, rotation  # noqa: PLC0415

    channel_id = ch["channel_id"]
    source = ch.get("source") or wdb.DEFAULT_SOURCE
    categories = [c for c in (ch.get("categories") or wdb.DEFAULT_CATEGORIES).split(",") if c]
    custom = wdb.list_questions(team_id, include_archived=False) if source in ("custom", "both") else []
    texts = {rotation.custom_ref(q["id"]): q["text"] for q in custom}
    refs = rotation.pool(source, categories, wdb.hidden_keys(team_id), [q["id"] for q in custom])
    ref = rotation.pick(refs, wdb.history(team_id, channel_id))
    if ref is None:
        return None
    if ref.startswith("b:"):
        return ref, bank.BY_KEY[ref[2:]].text
    return ref, texts[ref]


def run_post(team_id: str, channel_id: str, now: datetime | None = None, force: bool = False) -> str | None:
    """One firing for one channel. Returns the message ts when a question was posted.

    `force` is "Post one now": it skips the day-of-week and holiday checks
    but still counts as that day's post, so the scheduled one is skipped.
    """
    import src.modules.watercooler.db as wdb  # noqa: PLC0415
    from src.core.modules import is_active_for  # noqa: PLC0415
    from src.core.workspace_calendar import load_calendar  # noqa: PLC0415
    from src.modules.watercooler import messages  # noqa: PLC0415

    if not is_active_for(team_id, MODULE_NAME):
        return None
    ch = wdb.get_channel(team_id, channel_id)
    if not ch or (not ch.get("active", True) and not force):
        return None
    today = local_today(ch.get("timezone") or "", now)
    if today is None:
        return None
    if not force:
        if _WEEKDAYS[today.weekday()] not in _days(ch.get("days")):
            return None
        cal = load_calendar(team_id)
        if not cal.is_working_day(today):
            return None

    client = bot_client(team_id)
    if client is None:
        return None

    picked = question_for(team_id, ch)
    if picked is None:
        # Nothing to ask. Paused so this is said once, not at every firing.
        if wdb.set_channel_active(team_id, channel_id, False, "empty_pool"):
            _dm(client, ch.get("created_by") or "", messages.empty_pool_text(channel_id))
        return None
    ref, question = picked
    if not wdb.claim_post(team_id, channel_id, today, ref):
        return None
    try:
        response = client.chat_postMessage(
            channel=channel_id,
            text=messages.post_text(question),
            blocks=messages.post_blocks(question),
            unfurl_links=False,
            unfurl_media=False,
        )
        ts = response.get("ts") if response else None
    except Exception as exc:
        error = _slack_error(exc)
        try:
            wdb.release_post(team_id, channel_id, today)
        except Exception:
            logger.exception("watercooler: could not release the claim for %s", channel_id)
        if error in _GONE:
            if wdb.set_channel_active(team_id, channel_id, False, "not_in_channel"):
                _dm(client, ch.get("created_by") or "", messages.not_in_channel_text(channel_id))
        else:
            logger.warning("watercooler: could not post in %s for %s: %s", channel_id, team_id, error)
        return None
    if ts:
        wdb.record_post(team_id, channel_id, today, ts)
        if can_react(team_id):
            try:
                client.reactions_add(channel=channel_id, timestamp=ts, name=messages.REACTION)
            except Exception as exc:
                logger.info("watercooler: no reaction on %s: %s", ts, exc)
    try:
        wdb.purge_old_posts(team_id)
    except Exception:
        logger.warning("watercooler: could not purge old posts for %s", team_id)
    return ts
