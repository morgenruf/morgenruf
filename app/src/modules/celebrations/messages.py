"""What Celebrations says, in the channel and in a DM.

Warm and short. Names are mentions. No pronouns anywhere, because the profile
does not store them. The text is fixed in this first version; the design
(section 7) is the source for every wording here.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.core.profile import MONTHS
from src.core.workspace_calendar import Calendar
from src.modules.celebrations.rules import BIRTHDAY, Celebration, Honoree

ADD_DATES_ACTION = "celebrations:add_dates"
SKIP_ACTION = "celebrations:skip"

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def first_name(*candidates: str | None) -> str:
    """The first word of the first non-empty name, safe to put in mrkdwn."""
    for value in candidates:
        words = (value or "").strip().split()
        if words:
            return _escape(words[0])
    return ""


def _mention(h: Honoree) -> str:
    return f"<@{h.user_id}>"


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _number(n: int) -> str:
    return _NUMBER_WORDS[n] if 0 <= n < len(_NUMBER_WORDS) else str(n)


def day_label(day: date) -> str:
    """The day as "25 December"."""
    return f"{day.day} {MONTHS[day.month - 1]}"


def lead_in(day: date, today: date, cal: Calendar) -> str:
    """How the post opens: "Today is", "Tomorrow is", "On Sunday it's", "On 25 December it's".

    A weekend day, or a holiday straight after a weekend (a long weekend's
    Monday), is named by weekday: that is how people talk about the days just
    ahead. Any other holiday is named by date, so "On 25 December" reads as
    the holiday it is. Anything a week or more away is always a date, since a
    weekday name would be ambiguous.
    """
    gap = (day - today).days
    if gap <= 0:
        return "Today is"
    if gap == 1:
        return "Tomorrow is"
    by_weekday = cal.is_weekend(day) or (cal.is_weekend(day - timedelta(days=1)) and cal.is_holiday(day))
    if gap < 7 and by_weekday:
        return f"On {_WEEKDAYS[day.weekday()]} it's"
    return f"On {day_label(day)} it's"


def early_reason(day: date, cal: Calendar) -> str:
    """Why the post is early. A listed holiday is a day off; anything else is the weekend."""
    if cal.is_holiday(day):
        return "It's a day off, so let's celebrate early."
    return "Off for the weekend, so let's celebrate early."


def _years_label(years: int) -> str:
    return "1 year" if years == 1 else f"{years} years"


def birthday_text(c: Celebration, today: date, cal: Calendar) -> str:
    people = list(c.people)
    lead = lead_in(c.day, today, cal)
    early = c.day != today
    if len(people) == 1:
        head = f"🎂 {lead} {_mention(people[0])}'s birthday!"
    elif len(people) == 2:
        head = f"🎂 {lead} a birthday double: {_mention(people[0])} and {_mention(people[1])}!"
    else:
        head = f"🎂 {lead} the birthday of {_join([_mention(p) for p in people])}!"

    if early:
        tail = early_reason(c.day, cal)
        if len(people) >= 3:
            tail += " Happy birthday to all of you."
        return f"{head}\n{tail} 🎈"
    if len(people) == 1:
        name = people[0].name
        return f"{head}\nWishing you a lovely day, {name}. 💛" if name else f"{head}\nWishing you a lovely day. 💛"
    if len(people) == 2:
        return f"{head}\nWishing you both a lovely day. 💛"
    return f"{head}\nHappy birthday to all of you. 💛"


def anniversary_text(c: Celebration, today: date, cal: Calendar) -> str:
    people = list(c.people)
    lead = lead_in(c.day, today, cal)
    early = c.day != today

    if len(people) == 1:
        person = people[0]
        years = person.years or 1
        if years == 1:
            head = f"🎉 {lead} {_mention(person)}'s first work anniversary! 🥳"
        else:
            head = f"🎉 {lead} {_mention(person)}'s {years}-year work anniversary!"
        if early:
            return f"{head}\n{early_reason(c.day, cal)} 🎈"
        thanks = f", {person.name}" if person.name else ""
        if years == 1:
            return f"{head}\nOne year already. Thanks for everything{thanks}."
        return f"{head}\nThanks for {_number(years)} great years{thanks}. 🙌"

    listed = [f"{_mention(p)} ({_years_label(p.years or 1)})" for p in people]
    if len(people) == 2:
        head = f"🎉 {lead} a work anniversary double: {listed[0]} and {listed[1]}!"
    else:
        head = f"🎉 {lead} the work anniversary of {_join(listed)}!"
    if early:
        return f"{head}\n{early_reason(c.day, cal)} 🎈"
    if len(people) == 2:
        return f"{head}\nThanks to you both for everything. 🙌"
    return f"{head}\nThanks to all of you for everything. 🙌"


def celebration_text(c: Celebration, today: date, cal: Calendar) -> str:
    return birthday_text(c, today, cal) if c.kind == BIRTHDAY else anniversary_text(c, today, cal)


# ── The DM asking for dates ─────────────────────────────────────────────────


def nudge_text(name: str, channel_id: str) -> str:
    greeting = f"👋 Hi {name}!" if name else "👋 Hi!"
    return (
        f"{greeting} Your team celebrates birthdays and work anniversaries in <#{channel_id}>.\n\n"
        "Add yours so nobody misses it. For your birthday only the day and month are kept."
    )


def nudge_blocks(name: str, channel_id: str) -> list[dict]:
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": nudge_text(name, channel_id)}},
        {
            "type": "actions",
            "block_id": "celebrations:nudge",
            "elements": [
                {
                    "type": "button",
                    "action_id": ADD_DATES_ACTION,
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Add my dates", "emoji": True},
                    "value": "add",
                },
                {
                    "type": "button",
                    "action_id": SKIP_ACTION,
                    "text": {"type": "plain_text", "text": "Don't celebrate me", "emoji": True},
                    "value": "skip",
                },
            ],
        },
    ]


SKIPPED_TEXT = "Got it. You will not be celebrated publicly. Change your mind any time with `/morgenruf profile`."
