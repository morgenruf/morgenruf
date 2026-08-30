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

# Upper bound on users.list pagination. Slack ends a walk with an empty
# cursor; this stops a malformed or mocked response from looping forever.
MAX_USER_PAGES = 50


def is_human(user: dict[str, Any] | None) -> bool:
    """Return True when a `users.info` / `users.list` object is a real, active person."""
    if not user:
        return False
    if user.get("id") == SLACKBOT_ID:
        return False
    return not (user.get("deleted") or user.get("is_bot"))


def fetch_human_users(client: Any, user_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Return `{user_id: Slack user object}` for the real, active people in `user_ids`.

    Classifies in bulk via a paginated `users.list` so a large channel costs a
    handful of API calls rather than one `users.info` per member. Ids missing
    from `users.list` (Slack Connect guests, for example) fall back to an
    individual `users.info` lookup.

    The fetched user objects are handed back rather than discarded, so a caller
    that needs a profile (name, email, timezone) gets one without a second
    round trip. Ids kept only because Slack could not be reached map to an
    empty dict.

    On an unrecoverable API error the input is returned unchanged: dropping
    people from a standup is worse than the bot noise this filter removes.
    """
    wanted = {uid for uid in user_ids if uid}
    if not wanted:
        return {}

    humans: dict[str, dict[str, Any]] = {}
    classified: set[str] = set()
    try:
        cursor = None
        for _page in range(MAX_USER_PAGES):
            result = client.users_list(limit=200, cursor=cursor or "")
            members = result.get("members", [])
            if not isinstance(members, list):
                break
            for user in members:
                if not isinstance(user, dict):
                    continue
                uid = user.get("id")
                if uid not in wanted:
                    continue
                classified.add(uid)
                if is_human(user):
                    humans[uid] = user
            cursor = (result.get("response_metadata") or {}).get("next_cursor")
            # Slack signals the end with an empty string. Anything that is not a
            # non-empty string ends the walk too, so a malformed response cannot
            # spin this loop forever.
            if not isinstance(cursor, str) or not cursor:
                break
        else:
            logger.warning("users.list did not finish within %d pages, using what was read", MAX_USER_PAGES)
    except Exception as exc:
        logger.warning("users.list failed while filtering bots, keeping all %d ids: %s", len(wanted), exc)
        return {uid: {} for uid in wanted}

    for uid in wanted - classified:
        try:
            user = client.users_info(user=uid).get("user", {})
            if is_human(user):
                humans[uid] = user
        except Exception as exc:
            # Unknown rather than proven-bot, so keep them in the standup.
            logger.warning("users.info failed for %s, keeping as participant: %s", uid, exc)
            humans[uid] = {}

    dropped = len(wanted) - len(humans)
    if dropped:
        logger.info("Filtered %d bot/deactivated account(s) out of %d Slack members", dropped, len(wanted))
    return humans


def filter_human_ids(client: Any, user_ids: Iterable[str]) -> set[str]:
    """Return the subset of `user_ids` belonging to real, active people.

    Thin wrapper over `fetch_human_users` for callers that only need the ids.
    """
    return set(fetch_human_users(client, user_ids))


def member_profile(user: dict[str, Any] | None) -> dict[str, str | None]:
    """Pull the fields `db.upsert_member` stores out of a Slack user object.

    Anything the object does not carry comes back as None so an upsert leaves
    the stored value alone instead of blanking it.
    """
    user = user or {}
    profile = user.get("profile") or {}
    return {
        "real_name": profile.get("real_name") or profile.get("display_name") or user.get("real_name") or None,
        "email": profile.get("email") or None,
        "tz": user.get("tz") or None,
    }


def fetch_workspace_humans(client: Any) -> set[str] | None:
    """Return the ids of every real, active person in the workspace.

    Returns None when the walk could not be completed. That distinction matters
    to the caller: an empty set means "this workspace genuinely has nobody",
    while None means "we do not know", and deactivating members on a "do not
    know" would empty every standup in the workspace.
    """
    humans: set[str] = set()
    cursor = None
    try:
        for _page in range(MAX_USER_PAGES):
            result = client.users_list(limit=200, cursor=cursor or "")
            members = result.get("members", [])
            if not isinstance(members, list):
                return None
            for user in members:
                if isinstance(user, dict) and is_human(user):
                    uid = user.get("id")
                    if uid:
                        humans.add(uid)
            cursor = (result.get("response_metadata") or {}).get("next_cursor")
            if not isinstance(cursor, str) or not cursor:
                return humans
        logger.warning("users.list did not finish within %d pages, not reconciling", MAX_USER_PAGES)
        return None
    except Exception as exc:
        # slack_sdk's str() is just "The request to the Slack API failed", which
        # is not diagnosable. The response carries the actual code: ratelimited,
        # missing_scope, invalid_auth, account_inactive.
        code = getattr(getattr(exc, "response", None), "get", lambda _k, _d=None: None)("error")
        logger.warning("Could not list workspace users: %s", code or exc)
        return None
