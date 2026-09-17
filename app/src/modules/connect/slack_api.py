"""Connect's Slack calls, kept in one place.

Deliberately not built on PlatformAdapter: that interface has no group DM
concept and Google Chat has no MPIM equivalent, so pairing cannot be expressed
through it without redesigning it first.

Everything here has to survive rate limiting. A 200 person channel is 100
group DMs in one burst, and conversations.open is Tier 3 at roughly 50 a
minute. Getting this wrong means half a workspace silently never hears from
the bot.
"""

from __future__ import annotations

import logging
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)

# Slack asks for a pause between writes. A small floor keeps us under the
# per-channel posting limit without making a big round take all morning.
_MIN_INTERVAL_SECONDS = 1.1
_MAX_RETRIES = 3

# Errors that will never succeed on retry, so the caller should move on.
_PERMANENT = {
    "channel_not_found",
    "user_not_found",
    "users_not_found",
    "invalid_arguments",
    "method_not_supported_for_channel_type",
    "cannot_dm_bot",
    "user_disabled",
    "account_inactive",
    "token_revoked",
    "invalid_auth",
    "not_authed",
    "missing_scope",
}


class PermanentSlackError(Exception):
    """Raised when retrying cannot help, so the caller stops trying."""


def _call(fn, **kwargs):
    """One Slack call with backoff on rate limiting.

    Honours Retry-After rather than guessing, because guessing low gets the
    app rate limited harder.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(**kwargs)
        except SlackApiError as exc:
            err = (exc.response or {}).get("error", "")
            if err == "ratelimited":
                wait = int(exc.response.headers.get("Retry-After", 2))
                logger.info("rate limited, waiting %ss", wait)
                time.sleep(wait)
                continue
            if err in _PERMANENT:
                raise PermanentSlackError(err) from exc
            if attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise PermanentSlackError("retries exhausted")


def open_group_dm(client: WebClient, user_ids: list[str]) -> str:
    """Open the multi-person DM the pair or trio will talk in.

    Returns the channel id. Slack returns the same channel for the same set of
    people, so re-running a delivery does not create a second conversation.
    """
    resp = _call(client.conversations_open, users=",".join(user_ids))
    return resp["channel"]["id"]


def post(client: WebClient, channel: str, text: str, blocks=None) -> None:
    kwargs = {"channel": channel, "text": text}
    if blocks:
        kwargs["blocks"] = blocks
    _call(client.chat_postMessage, **kwargs)


def channel_member_ids(client: WebClient, channel_id: str) -> list[str]:
    """Everyone in the channel the programme draws from, following pagination."""
    members: list[str] = []
    cursor = None
    while True:
        resp = _call(client.conversations_members, channel=channel_id, limit=200, cursor=cursor)
        members.extend(resp.get("members", []))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            return members


def has_replies(client: WebClient, channel_id: str, since_ts: float | None = None) -> bool:
    """Whether anyone has said anything in the group DM.

    Used to decide whether a nudge is warranted. A pair already talking must
    not be nudged; that is what makes a bot annoying.
    """
    try:
        resp = _call(client.conversations_history, channel=channel_id, limit=20)
    except (SlackApiError, PermanentSlackError):
        # Unreadable history means we cannot tell. Staying quiet is the safer
        # failure: a missed nudge costs less than nagging a conversation.
        return True
    for msg in resp.get("messages", []):
        if msg.get("bot_id") or msg.get("subtype") == "bot_message":
            continue
        if since_ts and float(msg.get("ts", 0)) < since_ts:
            continue
        return True
    return False


def throttle() -> None:
    """Pause between writes so a large round stays inside the posting limit."""
    time.sleep(_MIN_INTERVAL_SECONDS)
