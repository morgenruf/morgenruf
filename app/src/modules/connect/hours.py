"""Whether two people's working days overlap enough to meet.

Matching on availability is the difference between an introduction someone can
act on and one they cannot. Two people eight hours apart can be told to find a
time all week and still never find one.

No calendar access is involved: this uses the timezone already stored for each
member and a working window, so it needs no extra Slack scope and no OAuth.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# What a working day is, absent anything more specific. Deliberately generous:
# excluding someone because we guessed their hours is worse than one awkward
# introduction.
DEFAULT_START_HOUR = 9
DEFAULT_END_HOUR = 17

# Used only when the working days do not meet at all. Early and late rather than
# round the clock: a call at 07:00 or 20:00 is an ask, one at 03:00 is not.
EARLY_START_HOUR = 7
LATE_END_HOUR = 21


def _offset_hours(tz_name: str, when: datetime) -> float | None:
    """A zone's offset from UTC in hours, or None if the zone is unknown."""
    if not tz_name:
        return None
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return None
    off = when.astimezone(tz).utcoffset()
    return None if off is None else off.total_seconds() / 3600.0


def overlap_hours(
    tz_a: str,
    tz_b: str,
    when: datetime | None = None,
    start_hour: int = DEFAULT_START_HOUR,
    end_hour: int = DEFAULT_END_HOUR,
) -> float:
    """Hours of the working day the two share.

    An unknown timezone returns the full window rather than zero: refusing to
    match someone because their profile is incomplete is the worse failure.
    """
    when = when or datetime.now(timezone.utc)
    window = max(0, end_hour - start_hour)
    a = _offset_hours(tz_a, when)
    b = _offset_hours(tz_b, when)
    if a is None or b is None:
        return float(window)
    # Each person's working window in UTC, then the length of the intersection.
    a_start, a_end = start_hour - a, end_hour - a
    b_start, b_end = start_hour - b, end_hour - b
    return float(max(0.0, min(a_end, b_end) - max(a_start, b_start)))


def can_meet(tz_a: str, tz_b: str, minimum_hours: float = 1.0, when: datetime | None = None) -> bool:
    """Whether the pair shares at least `minimum_hours` of working day."""
    return overlap_hours(tz_a, tz_b, when) >= minimum_hours


def within_working_hours(tz_a: str, tz_b: str, when: datetime | None = None) -> bool:
    """Whether the two share an ordinary working day at all."""
    return overlap_hours(tz_a, tz_b, when) > 0


def next_slots(
    tz_a: str,
    tz_b: str,
    count: int = 3,
    duration_minutes: int = 30,
    when: datetime | None = None,
) -> list[datetime]:
    """Times, in UTC, that fall inside both working days.

    These are proposals, not free/busy: without calendar access we can say the
    hour suits them both, never that they are free. The message that carries
    them has to say so.
    """
    when = when or datetime.now(timezone.utc)
    a = _offset_hours(tz_a, when)
    b = _offset_hours(tz_b, when)
    if a is None or b is None:
        a = b = 0.0
    start = max(DEFAULT_START_HOUR - a, DEFAULT_START_HOUR - b)
    end = min(DEFAULT_END_HOUR - a, DEFAULT_END_HOUR - b)
    if end - start < duration_minutes / 60:
        # No shared working day. Saying nothing is the worst answer: the pair
        # who most need help finding a time get none, and the message looks
        # exactly as it would if the feature did not exist. Widen to the edges
        # of both days and let the caller say these are outside normal hours.
        start = max(EARLY_START_HOUR - a, EARLY_START_HOUR - b)
        end = min(LATE_END_HOUR - a, LATE_END_HOUR - b)
        if end - start < duration_minutes / 60:
            return []

    base = (when + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    slots: list[datetime] = []
    day = 0
    while len(slots) < count and day < 7:
        candidate_day = base + timedelta(days=day)
        if candidate_day.weekday() < 5:  # weekdays only
            hour = start
            while hour + duration_minutes / 60 <= end and len(slots) < count:
                slots.append(candidate_day.replace(hour=int(hour) % 24, minute=int((hour % 1) * 60)))
                hour += 2  # spread them out rather than three in a row
        day += 1
    return slots
