"""Quick start: a standup from two fields, from the welcome DM or an empty Home tab.

The full create form asks for a lot and only lists channels the bot is
already in, and most new workspaces never finished it. This asks for a
channel and a time. If the bot is not in that channel, the standup is saved
waiting for an invite instead of refusing, because the bot cannot join a
channel on its own; the invite switches it on.
"""

from __future__ import annotations

import logging

from src.core.quickstart_button import OPEN_ACTION, button_block
from src.core.schedule_validation import DEFAULT_QUESTIONS, schedule_time_error, schedule_timezone_error
from src.core.standup_invites import activate_waiting, bot_channel_ids, channel_humans, when_text

logger = logging.getLogger(__name__)

CALLBACK_ID = "quickstart_modal"
DEFAULT_TIME = "09:30"
WEEKDAYS = "mon,tue,wed,thu,fri"

__all__ = ["OPEN_ACTION", "CALLBACK_ID", "button_block", "activate_waiting", "register"]


def quick_start_offers(team_id: str) -> list[tuple[str, str, object]]:
    """(module name, label, start) for every module offering a quick start extra here.

    Read from the registry, so this module never imports another by name. A
    module is offered when this deployment and installation permit it, even
    if the workspace has not switched it on yet: ticking the box is how they
    switch it on.
    """
    try:
        import src.core.db as db  # noqa: PLC0415
        from src.core.modules import deploy_allowlist, is_active  # noqa: PLC0415
        from src.modules import REGISTRY  # noqa: PLC0415

        granted = db.granted_scopes(team_id)
        allowlist = deploy_allowlist()
        return [
            (spec.name, spec.quick_start[0], spec.quick_start[1])
            for spec in REGISTRY
            if spec.quick_start and is_active(spec, granted, True, allowlist)
        ]
    except Exception as exc:
        logger.info("quickstart: no extras for %s: %s", team_id, exc)
        return []


def _extras_block(offers: list) -> list[dict]:
    if not offers:
        return []
    options = [{"text": {"type": "plain_text", "text": label}, "value": name} for name, label, _ in offers]
    return [
        {
            "type": "input",
            "block_id": "extras",
            "optional": True,
            "label": {"type": "plain_text", "text": "Also"},
            "element": {
                "type": "checkboxes",
                "action_id": "extras",
                "options": options,
                "initial_options": options,
            },
        }
    ]


def modal(tz: str, offers: list | None = None) -> dict:
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
            *_extras_block(offers or []),
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
    return bot_channel_ids(client)


def _channel_humans(client, channel_id: str) -> list[str]:
    return channel_humans(client, channel_id)


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
    team_id = _team_id(body)
    client.views_open(trigger_id=body["trigger_id"], view=modal(_user_tz(client, user_id), quick_start_offers(team_id)))


def _channel_error(channel_id: str | None) -> str | None:
    if not channel_id:
        return "Pick the channel your team talks in."
    # Public channels start with C and private ones with G. A DM or a group
    # DM picked from the list has nobody to sync with.
    if not channel_id.startswith(("C", "G")):
        return "Pick a channel, not a direct message."
    return None


def _already_has_standup(team_id: str, channel_id: str) -> bool:
    import src.core.db as db  # noqa: PLC0415

    return any(s.get("channel_id") == channel_id for s in db.get_standup_schedules(team_id))


def handle_submit(ack, body, view, client, on_saved=None) -> None:
    import src.core.db as db  # noqa: PLC0415

    values = view["state"]["values"]
    channel_id = (values.get("channel", {}).get("channel") or {}).get("selected_conversation")
    time = (values.get("time", {}).get("time") or {}).get("selected_time") or DEFAULT_TIME
    extras = {o["value"] for o in (values.get("extras", {}).get("extras") or {}).get("selected_options") or []}
    user_id = body["user"]["id"]
    team_id = _team_id(body)
    channel_error = _channel_error(channel_id)
    if channel_error:
        ack(response_action="errors", errors={"channel": channel_error})
        return
    if schedule_time_error(time):
        ack(response_action="errors", errors={"time": "Pick a time such as 09:30."})
        return
    # Checked again on submit, not only on open: this is what writes, and a
    # role can change while the modal is open.
    if not _may_manage(team_id, user_id):
        ack(response_action="errors", errors={"channel": "Only a workspace admin or a standup admin can do this."})
        return
    # A second press of the same button must not start a second standup.
    try:
        duplicate = _already_has_standup(team_id, channel_id)
    except Exception as exc:
        logger.warning("quickstart: could not list standups for %s: %s", team_id, exc)
        ack(response_action="errors", errors={"channel": "Couldn't check the channel, please try again."})
        return
    if duplicate:
        ack(
            response_action="errors",
            errors={"channel": "This channel already has a standup. Change it from the Home tab."},
        )
        return
    ack()

    # A wrong answer here is worse than none: a joined channel saved as
    # waiting never switches on, so any Slack error saves nothing.
    try:
        joined = channel_id in _bot_channel_ids(client)
        participants = _channel_humans(client, channel_id) if joined else []
    except Exception as exc:
        logger.warning("quickstart: could not check %s in %s: %s", channel_id, team_id, exc)
        client.chat_postMessage(channel=user_id, text="Couldn't check the channel, please try again.")
        return

    tz = _user_tz(client, user_id)
    try:
        db.create_standup_schedule(
            team_id,
            name="Daily standup",
            channel_id=channel_id,
            schedule_time=time,
            schedule_tz=tz,
            schedule_days=WEEKDAYS,
            questions=list(DEFAULT_QUESTIONS),
            participants=participants,
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
        text = f"Your standup is set. Everyone in <#{channel_id}> gets the questions {when_text(time, tz)}."
    else:
        text = (
            f"Saved for {when_text(time, tz)}. One step left: add me to <#{channel_id}>. "
            "Type `/invite @Morgenruf` there. If Slack opens a menu instead, pick "
            "*Add agents and apps to this channel* and press *Add* next to Morgenruf. "
            "The standup switches on the moment I'm in, and I'll tell you here."
        )
    for name, _label, start in quick_start_offers(team_id) if extras else []:
        if name not in extras:
            continue
        try:
            start(team_id, channel_id, user_id, tz)
        except Exception as exc:
            logger.warning("quickstart: %s did not start for %s: %s", name, team_id, exc)
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception as exc:
        logger.warning("quickstart: could not confirm to %s: %s", user_id, exc)
    if on_saved:
        try:
            on_saved(team_id, user_id, client)
        except Exception as exc:
            logger.info("quickstart: could not refresh Home for %s: %s", user_id, exc)


def register(app, refresh_home=None) -> None:
    """Wire the button and the modal. `refresh_home(team_id, user_id, client)`
    redraws the Home tab after a save, so the empty state does not linger."""
    app.action(OPEN_ACTION)(handle_open)

    def _submit(ack, body, view, client) -> None:  # noqa: ANN001
        handle_submit(ack, body, view, client, on_saved=refresh_home)

    app.view(CALLBACK_ID)(_submit)
