"""Polls in Slack: `/morgenruf poll`, the form, voting and closing.

The bot has no chat:write.public and cannot join a channel on its own, so a
poll can only be posted where it is already a member. That is checked before
anything is stored: a poll for a channel the bot is not in is never created,
and the person is told how to invite it.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.modules.polls import blocks as pblocks
from src.modules.polls.parse import options_error, options_from_lines, parse_quick, question_error, unslack

logger = logging.getLogger(__name__)

MODULE_NAME = "polls"

USAGE = (
    'Start a poll with `/morgenruf poll "Question" "Option 1" "Option 2"` (2 to 10 options, each in quotes), '
    "or type `/morgenruf poll` on its own to open the form."
)
CLOSED = "This poll is closed."
NO_SALT = "This poll can't take votes any more."
TURNED_OFF = "Polls are turned off in this workspace."
NOT_A_CHANNEL = "Polls go in a channel. Run `/morgenruf poll` in a channel Morgenruf is in, or pick one in the form."
COULD_NOT_CHECK = "I couldn't check that channel just now. Please try again in a minute."
COULD_NOT_SAVE = "I couldn't save the poll just now. Please try again in a minute."

_VOTE = re.compile(r"^polls:vote:(\d+):(\d+)$")
_CLOSE = re.compile(r"^polls:close:(\d+)$")


def invite_text(channel_id: str) -> str:
    return (
        f"I can't post in <#{channel_id}> yet. Type `/invite @Morgenruf` there "
        "(or pick *Add agents and apps to this channel* if Slack opens a menu), then try again."
    )


def _team_id(body: dict) -> str:
    return (body.get("team") or {}).get("id") or (body.get("user") or {}).get("team_id", "")


def _dm(client, user_id: str, text: str) -> None:  # noqa: ANN001
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception:
        logger.info("polls: could not DM a reply")


def _ephemeral(client, channel_id: str, user_id: str, text: str) -> None:  # noqa: ANN001
    try:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)
    except Exception:
        logger.info("polls: could not send an ephemeral reply")


def _user_zone(client, user_id: str) -> ZoneInfo:  # noqa: ANN001
    """The person's Slack timezone, or UTC."""
    try:
        from src.core.timezones import canonical_tz  # noqa: PLC0415

        return ZoneInfo(canonical_tz(client.users_info(user=user_id)["user"].get("tz") or "UTC"))
    except Exception:
        return ZoneInfo("UTC")


def closes_at_for(choice: str, now: datetime, zone: ZoneInfo) -> datetime | None:
    """When a poll closes for one of the form's Close choices. None is never."""
    if choice == "1h":
        return now + timedelta(hours=1)
    if choice == "1d":
        return now + timedelta(days=1)
    if choice == "1w":
        return now + timedelta(weeks=1)
    if choice == "today":
        local = now.astimezone(zone)
        end = local.replace(hour=23, minute=59, second=0, microsecond=0)
        return end.astimezone(timezone.utc)
    return None


# ── Showing a poll ──────────────────────────────────────────────────────────


def refresh(client, poll_id: int, ts: str | None = None) -> bool:  # noqa: ANN001
    """Redraw the poll message from the database, as it is right now.

    The poll and its votes are read inside polls.db.redraw, under a lock per
    poll that is held across the chat.update, so a vote that races a close
    always draws after it and draws it closed. `ts` is the clicked message,
    used only when the poll row never got its own message_ts.
    """
    import src.modules.polls.db as pdb  # noqa: PLC0415

    def draw(poll: dict, counts: list[int], names: dict | None) -> None:
        target = poll.get("message_ts") or ts
        if not target:
            return
        client.chat_update(
            channel=poll["channel_id"],
            ts=target,
            text=pblocks.fallback_text(poll),
            blocks=pblocks.poll_message(poll, counts, names, closed=bool(poll.get("closed_at"))),
        )

    return pdb.redraw(poll_id, draw)


def finish_poll(client, poll_id: int) -> bool:  # noqa: ANN001
    """Close a poll and show its final results. False when it was already closed.

    The database close comes first and is what counts: a Slack error on the
    final redraw is logged and the poll stays closed. Used by the Close
    button, the auto-close job, the dashboard and turning Polls off.
    """
    import src.core.analytics as analytics  # noqa: PLC0415
    import src.modules.polls.db as pdb  # noqa: PLC0415

    if not pdb.close_poll(poll_id):
        return False
    poll = pdb.get_poll(poll_id)
    if not poll:
        return True
    analytics.capture("poll_closed", poll["team_id"], options=len(poll["options"]), votes=sum(pdb.tally(poll_id)))
    if client is None:
        return True
    try:
        refresh(client, poll_id)
    except Exception as exc:
        logger.warning("polls: closed poll %s but could not update its message: %s", poll_id, exc)
    return True


def close_all(team_id: str) -> int:
    """Close every open poll in a workspace. For when Polls is turned off. Returns how many."""
    import src.modules.polls.db as pdb  # noqa: PLC0415
    from src.modules.polls.jobs import bot_client  # noqa: PLC0415

    client = bot_client(team_id)
    closed = 0
    for poll_id in pdb.open_poll_ids(team_id):
        try:
            if finish_poll(client, poll_id):
                closed += 1
        except Exception:
            logger.exception("polls: could not close poll %s while turning Polls off", poll_id)
    logger.info("polls: turned off in %s, closed %d open poll(s)", team_id, closed)
    return closed


# ── Creating a poll ─────────────────────────────────────────────────────────


def post_new_poll(
    client,  # noqa: ANN001
    tell,  # noqa: ANN001
    team_id: str,
    user_id: str,
    channel_id: str,
    question: str,
    options: list[str],
    anonymous: bool = False,
    multiple: bool = False,
    hide_results: bool = False,
    closes_at: datetime | None = None,
) -> int | None:
    """Store and post a poll, or tell the person why not. Returns the poll id.

    Nothing is stored until the bot is known to be in the channel, and a poll
    whose message fails to post is deleted again, so no half-created poll is
    left behind.
    """
    import src.core.analytics as analytics  # noqa: PLC0415
    import src.modules.polls.db as pdb  # noqa: PLC0415
    from src.core.standup_invites import bot_channel_ids  # noqa: PLC0415

    if not channel_id or not channel_id.startswith(("C", "G")):
        tell(NOT_A_CHANNEL)
        return None
    try:
        member = channel_id in bot_channel_ids(client)
    except Exception as exc:
        logger.warning("polls: could not list the bot's channels in %s: %s", team_id, exc)
        tell(COULD_NOT_CHECK)
        return None
    if not member:
        tell(invite_text(channel_id))
        return None

    try:
        poll_id = pdb.create_poll(
            team_id, user_id, channel_id, question, options, anonymous, multiple, hide_results, closes_at
        )
        poll = pdb.get_poll(poll_id)
    except Exception:
        logger.exception("polls: could not save a poll in %s", team_id)
        tell(COULD_NOT_SAVE)
        return None

    try:
        resp = client.chat_postMessage(
            channel=channel_id,
            text=pblocks.fallback_text(poll),
            blocks=pblocks.poll_message(poll, [0] * len(options), {}, closed=False),
        )
    except Exception as exc:
        logger.warning("polls: could not post poll %s in %s: %s", poll_id, team_id, exc)
        try:
            pdb.delete_poll(poll_id)
        except Exception:
            logger.exception("polls: could not remove unposted poll %s", poll_id)
        try:
            error = exc.response["error"]  # type: ignore[attr-defined]
        except Exception:
            error = "an error"
        tell(f"I couldn't post the poll in <#{channel_id}> ({error}). Nothing was saved, so you can try again.")
        return None

    if not _save_message(client, tell, poll_id, channel_id, resp["ts"]):
        return None

    analytics.capture(
        "poll_created",
        team_id,
        options=len(options),
        anonymous=bool(anonymous),
        multiple=bool(multiple),
        hide_results=bool(hide_results),
    )
    return poll_id


def _save_message(client, tell, poll_id: int, channel_id: str, ts: str) -> bool:  # noqa: ANN001
    """Store the posted message's ts on the poll, so votes can redraw it.

    Tried twice. If it still fails the message is taken down and the row
    deleted, so the person can simply try again. If the message cannot be
    taken down the row stays: a live poll message with no row behind it would
    take votes that go nowhere, while a row without its ts still works off
    the clicked message.
    """
    import src.modules.polls.db as pdb  # noqa: PLC0415

    for attempt in (1, 2):
        try:
            pdb.set_message(poll_id, ts)
            return True
        except Exception as exc:
            logger.warning("polls: could not save the message of poll %s (attempt %d): %s", poll_id, attempt, exc)
    try:
        client.chat_delete(channel=channel_id, ts=ts)
    except Exception as exc:
        logger.error("polls: poll %s is posted but its message could not be saved or removed: %s", poll_id, exc)
        return True
    try:
        pdb.delete_poll(poll_id)
    except Exception:
        logger.exception("polls: could not remove poll %s after taking its message down", poll_id)
    tell("Something went wrong saving that poll, so I took it down again. Please try again in a minute.")
    return False


def handle_poll_command(body: dict, client, respond, args_text: str) -> None:  # noqa: ANN001
    """`/morgenruf poll`: the form when bare, the quick syntax otherwise."""
    user_id = body.get("user_id", "")
    team_id = body.get("team_id", "")
    channel_id = body.get("channel_id", "")

    def tell(text: str) -> None:
        if respond is not None:
            try:
                respond(text=text, response_type="ephemeral")
                return
            except Exception:
                logger.info("polls: respond failed, sending a DM instead")
        _dm(client, user_id, text)

    if not args_text.strip():
        try:
            client.views_open(trigger_id=body.get("trigger_id", ""), view=pblocks.create_modal(channel_id))
        except Exception:
            logger.exception("polls: could not open the form")
            tell("I couldn't open the poll form just now. Please try again in a minute.")
        return

    found = parse_quick(args_text)
    if not found:
        tell(USAGE)
        return
    question, options = found
    error = question_error(question) or options_error(options)
    if error:
        tell(f"{error} {USAGE}")
        return
    post_new_poll(client, tell, team_id, user_id, channel_id, question, options)


def form_errors(values: dict) -> tuple[dict, dict]:
    """The form's fields and its errors by block id."""

    def state(block: str, action: str) -> dict:
        return (values.get(block) or {}).get(action) or {}

    question = unslack(state("question", "polls:question").get("value") or "").strip()
    options = options_from_lines(unslack(state("options", "polls:options").get("value") or ""))
    channel = state("channel", "polls:channel").get("selected_conversation") or ""
    checks = {o.get("value") for o in state("settings", "polls:settings").get("selected_options") or []}
    close = (state("close", "polls:close_after").get("selected_option") or {}).get("value") or "never"

    errors = {}
    if err := question_error(question):
        errors["question"] = err
    if err := options_error(options):
        errors["options"] = err
    if not channel.startswith(("C", "G")):
        errors["channel"] = "Pick a channel. A poll can't go in a DM."
    fields = {
        "question": question,
        "options": options,
        "channel_id": channel,
        "anonymous": pblocks.CHECK_ANONYMOUS in checks,
        "multiple": pblocks.CHECK_MULTIPLE in checks,
        "hide_results": pblocks.CHECK_HIDE in checks,
        "close": close,
    }
    return fields, errors


# ── Voting and closing ──────────────────────────────────────────────────────


def _module_on(team_id: str) -> bool:
    from src.core.modules import is_active_for  # noqa: PLC0415

    return is_active_for(team_id, MODULE_NAME)


def handle_vote(ack, body, client) -> None:  # noqa: ANN001
    ack()
    import src.modules.polls.db as pdb  # noqa: PLC0415

    action = (body.get("actions") or [{}])[0]
    match = _VOTE.match(action.get("action_id", ""))
    user_id = (body.get("user") or {}).get("id", "")
    channel_id = (body.get("channel") or {}).get("id", "")
    team_id = _team_id(body)
    if not match:
        return
    poll_id, idx = int(match.group(1)), int(match.group(2))
    poll = pdb.get_poll(poll_id)
    if not poll or poll.get("closed_at") or poll.get("team_id") != team_id or idx >= len(poll["options"]):
        _ephemeral(client, channel_id, user_id, CLOSED)
        return
    if not _module_on(team_id):
        _ephemeral(client, channel_id, user_id, TURNED_OFF)
        return
    if poll.get("anonymous") and not poll.get("salt"):
        # Open but saltless: the database was restored from a backup, which
        # leaves poll_salts out. Its votes can no longer be keyed.
        _ephemeral(client, channel_id, user_id, NO_SALT)
        return
    try:
        key = pdb.voter_key(poll, user_id)
        if not pdb.toggle_vote(poll_id, idx, key, bool(poll.get("multiple"))):
            _ephemeral(client, channel_id, user_id, CLOSED)
            return
    except Exception:
        logger.exception("polls: could not record a vote on poll %s", poll_id)
        _ephemeral(client, channel_id, user_id, "I couldn't record that vote. Please try again.")
        return

    ts = (body.get("container") or {}).get("message_ts") or (body.get("message") or {}).get("ts")
    try:
        refresh(client, poll_id, ts)
    except Exception as exc:
        logger.warning("polls: vote saved but could not update poll %s: %s", poll_id, exc)

    if poll.get("anonymous"):
        # No names show on an anonymous poll, so this is the only place a voter
        # can see what they picked.
        try:
            picked = [poll["options"][i] for i in pdb.my_choices(poll_id, key)]
        except Exception:
            picked = None
        if picked is None:
            return
        if picked:
            chosen = ", ".join(f"*{pblocks.escape(p)}*" for p in picked)
            text = f"You voted for {chosen}. Only you can see this."
        else:
            text = "You have no vote on this poll now. Only you can see this."
        _ephemeral(client, poll["channel_id"], user_id, text)


def handle_close(ack, body, client) -> None:  # noqa: ANN001
    ack()
    import src.core.db as db  # noqa: PLC0415
    import src.modules.polls.db as pdb  # noqa: PLC0415

    action = (body.get("actions") or [{}])[0]
    match = _CLOSE.match(action.get("action_id", ""))
    user_id = (body.get("user") or {}).get("id", "")
    channel_id = (body.get("channel") or {}).get("id", "")
    team_id = _team_id(body)
    if not match:
        return
    poll = pdb.get_poll(int(match.group(1)))
    if not poll or poll.get("team_id") != team_id:
        _ephemeral(client, channel_id, user_id, CLOSED)
        return
    if poll.get("closed_at"):
        return
    allowed = poll.get("created_by") == user_id
    if not allowed:
        try:
            allowed = db.can_administer(team_id, user_id, MODULE_NAME)
        except Exception:
            allowed = False
    if not allowed:
        _ephemeral(client, channel_id, user_id, "Only the person who started this poll, or an admin, can close it.")
        return
    finish_poll(client, poll["id"])


def handle_open(ack, body, client) -> None:  # noqa: ANN001
    ack()
    try:
        client.views_open(trigger_id=body.get("trigger_id", ""), view=pblocks.create_modal())
    except Exception:
        logger.exception("polls: could not open the form from the Home tab")


def handle_create_submit(ack, body, view, client) -> None:  # noqa: ANN001
    fields, errors = form_errors((view or {}).get("state", {}).get("values", {}))
    if errors:
        ack(response_action="errors", errors=errors)
        return
    ack()
    user_id = (body.get("user") or {}).get("id", "")
    team_id = _team_id(body)
    if not _module_on(team_id):
        _dm(client, user_id, TURNED_OFF)
        return
    closes_at = closes_at_for(fields["close"], datetime.now(timezone.utc), _user_zone(client, user_id))
    post_new_poll(
        client,
        lambda text: _dm(client, user_id, text),
        team_id,
        user_id,
        fields["channel_id"],
        fields["question"],
        fields["options"],
        anonymous=fields["anonymous"],
        multiple=fields["multiple"],
        hide_results=fields["hide_results"],
        closes_at=closes_at,
    )


# ── App Home ────────────────────────────────────────────────────────────────


def home_blocks(team_id: str, user_id: str) -> list[dict]:
    """A Create button, and the viewer's own open polls."""
    import src.modules.polls.db as pdb  # noqa: PLC0415

    try:
        mine = pdb.open_polls_by(team_id, user_id, limit=3)
    except Exception as exc:
        logger.warning("polls App Home unavailable for %s: %s", team_id, exc)
        mine = []
    blocks: list[dict] = [
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📊 Polls*\nAsk the team something. Votes update live."},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Create a poll"},
                "action_id": pblocks.OPEN_ACTION,
            },
        },
    ]
    if mine:
        lines = "\n".join(f"• <#{p['channel_id']}>  {pblocks.escape(p['question'])}" for p in mine)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Your open polls*\n{lines}"}})
    return blocks


def register_handlers(app) -> None:
    """Votes, closes, the form and the Home button. The command is a subcommand."""
    app.action(re.compile(r"^polls:vote:"))(handle_vote)
    app.action(re.compile(r"^polls:close:"))(handle_close)
    app.action(pblocks.OPEN_ACTION)(handle_open)
    app.view(pblocks.CREATE_CALLBACK)(handle_create_submit)
