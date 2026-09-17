"""What "this morning" means, as pure functions.

The Today view answers two questions a list of schedules cannot: who was asked
today, and who has not replied yet. Both are judgement calls, so they live here
with no I/O and get tested against hand-written cases:

  * a schedule only counts today if today is one of its days *in its own
    timezone*, because a workspace can run a Monday standup in Asia/Kolkata
    that is still Sunday in UTC;
  * someone in two schedules is one person waiting, not two.

Eligibility (active, not on leave) is deliberately not decided here. It comes
in as a set from src.core.roster, so this module cannot disagree with the rest
of the app about who is away.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from src.core.db import parse_schedule_days


def _zone(name: object):
    """A tzinfo for an IANA name, falling back to UTC on anything unusable."""
    if isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except Exception:  # noqa: BLE001 - unknown name or missing tz database
            return timezone.utc
    return timezone.utc


def as_date(value: object) -> date | None:
    """Coerce a timestamp, a date or an ISO string to a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def fires_today(schedule: dict, now: datetime) -> bool:
    """Whether this schedule asked for a standup on its own local today."""
    if not schedule.get("active", True):
        return False
    local_day = now.astimezone(_zone(schedule.get("schedule_tz"))).date()
    return local_day.weekday() in parse_schedule_days(schedule.get("schedule_days"))


def expected_today(schedules: Iterable[dict], eligible: Iterable[str], now: datetime) -> list[str]:
    """Who owes a standup today, in the order the schedules ask them.

    Deduplicated across schedules: a person on both the morning and the evening
    standup is one name on the page, not two. Anyone outside `eligible` is
    dropped, which is how vacation and deactivation are honoured.
    """
    allowed = set(eligible)
    out: list[str] = []
    seen: set[str] = set()
    for schedule in schedules:
        if not fires_today(schedule, now):
            continue
        for user_id in schedule.get("participants") or []:
            if not user_id or user_id in seen or user_id not in allowed:
                continue
            seen.add(user_id)
            out.append(user_id)
    return out


def awaiting(expected: Iterable[str], answered: Iterable[str]) -> list[str]:
    """Expected people with nothing filed yet, keeping the expected order."""
    done = set(answered)
    return [user_id for user_id in expected if user_id not in done]


def blocked_from(responses: Iterable[dict]) -> list[dict]:
    """Today's responses that reported a blocker.

    Reads has_blockers rather than re-judging the text: migration 024 already
    settled which stored answers are real blockers, and a second opinion here
    would quietly contradict the Slack report.
    """
    out = []
    for row in responses:
        if not row.get("has_blockers"):
            continue
        out.append(
            {
                "user_id": row.get("user_id"),
                "real_name": row.get("real_name"),
                "blockers": row.get("blockers"),
                "submitted_at": row.get("submitted_at"),
            }
        )
    return out


def next_chat_date(program: dict | None, today: date) -> date | None:
    """When the next coffee chat round falls, or None without a programme.

    A round already on the books wins. Otherwise the date is derived the same
    way connect's own scheduler derives it, from the last round plus the
    cadence, so the two cannot disagree. A programme that has never run is due
    the moment its job next fires, which is today at the earliest.
    """
    if not program:
        return None
    scheduled = as_date(program.get("next_scheduled"))
    if scheduled:
        return scheduled
    last = as_date(program.get("last_round"))
    if last is None:
        return today
    try:
        weeks = max(1, int(program.get("interval_weeks") or 1))
    except (TypeError, ValueError):
        weeks = 1
    return last + timedelta(days=weeks * 7)
