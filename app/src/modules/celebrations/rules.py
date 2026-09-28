"""Who is celebrated on which day. No I/O, so every rule is testable with dates.

The daily pass runs on working days only. A working day covers itself plus
every day off up to the next working day, so a Saturday birthday is posted on
Friday and a birthday on a Monday holiday is posted on the Friday before.
"""

from __future__ import annotations

import calendar as _stdlib_calendar
from dataclasses import dataclass
from datetime import date, timedelta

from src.core.workspace_calendar import Calendar

BIRTHDAY = "birthday"
ANNIVERSARY = "anniversary"


@dataclass(frozen=True)
class Person:
    """One profile, reduced to what celebrating needs."""

    user_id: str
    name: str = ""
    birth_month: int | None = None
    birth_day: int | None = None
    start_date: date | None = None


@dataclass(frozen=True)
class Honoree:
    user_id: str
    name: str = ""
    # Completed years, for an anniversary. None for a birthday.
    years: int | None = None


@dataclass(frozen=True)
class Celebration:
    """One message: every person celebrating one kind of occasion on one day."""

    kind: str
    day: date
    people: tuple[Honoree, ...]

    @property
    def user_ids(self) -> list[str]:
        return [p.user_id for p in self.people]


def occurs_on(month: int, day: int, year: int) -> date | None:
    """The date a day-and-month falls on in `year`.

    29 February is celebrated on 28 February in a year without one. Anything
    else that is not a real date (a corrupt row) gives None.
    """
    if month == 2 and day == 29 and not _stdlib_calendar.isleap(year):
        return date(year, 2, 28)
    try:
        return date(year, month, day)
    except (TypeError, ValueError):
        return None


def is_birthday(person: Person, day: date) -> bool:
    if not person.birth_month or not person.birth_day:
        return False
    return occurs_on(person.birth_month, person.birth_day, day.year) == day


def anniversary_years(person: Person, day: date) -> int | None:
    """Completed years if `day` is this person's work anniversary, else None.

    A start date less than a year ago has no anniversary yet, and neither does
    one in the future.
    """
    start = person.start_date
    if not start:
        return None
    years = day.year - start.year
    if years < 1:
        return None
    if occurs_on(start.month, start.day, day.year) != day:
        return None
    return years


def dates_covered(cal: Calendar, today: date) -> list[date]:
    """The days a pass on `today` celebrates: today and the days off after it.

    Empty when today is not a working day, because a day off is always
    covered by the working day before it.
    """
    if not cal.is_working_day(today):
        return []
    return [today, *cal.days_off_after(today)]


def _sort_key(h: Honoree) -> tuple:
    return ((h.name or "").lower(), h.user_id)


def due(
    people,
    cal: Calendar,
    today: date,
    birthdays: bool = True,
    anniversaries: bool = True,
) -> list[Celebration]:
    """What a pass on `today` posts: one Celebration per kind per day.

    The caller passes only people who may be celebrated (active, not opted
    out); this decides only whose day it is.
    """
    out: list[Celebration] = []
    people = list(people)
    for day in dates_covered(cal, today):
        if birthdays:
            born = [Honoree(p.user_id, p.name) for p in people if is_birthday(p, day)]
            if born:
                out.append(Celebration(BIRTHDAY, day, tuple(sorted(born, key=_sort_key))))
        if anniversaries:
            joined = []
            for p in people:
                years = anniversary_years(p, day)
                if years:
                    joined.append(Honoree(p.user_id, p.name, years))
            if joined:
                out.append(Celebration(ANNIVERSARY, day, tuple(sorted(joined, key=_sort_key))))
    return out


def upcoming(
    people,
    cal: Calendar,
    today: date,
    days: int = 30,
    birthdays: bool = True,
    anniversaries: bool = True,
) -> list[tuple[date, Celebration]]:
    """Every post the next `days` days will make, as (posted_on, celebration)."""
    people = list(people)
    out: list[tuple[date, Celebration]] = []
    for offset in range(days + 1):
        posted_on = today + timedelta(days=offset)
        for c in due(people, cal, posted_on, birthdays, anniversaries):
            out.append((posted_on, c))
    return out
