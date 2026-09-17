"""Deciding which token the bot posts.

A custom emoji only renders in Slack once someone has imported it. Defaulting
to :morgenruf: meant a workspace that had not done that posted the literal
text in every kudos message, and only found out by seeing it.

So the default is a plain emoji, and this upgrades a workspace to the branded
one after confirming the emoji actually exists there. The check needs the
emoji:read scope; without it the workspace simply stays on the plain emoji,
which is the same outcome as before and never worse.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BRAND_TOKEN = ":morgenruf:"
BRAND_EMOJI_NAME = "morgenruf"


def workspace_has_brand_emoji(client) -> bool | None:
    """True, False, or None when Slack could not tell us.

    None matters: a missing scope or a rate limit must not be read as "the
    emoji is gone" and downgrade a workspace that is happily using it.
    """
    try:
        resp = client.emoji_list()
    except Exception as exc:
        logger.info("kudos: could not read the emoji list: %s", exc)
        return None
    try:
        names = resp.get("emoji") or {}
    except AttributeError:
        return None
    if not isinstance(names, dict):
        return None
    return BRAND_EMOJI_NAME in names


def resolve(current: str, token_auto: bool, has_brand: bool | None) -> str | None:
    """The token to store, or None to leave it alone.

    Only ever moves a workspace that has not chosen for itself, and only in
    the direction the evidence supports.
    """
    if not token_auto or has_brand is None:
        return None
    if has_brand and current != BRAND_TOKEN:
        return BRAND_TOKEN
    if not has_brand and current == BRAND_TOKEN:
        # The emoji was deleted, or we set it before it existed. Either way the
        # workspace is posting literal text right now.
        return "\N{MAPLE LEAF}"
    return None
