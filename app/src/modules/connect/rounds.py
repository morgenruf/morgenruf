"""When a round is due.

APScheduler's cron `week` field is an ISO week number, which drifts at year
boundaries and cannot express "every two weeks from this programme's start".
So the job fires weekly on the chosen weekday and this decides whether today
is actually a round day.

Deciding here rather than in the trigger also means a missed week starts the
round late instead of losing it, which matters when the bot was down.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def is_round_due(
    interval_weeks: int,
    last_round: date | None,
    today: date,
    pinned: date | None = None,
) -> bool:
    """Whether a round should start today.

    A programme that has never run is due immediately. Otherwise a round is
    due once at least `interval_weeks` have passed, using >= rather than == so
    an overdue programme catches up instead of waiting for an exact multiple.

    `pinned` is an explicit date for the next round, which overrides the
    cadence once. It is how an admin moves one round without changing the
    rhythm: a date in the future holds the round back even if the cadence says
    it is due, and a date reached or passed releases it. It is cleared once the
    round runs, so the cadence takes over again from there.
    """
    if pinned is not None:
        if last_round is not None and last_round >= pinned:
            # The pinned round already happened; fall through to the cadence.
            pass
        else:
            return today >= pinned
    if last_round is None:
        return True
    if last_round >= today:
        return False
    return (today - last_round).days >= max(1, int(interval_weeks)) * 7


def next_round_date(interval_weeks: int, last_round: date | None) -> date | None:
    """When the following round falls, or None if the programme has not run."""
    if last_round is None:
        return None
    return last_round + timedelta(days=max(1, int(interval_weeks)) * 7)


def match_status(met, delivered_at) -> str:
    """What became of one pairing.

    "Not met" hides three different problems: they said no, they never
    answered, or the invite never reached them. Only the first is about the
    people; the last is a bug on our side.
    """
    if met is True:
        return "met"
    if met is False:
        return "missed"
    if delivered_at is None:
        return "undelivered"
    return "no_reply"


def upcoming_round_date(program: dict, today: date) -> date:
    """When the next round falls for a programme, as the job will decide it.

    The job only fires on the programme's weekday and then asks is_round_due,
    so this walks those weekdays with the same question. Counting from the last
    round alone named dates the job never fires on, such as a Thursday for a
    Monday programme that was last run by hand.

    A programme that has never run is due on its next scheduled weekday, not
    today: telling someone who joins on a Thursday that their Monday coffee
    chat is about to happen is simply wrong.
    """
    last = _as_date(program.get("last_scheduled_round", program.get("last_round")))
    pinned = _as_date(program.get("next_round_date"))
    try:
        weeks = max(1, int(program.get("interval_weeks") or 1))
    except (TypeError, ValueError):
        weeks = 1

    day = _next_weekday(today, program.get("day_of_week"))
    # Bounded so a pinned date years out cannot spin; ten years of weekdays.
    for _ in range(520):
        if is_round_due(weeks, last, day, pinned):
            return day
        day += timedelta(days=7)
    return day


def _as_date(value: object) -> date | None:
    """Rounds come back as dates from some queries and timestamps from others."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _next_weekday(today: date, day_of_week: object) -> date:
    """Next occurrence of a weekday, today included. connect stores 0 = Monday,
    which is what date.weekday() uses."""
    try:
        wanted = int(day_of_week)
    except (TypeError, ValueError):
        return today
    if not 0 <= wanted <= 6:
        return today
    return today + timedelta(days=(wanted - today.weekday()) % 7)


def cadence_phrase(interval_weeks: object) -> str:
    """ "every week", "every 2 weeks" — the words a welcome message needs."""
    try:
        weeks = max(1, int(interval_weeks or 1))
    except (TypeError, ValueError):
        weeks = 1
    return "every week" if weeks == 1 else f"every {weeks} weeks"
