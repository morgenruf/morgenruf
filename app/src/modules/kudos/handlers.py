"""Kudos Slack handlers: the /kudos command and the `kudos @user ...` DM.

The command is a Bolt listener. The DM is not: core owns the only message
listener that runs (Bolt stops at the first match), so the DM form arrives
through claim_dm_command. Both end in give_kudos, so the checks, the save and
the card are the same whichever way someone gives one.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _giver_timezone(team_id: str, user_id: str) -> str:
    """The giver's timezone, so their day resets at their own midnight."""
    try:
        import src.core.db as core_db  # noqa: PLC0415

        for row in core_db.get_all_members(team_id):
            if row.get("user_id") == user_id:
                return row.get("tz") or "UTC"
    except Exception:
        pass
    return "UTC"


def _check_allowance(team_id: str, from_user: str):
    """Returns (state, refusal_message). refusal_message is None when allowed.

    A database problem must not block recognition, so an unreadable allowance
    lets the kudos through rather than refusing it.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    import src.modules.kudos.db as kdb  # noqa: PLC0415

    try:
        state = kdb.allowance_state(team_id, from_user, _giver_timezone(team_id, from_user), datetime.now(timezone.utc))
    except Exception as exc:
        logger.warning("allowance lookup failed for %s: %s", from_user, exc)
        return {"emoji": kdb.DEFAULT_EMOJI, "remaining": 1, "allowance": 0}, None

    if state["allowance"] == 0:
        return state, "Kudos are switched off for this workspace. An admin can turn them on in the dashboard."
    if not state["can_give"]:
        return state, (
            f"That was all {state['allowance']} of your {state['emoji']} for today. "
            "You get a fresh set at midnight where you are."
        )
    return state, None


def _remaining_note(state) -> str:
    """A quiet reminder of what is left, so the budget is visible."""
    left = max(0, state.get("remaining", 0) - 1)
    emoji = state.get("emoji", "")
    if state.get("allowance", 0) <= 0:
        return ""
    if left == 0:
        return f"That was your last kudos {emoji} for today. A fresh set arrives at midnight."
    return f"{left} kudos {emoji} left today."


def _context(*lines: str) -> list[dict]:
    """A context block per line, skipping the ones that came back empty."""
    return [{"type": "context", "elements": [{"type": "mrkdwn", "text": line}]} for line in lines if line]


def _quote(message: str) -> str:
    """Every line prefixed, so a multi-line reason stays inside the quote."""
    lines = (message or "").strip().splitlines()
    return "\n".join(f"> {line}" if line.strip() else ">" for line in lines) or "> "


def kudos_card(from_user: str, to_user: str, message: str, emoji: str | None = None) -> tuple[str, list[dict]]:
    """The card that lands in the channel.

    The person being recognised is named first and in bold, because they are
    the point of the message. The reason is quoted so it reads as their words
    being passed on, and the last line tells everyone else how to join in.
    There is always a recipient: a kudos nobody could be found for is never
    saved or shown.
    """
    if emoji is None:
        from src.modules.kudos.db import DEFAULT_EMOJI  # noqa: PLC0415

        emoji = DEFAULT_EMOJI
    headline = f"{emoji} *<@{to_user}>* got kudos from <@{from_user}>"
    text = f"{emoji} <@{from_user}> gave <@{to_user}> kudos"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": headline}},
        {"type": "section", "text": {"type": "mrkdwn", "text": _quote(message)}},
        *_context("Pass one on with `kudos @someone` and a reason, or `/kudos`"),
    ]
    return text, blocks


USAGE = (
    "I could not tell who that was for. Start with an @mention and say why, "
    "for example: `/kudos @sam for catching the migration bug`"
)

# `<@U123>` or `<@U123|name>`, then the reason. Slack sends a mention in a
# message event as `<@U123>`, and in an escaped slash command as `<@U123|name>`.
_MENTION = re.compile(r"^<@([UW][A-Z0-9]+)(?:\|[^>]*)?>[\s,:]*(.*)$", re.DOTALL)
_DM_KUDOS = re.compile(r"^kudos\s+(?=<@|@)(.*)$", re.IGNORECASE | re.DOTALL)


def _resolve_plain_name(team_id: str, text: str) -> tuple[str, str] | None:
    """`@Anmol Nagpal for the review` against the roster: (user_id, reason).

    A slash command declared without should_escape arrives with the mention as
    plain text. The manifest now asks for escaping, but a hosted app config is
    changed by hand, so this keeps kudos working until it is. Display and real
    names are both tried, the longest name that fits wins (so "Sam Lee" beats
    "Sam"), and it resolves only when that names exactly one person.
    """
    if not text.startswith("@"):
        return None
    rest = text[1:]
    try:
        import src.core.db as core_db  # noqa: PLC0415

        members = core_db.get_all_members(team_id)
    except Exception as exc:
        logger.warning("kudos: could not read the roster for %s: %s", team_id, exc)
        return None

    best_len = 0
    matches: set[str] = set()
    for member in members:
        if member.get("active") is False or not member.get("user_id"):
            continue
        for field in ("display_name", "real_name"):
            name = (member.get(field) or "").strip()
            if not name or rest[: len(name)].casefold() != name.casefold():
                continue
            after = rest[len(name) : len(name) + 1]
            if after and not (after.isspace() or after in ",:"):
                continue
            if len(name) > best_len:
                best_len, matches = len(name), {member["user_id"]}
            elif len(name) == best_len:
                matches.add(member["user_id"])
    if len(matches) != 1:
        return None
    return matches.pop(), rest[best_len:].lstrip(" \t\n,:")


def parse_recipient(team_id: str, text: str) -> tuple[str, str] | None:
    """Who the kudos is for and why, or None when that cannot be told."""
    text = (text or "").strip()
    match = _MENTION.match(text)
    if match:
        found: tuple[str, str] | None = (match.group(1), match.group(2))
    else:
        found = _resolve_plain_name(team_id, text)
    if not found:
        return None
    to_user, reason = found[0], found[1].strip()
    if not reason:
        return None
    return to_user, reason


def recipient_card(from_user: str, message: str, emoji: str) -> tuple[str, list[dict]]:
    """The DM the person being recognised gets.

    Written to them rather than about them, with the reason quoted as the
    giver wrote it. The giver's remaining allowance is theirs, not shown here.
    """
    text = f"{emoji} <@{from_user}> sent you kudos"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{emoji} *<@{from_user}>* sent you kudos"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": _quote(message)}},
        *_context("Pass one on with `kudos @someone` and a reason, or `/kudos`"),
    ]
    return text, blocks


def kudos_channel(team_id: str) -> str:
    """Where the card is shared: the kudos channel, else the legacy workspace
    channel, else nowhere ("").

    A lookup that fails means no channel post, never a lost kudos.
    """
    try:
        import src.modules.kudos.db as kdb  # noqa: PLC0415

        channel = (kdb.get_config(team_id) or {}).get("channel_id") or ""
    except Exception as exc:
        logger.warning("kudos: could not read the kudos channel for %s: %s", team_id, exc)
        channel = ""
    if channel:
        return channel
    try:
        import src.core.db as core_db  # noqa: PLC0415

        return (core_db.get_workspace_config(team_id) or {}).get("channel_id") or ""
    except Exception as exc:
        logger.warning("kudos: could not read the workspace channel for %s: %s", team_id, exc)
        return ""


def give_kudos(client, team_id: str, from_user: str, to_user: str, reason: str, reply_to: str, source: str) -> bool:
    """Check, save and announce one kudos. Returns True when it was saved.

    Every reply to the giver goes to reply_to (their DM). Once the row is
    saved the recipient gets a DM, and the card is shared in the kudos channel
    when there is one. Nothing is sent to anyone for a kudos that was not
    saved.
    """

    def tell(text: str, blocks: list[dict] | None = None) -> None:
        if blocks:
            client.chat_postMessage(channel=reply_to, text=text, blocks=blocks)
        else:
            client.chat_postMessage(channel=reply_to, text=text)

    if from_user == to_user:
        tell("Kudos are for other people. Pick a teammate.")
        return False

    state, refusal = _check_allowance(team_id, from_user)
    if refusal:
        tell(refusal)
        return False

    emoji = state["emoji"]
    post_channel = kudos_channel(team_id)
    try:
        import src.modules.kudos.db as db  # noqa: PLC0415

        db.save_kudos(team_id, from_user, to_user, reason, post_channel, emoji)
    except Exception as exc:
        logger.warning("kudos: could not save a kudos in %s: %s", team_id, exc)
        tell("That kudos did not go through. Try it once more.")
        return False

    from src.core.analytics import capture  # noqa: PLC0415

    capture("kudos_given", team_id, source=source)

    posted = False
    if post_channel:
        card_text, card_blocks = kudos_card(from_user, to_user, reason, emoji)
        try:
            client.chat_postMessage(channel=post_channel, text=card_text, blocks=card_blocks)
            posted = True
        except Exception as exc:
            logger.warning("kudos: saved but could not post in %s: %s", post_channel, exc)

    delivered = False
    dm_text, dm_blocks = recipient_card(from_user, reason, emoji)
    try:
        client.chat_postMessage(channel=to_user, text=dm_text, blocks=dm_blocks)
        delivered = True
    except Exception as exc:
        logger.warning("kudos: saved but could not DM %s: %s", to_user, exc)

    if delivered and posted:
        sent = f"Sent to <@{to_user}> and posted in <#{post_channel}>."
    elif delivered:
        sent = f"Sent to <@{to_user}>."
    elif posted:
        sent = f"Posted in <#{post_channel}>. I could not send <@{to_user}> a DM."
    else:
        sent = f"Saved. I could not reach <@{to_user}>, but it shows on the Kudos page in the dashboard."
    missed = (
        f"I could not post in <#{post_channel}>. Invite @Morgenruf to it so the next one shows up there."
        if post_channel and not posted
        else ""
    )
    try:
        tell(
            sent,
            [{"type": "section", "text": {"type": "mrkdwn", "text": sent}}, *_context(missed, _remaining_note(state))],
        )
    except Exception:
        logger.exception("kudos: could not reply to %s", from_user)
    return True


def claim_dm_command(ctx) -> bool:
    """`kudos @someone reason` sent to the bot by DM. True when handled.

    Only messages that start with `kudos` and a mention are claimed, so a
    standup answer like "kudos to the team" still reaches standup.
    """
    event = ctx.event
    if event.get("channel_type") != "im" or event.get("subtype") or event.get("bot_id"):
        return False
    match = _DM_KUDOS.match(ctx.text or "")
    if not match:
        return False
    reply_to = ctx.channel_id or ctx.user_id
    found = parse_recipient(ctx.team_id, match.group(1))
    if not found:
        ctx.client.chat_postMessage(channel=reply_to, text=USAGE.replace("/kudos @", "kudos @"))
        return True
    to_user, reason = found
    give_kudos(ctx.client, ctx.team_id, ctx.user_id, to_user, reason, reply_to, source="message")
    return True


def register_handlers(app) -> None:
    """Register the kudos slash commands. The DM form is claim_dm_command."""

    @app.command("/kudos")
    @app.command("/morgenruf-kudos")
    def handle_kudos_command(ack, body, client):  # noqa: ANN001
        """Slash command to give kudos to a teammate."""
        ack()
        user_id: str = body["user_id"]
        team_id: str = body["team_id"]
        text: str = (body.get("text") or "").strip()

        if not text:
            client.chat_postMessage(
                channel=user_id,
                text="Name someone and say why. For example: `/kudos @sam caught the migration bug before it shipped`",
            )
            return

        found = parse_recipient(team_id, text)
        if not found:
            client.chat_postMessage(channel=user_id, text=USAGE)
            return
        to_user, reason = found
        give_kudos(client, team_id, user_id, to_user, reason, user_id, source="command")
