"""The workspace calendar: working days and company holidays.

Core, not a module, because more than one module plans around the same
company calendar. Celebrations moves a celebration that falls on a day off to
the last working day before it; Onboarding buddies will move a task to the
next working day after. HR keeps one list, and neither module reads the
other's settings.

The Calendar class holds the rules with no I/O, so they can be tested with
plain dates. The module-level helpers load a workspace's calendar first.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_WORKING_DAYS = "mon,tue,wed,thu,fri"

MAX_HOLIDAY_NAME = 80
# Holidays further back than this are purged. Nothing plans backwards.
HOLIDAY_RETENTION_DAYS = 365
# A company's holiday list is a few dozen rows a year. A thousand leaves room
# for several years pasted at once and keeps one request bounded.
MAX_HOLIDAY_IMPORT_ROWS = 1000

# How far the working day search looks before giving up. A year of days off in
# a row is not a calendar anyone keeps, so running out means "none".
_SEARCH_LIMIT = 366

_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


class CalendarError(ValueError):
    """A working days value or a holiday that cannot be stored."""


def parse_working_days(spec: object) -> frozenset[int]:
    """Weekday numbers (Monday is 0) from "mon,tue,wed". Strict.

    Unlike standup's schedule_days parser this refuses anything it does not
    recognise instead of falling back to a default, because it validates what
    an admin typed, and a week with no working days is refused too.
    """
    if isinstance(spec, (list, tuple, set, frozenset)):
        tokens = [str(t) for t in spec]
    elif isinstance(spec, str):
        tokens = spec.split(",")
    else:
        raise CalendarError("Pick at least one working day.")
    days: set[int] = set()
    for token in tokens:
        key = token.strip().lower()[:3]
        if not key:
            continue
        if key not in WEEKDAY_KEYS:
            raise CalendarError(f"'{token.strip()}' is not a day of the week.")
        days.add(WEEKDAY_KEYS.index(key))
    if not days:
        raise CalendarError("Pick at least one working day.")
    return frozenset(days)


def format_working_days(days) -> str:
    """The stored spelling, always in week order: "mon,tue,wed,thu,fri"."""
    return ",".join(WEEKDAY_KEYS[d] for d in sorted(set(days)))


def working_day_keys(spec: object) -> list[str]:
    """The stored value as a list of keys, falling back to Monday to Friday."""
    try:
        return [WEEKDAY_KEYS[d] for d in sorted(parse_working_days(spec or DEFAULT_WORKING_DAYS))]
    except CalendarError:
        return DEFAULT_WORKING_DAYS.split(",")


@dataclass
class Calendar:
    """One workspace's working week and holiday list."""

    working_days: frozenset[int] = frozenset(range(5))
    holidays: dict[date, str] = field(default_factory=dict)

    def is_holiday(self, day: date) -> bool:
        return day in self.holidays

    def is_weekend(self, day: date) -> bool:
        """Outside the working week, whatever the name of the day."""
        return day.weekday() not in self.working_days

    def is_working_day(self, day: date) -> bool:
        return not self.is_weekend(day) and not self.is_holiday(day)

    def previous_working_day(self, day: date) -> date | None:
        """The last working day strictly before `day`, or None."""
        for back in range(1, _SEARCH_LIMIT + 1):
            candidate = day - timedelta(days=back)
            if self.is_working_day(candidate):
                return candidate
        return None

    def next_working_day(self, day: date) -> date | None:
        """The first working day strictly after `day`, or None."""
        for ahead in range(1, _SEARCH_LIMIT + 1):
            candidate = day + timedelta(days=ahead)
            if self.is_working_day(candidate):
                return candidate
        return None

    def days_off_after(self, day: date) -> list[date]:
        """The non-working days between `day` and the next working day.

        Friday in a Monday to Friday week gives Saturday and Sunday. Empty when
        tomorrow is a working day.
        """
        following = self.next_working_day(day)
        if following is None:
            return []
        return [day + timedelta(days=n) for n in range(1, (following - day).days)]


def from_rows(working_days: object, holidays) -> Calendar:
    """Build a Calendar from the stored working days and holiday rows."""
    try:
        days = parse_working_days(working_days or DEFAULT_WORKING_DAYS)
    except CalendarError:
        days = parse_working_days(DEFAULT_WORKING_DAYS)
    return Calendar(working_days=days, holidays={h["date"]: h["name"] for h in holidays or ()})


def load_calendar(team_id: str) -> Calendar:
    """The workspace's calendar, read from the database."""
    import src.core.db as db  # noqa: PLC0415

    return from_rows(db.get_working_days(team_id), db.list_holidays(team_id))


def is_working_day(team_id: str, day: date) -> bool:
    return load_calendar(team_id).is_working_day(day)


def previous_working_day(team_id: str, day: date) -> date | None:
    return load_calendar(team_id).previous_working_day(day)


def next_working_day(team_id: str, day: date) -> date | None:
    return load_calendar(team_id).next_working_day(day)


# ── Holidays ────────────────────────────────────────────────────────────────


def clean_holiday_name(name: object) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        raise CalendarError("Give the holiday a name.")
    if len(text) > MAX_HOLIDAY_NAME:
        raise CalendarError(f"Keep the name under {MAX_HOLIDAY_NAME} characters.")
    return text


def parse_holiday_date(text: object) -> date:
    raw = str(text or "").strip()
    match = _ISO_DATE.match(raw)
    if not match:
        raise CalendarError(f"Date {raw!r} is not YYYY-MM-DD.")
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        raise CalendarError(f"{raw} is not a real date.") from None


def read_holiday_csv(text: str, today: date | None = None) -> list[dict]:
    """Rows of a `date,name` file, each marked ready or invalid.

    A header row is optional. A date already given earlier in the same file is
    invalid rather than silently replacing the first. A date more than a year
    back is refused, because the nightly purge would delete it anyway.
    """
    today = today or datetime.now(timezone.utc).date()
    oldest = today - timedelta(days=HOLIDAY_RETENTION_DAYS)
    reader = csv.reader(io.StringIO((text or "").lstrip("﻿")))
    rows: list[dict] = []
    seen: set[date] = set()
    for number, cells in enumerate(reader, 1):
        cells = [c.strip() for c in cells]
        if not any(cells):
            continue
        if number == 1 and cells[0].lower() == "date":
            continue
        if len(rows) >= MAX_HOLIDAY_IMPORT_ROWS:
            raise CalendarError(f"Import at most {MAX_HOLIDAY_IMPORT_ROWS} holidays at once.")
        row = {
            "line": number,
            "date": None,
            "name": cells[1] if len(cells) > 1 else "",
            "status": "ready",
            "error": None,
        }
        try:
            day = parse_holiday_date(cells[0])
            row["date"] = day
            row["name"] = clean_holiday_name(row["name"])
            if day < oldest:
                raise CalendarError("More than a year ago.")
            if day in seen:
                raise CalendarError("This date is already in the file.")
            seen.add(day)
        except CalendarError as exc:
            row["status"], row["error"] = "invalid", str(exc)
        rows.append(row)
    if not rows:
        raise CalendarError("The file has no holidays. Use one `date,name` per line.")
    return rows
