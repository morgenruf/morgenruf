"""The daily pass: post today's celebrations, then ask people for missing dates.

One cron job per workspace, planned through plan_jobs so module job
reconciliation keeps it (and removes it when the module is switched off or
the settings are cleared). It fires at the post time in the Celebrations
timezone and then once an hour for the next few hours. Only the first firing
normally does anything; the later ones exist so a pod that was down at post
time still posts that day. celebration_posts makes every firing after the
first a no-op, on any number of pods.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from src.core.scheduler import JobSpec
from src.core.timezones import canonical_tz

logger = logging.getLogger(__name__)

MODULE_NAME = "celebrations"
# Catch-up firings after the post time, one an hour. Eight keeps every firing
# inside a working day for any sensible post time.
CATCH_UP_HOURS = 8
# DMs asking for dates sent per pass. The rest go on the next hourly pass.
NUDGE_BATCH = 100
# The pause between DMs, so a large workspace does not hit Slack's limits.
DM_PAUSE_SECONDS = 0.5
# "Ask for dates" reaches the same person at most this often.
ASK_AGAIN_AFTER_DAYS = 30
REACTION = "tada"
REACTION_SCOPE = "reactions:write"


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


def plan_jobs(ctx: dict) -> list[JobSpec]:
    """The daily pass for this workspace, once the settings allow one.

    The post time and timezone are part of the job key, so changing either
    replaces the job on the next reconcile instead of leaving the old trigger
    in place. The job carries only the team id: the bot token is read when it
    runs, because tokens rotate.
    """
    import src.modules.celebrations.db as cdb  # noqa: PLC0415

    team_id = ctx["team_id"]
    try:
        settings = cdb.get_settings(team_id)
    except Exception as exc:
        logger.warning("celebrations could not plan jobs for %s: %s", team_id, exc)
        return []
    if not cdb.is_ready(settings):
        return []
    at = _parse_time(settings.get("post_time") or cdb.DEFAULT_POST_TIME)
    tz = canonical_tz(settings.get("timezone"))
    if at is None or _zone(tz) is None:
        logger.warning("celebrations: unusable post time or timezone for %s", team_id)
        return []
    hour, minute = at
    last = min(hour + CATCH_UP_HOURS, 23)
    return [
        JobSpec(
            key=f"daily:{hour:02d}{minute:02d}:{tz}",
            trigger=CronTrigger(hour=f"{hour}-{last}", minute=minute, timezone=tz),
            func=run_daily,
            args=(team_id,),
        )
    ]


def bot_client(team_id: str):
    """A WebClient on the workspace's current bot token, or None."""
    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        import src.core.db as db  # noqa: PLC0415

        inst = db.get_installation(team_id)
        token = inst.get("bot_token") if inst else None
        return WebClient(token=token) if token else None
    except Exception:
        logger.exception("celebrations: no Slack client for %s", team_id)
        return None


def local_today(tz_name: str, now: datetime | None = None) -> date | None:
    """The calendar date in the Celebrations timezone, which is the one that counts."""
    zone = _zone(tz_name)
    if zone is None:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(zone).date()


def people_from_rows(rows: list[dict]):
    from src.modules.celebrations.messages import first_name  # noqa: PLC0415
    from src.modules.celebrations.rules import Person  # noqa: PLC0415

    return [
        Person(
            user_id=r["user_id"],
            name=first_name(r.get("display_name"), r.get("real_name")),
            birth_month=r.get("birth_month"),
            birth_day=r.get("birth_day"),
            start_date=r.get("start_date"),
        )
        for r in rows
    ]


def _fill_names(client, celebration):
    """Look up a first name in Slack for anyone the members table has no name for."""
    from dataclasses import replace  # noqa: PLC0415

    from src.modules.celebrations.messages import first_name  # noqa: PLC0415

    people = []
    for person in celebration.people:
        if not person.name and client is not None:
            try:
                user = (client.users_info(user=person.user_id) or {}).get("user") or {}
                profile = user.get("profile") or {}
                name = first_name(profile.get("first_name"), profile.get("display_name"), profile.get("real_name"))
                person = replace(person, name=name)
            except Exception:
                logger.info("celebrations: no name for %s, posting without it", person.user_id)
        people.append(person)
    # Alphabetical by the names the post will show.
    people.sort(key=lambda h: ((h.name or "").lower(), h.user_id))
    return replace(celebration, people=tuple(people))


def can_react(team_id: str) -> bool:
    """Whether this installation granted reactions:write.

    Workspaces that installed before the scope existed do not hold it until
    they reinstall. They still get the post, just not the reaction.
    """
    import src.core.db as db  # noqa: PLC0415

    return REACTION_SCOPE in db.granted_scopes(team_id)


def post_celebration(client, team_id: str, channel_id: str, celebration, today: date, cal, react: bool) -> str | None:
    """Claim, post and react for one celebration. Returns the message ts, or None.

    The claim comes first. If Slack refuses the post the claim is released,
    so the next hourly firing tries again; a post Slack accepted is never
    sent a second time.
    """
    import src.modules.celebrations.db as cdb  # noqa: PLC0415
    from src.modules.celebrations.messages import celebration_text  # noqa: PLC0415

    kind, day = celebration.kind, celebration.day
    if not cdb.claim_post(team_id, kind, day, today, channel_id, celebration.user_ids):
        return None
    try:
        text = celebration_text(_fill_names(client, celebration), today, cal)
        response = client.chat_postMessage(channel=channel_id, text=text, unfurl_links=False, unfurl_media=False)
        ts = response.get("ts") if response else None
    except Exception:
        logger.exception("celebrations: could not post the %s for %s in %s", kind, day, team_id)
        try:
            cdb.release_post(team_id, kind, day)
        except Exception:
            logger.exception("celebrations: could not release the claim for %s %s", kind, day)
        return None
    if ts:
        cdb.record_post(team_id, kind, day, ts)
    if react and ts:
        try:
            client.reactions_add(channel=channel_id, timestamp=ts, name=REACTION)
        except Exception as exc:
            # The post is what matters. A missing reaction is not worth a retry.
            logger.info("celebrations: no reaction on %s in %s: %s", ts, team_id, exc)
    return ts


def run_daily(team_id: str, now: datetime | None = None) -> list[str]:
    """One firing of the daily pass. Returns the ts of every message posted."""
    import src.modules.celebrations.db as cdb  # noqa: PLC0415
    from src.core.modules import is_active_for  # noqa: PLC0415
    from src.core.workspace_calendar import load_calendar  # noqa: PLC0415
    from src.modules.celebrations.rules import due  # noqa: PLC0415

    if not is_active_for(team_id, MODULE_NAME):
        return []
    settings = cdb.get_settings(team_id)
    if not cdb.is_ready(settings):
        return []
    today = local_today(settings["timezone"], now)
    if today is None:
        return []
    cal = load_calendar(team_id)
    if not cal.is_working_day(today):
        return []

    client = bot_client(team_id)
    if client is None:
        return []

    posted: list[str] = []
    celebrations = due(
        people_from_rows(cdb.celebrants(team_id)),
        cal,
        today,
        birthdays=bool(settings.get("birthdays", True)),
        anniversaries=bool(settings.get("anniversaries", True)),
    )
    if celebrations:
        react = can_react(team_id)
        for c in celebrations:
            ts = post_celebration(client, team_id, settings["channel_id"], c, today, cal, react)
            if ts:
                posted.append(ts)

    try:
        cdb.purge_old_posts(team_id)
    except Exception:
        logger.warning("celebrations: could not purge old posts for %s", team_id)

    try:
        send_first_nudges(client, team_id, settings["channel_id"])
    except Exception:
        logger.exception("celebrations: nudge pass failed for %s", team_id)
    return posted


# ── Asking for dates ────────────────────────────────────────────────────────


def workspace_people(client, team_id: str) -> dict[str, str]:
    """Every active human in the workspace, user id to first name.

    The Slack directory, because the people to ask are the whole company and
    the members table holds only people the bot has met. Falls back to the
    members table when Slack cannot be read.
    """
    from src.core.slack_users import fetch_workspace_directory  # noqa: PLC0415
    from src.modules.celebrations.messages import first_name  # noqa: PLC0415

    directory = None
    if client is not None:
        try:
            directory, _error = fetch_workspace_directory(client)
        except Exception:
            directory = None
    if directory:
        out = {}
        for uid, user in directory.items():
            profile = user.get("profile") or {}
            out[uid] = first_name(profile.get("first_name"), profile.get("display_name"), user.get("real_name"))
        return out
    import src.core.db as db  # noqa: PLC0415

    return {r["user_id"]: first_name(r.get("display_name"), r.get("real_name")) for r in db.get_active_members(team_id)}


def missing_dates(team_id: str, people: dict[str, str], cooldown_days: int | None) -> list[str]:
    """Who of `people` may be asked for dates now, in a stable order.

    No birthday and no start date, not opted out of being celebrated, and not
    asked before (or, with a cooldown, not asked within it).
    """
    import src.core.db as db  # noqa: PLC0415

    profiles = {p["user_id"]: p for p in db.list_member_profiles(team_id, include_departed=True)}
    now = datetime.now(timezone.utc)
    out = []
    for uid in sorted(people, key=lambda u: ((people[u] or "").lower(), u)):
        p = profiles.get(uid)
        if p:
            if p.get("birth_month") or p.get("start_date") or not p.get("celebrate", True):
                continue
            asked = p.get("nudged_at")
            if asked is not None:
                if cooldown_days is None:
                    continue
                if asked.tzinfo is None:
                    asked = asked.replace(tzinfo=timezone.utc)
                if (now - asked).days < cooldown_days:
                    continue
        out.append(uid)
    return out


def send_nudge(client, user_id: str, name: str, channel_id: str) -> bool:
    from src.modules.celebrations.messages import nudge_blocks, nudge_text  # noqa: PLC0415

    try:
        client.chat_postMessage(
            channel=user_id, text=nudge_text(name, channel_id), blocks=nudge_blocks(name, channel_id)
        )
        return True
    except Exception as exc:
        # Not retried: the claim stays, so a person who cannot be messaged is
        # not tried again on every pass.
        logger.info("celebrations: could not ask %s for dates: %s", user_id, exc)
        return False


def send_nudges(client, team_id: str, channel_id: str, user_ids, names: dict[str, str], cooldown_days=None) -> int:
    """Claim, then DM. Returns how many DMs were sent."""
    import src.core.db as db  # noqa: PLC0415

    claimed = db.claim_profile_nudges(team_id, user_ids, cooldown_days=cooldown_days)
    sent = 0
    for index, uid in enumerate(claimed):
        if index:
            time.sleep(DM_PAUSE_SECONDS)
        if send_nudge(client, uid, names.get(uid, ""), channel_id):
            sent += 1
    return sent


def send_first_nudges(client, team_id: str, channel_id: str) -> int:
    """The one-time DM to everyone with no dates, a batch per pass."""
    people = workspace_people(client, team_id)
    targets = missing_dates(team_id, people, cooldown_days=None)[:NUDGE_BATCH]
    if not targets:
        return 0
    sent = send_nudges(client, team_id, channel_id, targets, people)
    if sent:
        logger.info("celebrations: asked %d people in %s for their dates", sent, team_id)
    return sent
