"""When a round is due.

APScheduler's cron `week` field is an ISO week number, which drifts at year
boundaries and cannot express "every two weeks from this programme's start".
So the job fires weekly on the chosen weekday and this decides whether today
is actually a round day.

Deciding here rather than in the trigger also means a missed week starts the
round late instead of losing it, which matters when the bot was down.
"""

from __future__ import annotations

from datetime import date, timedelta


def is_round_due(interval_weeks: int, last_round: date | None, today: date) -> bool:
    """Whether a round should start today.

    A programme that has never run is due immediately. Otherwise a round is
    due once at least `interval_weeks` have passed, using >= rather than == so
    an overdue programme catches up instead of waiting for an exact multiple.
    """
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
