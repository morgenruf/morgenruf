"""Closing polls when their time is up.

A workspace with an open poll gets a sweep every minute; one with none gets
no job at all, so the scheduler is not woken for nothing. A new poll with a
closing time is picked up by the next module job sync, a couple of minutes at
most.
"""

from __future__ import annotations

import logging

from apscheduler.triggers.interval import IntervalTrigger

from src.core.scheduler import JobSpec

logger = logging.getLogger(__name__)


def plan_jobs(ctx: dict) -> list[JobSpec]:
    import src.modules.polls.db as pdb  # noqa: PLC0415

    team_id = ctx["team_id"]
    # Raises on a failed read: module job sync then keeps the live job, where
    # an empty plan would delete it.
    if pdb.open_poll_count(team_id) <= 0:
        return []
    return [
        JobSpec(
            key="close",
            trigger=IntervalTrigger(minutes=1),
            func=close_due_polls,
            # The bot token is read when the job runs, because tokens rotate.
            args=(team_id,),
        )
    ]


def bot_client(team_id: str):
    """A WebClient on the workspace's current bot token, or None."""
    from slack_sdk import WebClient  # noqa: PLC0415

    try:
        from src.core.scheduler import _fresh_bot_token  # noqa: PLC0415

        token = _fresh_bot_token(team_id, "")
    except Exception:
        token = ""
    return WebClient(token=token) if token else None


def close_due_polls(team_id: str) -> int:
    """Close every poll past its closing time. Returns how many this run closed.

    Safe to run twice or on two pods at once: close_poll only succeeds for
    the run that actually closed the poll, and only that run redraws it.
    """
    import src.modules.polls.db as pdb  # noqa: PLC0415
    from src.modules.polls.handlers import finish_poll  # noqa: PLC0415

    due = pdb.due_polls(team_id)
    if not due:
        return 0
    client = bot_client(team_id)
    closed = 0
    for poll in due:
        try:
            if finish_poll(client, poll["id"]):
                closed += 1
        except Exception:
            logger.exception("polls: could not close poll %s in %s", poll["id"], team_id)
    if closed:
        logger.info("polls: closed %d poll(s) in %s", closed, team_id)
    return closed
