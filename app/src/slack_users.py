"""Helpers for narrowing Slack user lists down to real, active people.

Bots, apps, Slackbot and deactivated accounts cannot take part in a standup:
`conversations.open` against them fails, which surfaces to the team as a
"Failed to send standup DMs to N/M members" error on every scheduled run.
Every path that turns Slack ids into standup participants should filter
through here first.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SLACKBOT_ID = "USLACKBOT"


def is_human(user: dict[str, Any] | None) -> bool:
    """Return True when a `users.info` / `users.list` object is a real, active person."""
    if not user:
        return False
    if user.get("id") == SLACKBOT_ID:
        return False
    return not (user.get("deleted") or user.get("is_bot"))


def filter_human_ids(client: Any, user_ids: Iterable[str]) -> set[str]:
    """Return the subset of `user_ids` belonging to real, active people.

    Classifies in bulk via a paginated `users.list` so a large channel costs a
    handful of API calls rather than one `users.info` per member. Ids missing
    from `users.list` (Slack Connect guests, for example) fall back to an
    individual `users.info` lookup.

    On an unrecoverable API error the input is returned unchanged: dropping
    people from a standup is worse than the bot noise this filter removes.
    """
    wanted = {uid for uid in user_ids if uid}
    if not wanted:
        return set()

    humans: set[str] = set()
    classified: set[str] = set()
    try:
        cursor = None
        while True:
            result = client.users_list(limit=200, cursor=cursor or "")
            for user in result.get("members", []):
                uid = user.get("id")
                if uid not in wanted:
                    continue
                classified.add(uid)
                if is_human(user):
                    humans.add(uid)
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as exc:
        logger.warning("users.list failed while filtering bots, keeping all %d ids: %s", len(wanted), exc)
        return wanted

    for uid in wanted - classified:
        try:
            if is_human(client.users_info(user=uid).get("user", {})):
                humans.add(uid)
        except Exception as exc:
            # Unknown rather than proven-bot, so keep them in the standup.
            logger.warning("users.info failed for %s, keeping as participant: %s", uid, exc)
            humans.add(uid)

    dropped = len(wanted) - len(humans)
    if dropped:
        logger.info("Filtered %d bot/deactivated account(s) out of %d Slack members", dropped, len(wanted))
    return humans
