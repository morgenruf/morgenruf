"""When a giver's kudos day resets, and how many they have left.

The reset is midnight in the giver's own timezone. Using UTC instead would
hand someone in Auckland a fresh allowance in the middle of their afternoon
and someone in Toronto theirs at 8pm.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def day_bounds_utc(tz_name: str, now_utc: datetime) -> tuple[datetime, datetime]:
    """The giver's current local day, expressed as a UTC half-open range.

    An unknown or empty timezone falls back to UTC rather than raising: a bad
    value in the members table must not stop someone giving kudos.

    The end is computed by adding a calendar day to the local date and
    converting back, so a 23 or 25 hour day across a DST change stays one day.
    """
    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        tz = timezone.utc

    local = now_utc.astimezone(tz)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    # Add the day to the naive local date, then re-attach the zone, so the
    # offset is recomputed on the far side of a DST boundary.
    end_local = (start_local.replace(tzinfo=None) + timedelta(days=1)).replace(tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def remaining(allowance: int, used: int) -> int:
    """How many kudos the giver can still send today, never below zero.

    Clamping matters because an admin can lower the allowance after people
    have already given more than the new limit.
    """
    return max(0, int(allowance) - int(used))
