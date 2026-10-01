"""Quick start: a standup from two fields, from the welcome DM or an empty Home tab.

The full create form asks for a lot and only lists channels the bot is
already in, and most new workspaces never finished it. This asks for a
channel and a time. If the bot is not in that channel, the standup is saved
waiting for an invite instead of refusing, because the bot cannot join a
channel on its own; the invite switches it on.
"""

from __future__ import annotations

import logging

from src.core.schedule_validation import DEFAULT_QUESTIONS, schedule_time_error, schedule_timezone_error

logger = logging.getLogger(__name__)

OPEN_ACTION = "quickstart:open"
CALLBACK_ID = "quickstart_modal"
DEFAULT_TIME = "09:30"
WEEKDAYS = "mon,tue,wed,thu,fri"


def button_block() -> dict:
    """The "Start a standup" button. Its own block_id, so a message can drop
    other action blocks (the email offer) and keep this one."""
    return {
        "type": "actions",
        "block_id": "quickstart",
        "elements": [
            {
                "type": "button",
                "style": "primary",
                "action_id": OPEN_ACTION,
                "text": {"type": "plain_text", "text": "Start a standup"},
            }
        ],
    }


def modal(tz: str) -> dict:
    return {
        "type": "modal",
        "callback_id": CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Start a standup"},
        "submit": {"type": "plain_text", "text": "Start"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "channel",
                "label": {"type": "plain_text", "text": "Which channel is the team in?"},
                "element": {
                    "type": "conversations_select",
                    "action_id": "channel",
                    "default_to_current_conversation": True,
                    "filter": {"include": ["public", "private"], "exclude_bot_users": True},
                },
            },
            {
                "type": "input",
                "block_id": "time",
                "label": {"type": "plain_text", "text": "When should the questions arrive?"},
                "element": {"type": "timepicker", "action_id": "time", "initial_time": DEFAULT_TIME},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Everyone in the channel gets the three standard questions by DM on weekdays "
                            f"at this time ({tz}). The summary posts in the channel an hour later. "
                            "Change anything later from the Home tab."
                        ),
                    }
                ],
            },
        ],
    }


def _team_id(body: dict) -> str:
    return (body.get("team") or {}).get("id") or body["user"].get("team_id", "")


def _user_tz(client, user_id: str) -> str:
    """The person's Slack timezone, or UTC when Slack has none the scheduler accepts."""
    try:
        tz = client.users_info(user=user_id)["user"].get("tz") or "UTC"
    except Exception:
        return "UTC"
    return "UTC" if schedule_timezone_error(tz) else tz


def _bot_channel_ids(client) -> set[str]:
    from src.modules.standup.handlers import _get_bot_channels  # noqa: PLC0415

    return {c["id"] for c in _get_bot_channels(client)}


def _may_manage(team_id: str, user_id: str) -> bool:
    from src.modules.standup.handlers import may_manage_standups  # noqa: PLC0415

    return may_manage_standups(team_id, user_id)


def handle_open(ack, body, client) -> None:
    ack()
    user_id = body["user"]["id"]
    if not _may_manage(_team_id(body), user_id):
        from src.modules.standup.handlers import _refuse_standup_change  # noqa: PLC0415

        _refuse_standup_change(client, user_id)
        return
    client.views_open(trigger_id=body["trigger_id"], view=modal(_user_tz(client, user_id)))


def handle_submit(ack, body, view, client, on_saved=None) -> None:
    import src.core.db as db  # noqa: PLC0415

    values = view["state"]["values"]
    channel_id = (values.get("channel", {}).get("channel") or {}).get("selected_conversation")
    time = (values.get("time", {}).get("time") or {}).get("selected_time") or DEFAULT_TIME
    user_id = body["user"]["id"]
    team_id = _team_id(body)
    if not channel_id:
        ack(response_action="errors", errors={"channel": "Pick the channel your team talks in."})
        return
    if schedule_time_error(time):
        ack(response_action="errors", errors={"time": "Pick a time such as 09:30."})
        return
    # Checked again on submit, not only on open: this is what writes, and a
    # role can change while the modal is open.
    if not _may_manage(team_id, user_id):
        ack(response_action="errors", errors={"channel": "Only a workspace admin or a standup admin can do this."})
        return
    ack()

    joined = channel_id in _bot_channel_ids(client)
    try:
        db.create_standup_schedule(
            team_id,
            name="Daily standup",
            channel_id=channel_id,
            schedule_time=time,
            schedule_tz=_user_tz(client, user_id),
            schedule_days=WEEKDAYS,
            questions=list(DEFAULT_QUESTIONS),
            participants=[],
            sync_with_channel=True,
            active=joined,
            awaiting_invite_by=None if joined else user_id,
        )
    except Exception as exc:
        logger.error("quickstart: could not save the standup for %s: %s", team_id, exc)
        client.chat_postMessage(
            channel=user_id, text="I couldn't save the standup just now. Nothing was changed, please try again."
        )
        return

    if joined:
        text = f"Your standup is set. Everyone in <#{channel_id}> gets the questions on weekdays at {time}."
    else:
        text = (
            f"Saved. One step left: type `/invite @Morgenruf` in <#{channel_id}>. "
            "The standup switches on the moment I'm in, and I'll tell you here."
        )
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception as exc:
        logger.warning("quickstart: could not confirm to %s: %s", user_id, exc)
    if on_saved:
        try:
            on_saved(team_id, user_id, client)
        except Exception as exc:
            logger.info("quickstart: could not refresh Home for %s: %s", user_id, exc)


def activate_waiting(client, team_id: str, channel_id: str) -> int:
    """The bot was invited to a channel: switch on standups that were waiting for it.

    Returns how many were switched on. A standup is switched on, and its
    creator told, only by the call that cleared its waiting flag, so an
    invite with nothing waiting, or a second invite, does nothing.
    """
    import src.core.db as db  # noqa: PLC0415

    switched = 0
    for row in db.waiting_standups(team_id, channel_id):
        if not db.activate_waiting_standup(row["id"]):
            continue
        switched += 1
        try:
            client.chat_postMessage(
                channel=row["awaiting_invite_by"],
                text=f"I'm in <#{channel_id}> now, so your standup is on: weekdays at {row['schedule_time']}.",
            )
        except Exception:
            logger.info("quickstart: could not confirm activation for schedule %s", row["id"])
    return switched


def register(app, refresh_home=None) -> None:
    """Wire the button and the modal. `refresh_home(team_id, user_id, client)`
    redraws the Home tab after a save, so the empty state does not linger."""
    app.action(OPEN_ACTION)(handle_open)

    def _submit(ack, body, view, client) -> None:  # noqa: ANN001
        handle_submit(ack, body, view, client, on_saved=refresh_home)

    app.view(CALLBACK_ID)(_submit)
