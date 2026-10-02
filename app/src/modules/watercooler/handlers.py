"""Watercooler in Slack: `/morgenruf watercooler`, the setup modal, the Home section.

No new slash command, shortcut, event or scope: the command is a subcommand
of `/morgenruf` and the Home section is the module's home_blocks hook.
"""

from __future__ import annotations

import logging

from src.core.schedule_validation import schedule_time_error, schedule_timezone_error
from src.modules.watercooler import messages

logger = logging.getLogger(__name__)

MODULE_NAME = "watercooler"
NOT_ALLOWED = (
    "Only a workspace admin or someone in charge of Watercooler can set it up. "
    "Ask an admin, or ask them to put you in charge of Watercooler in the dashboard."
)


def may_manage(team_id: str, user_id: str) -> bool:
    try:
        import src.core.db as db  # noqa: PLC0415

        # `is True`: a lookup that returns anything but a real True refuses.
        return db.can_administer(team_id, user_id, MODULE_NAME) is True
    except Exception as exc:
        logger.warning("watercooler: could not check %s: %s", user_id, exc)
        return False


def user_tz(client, user_id: str) -> str:
    try:
        tz = (client.users_info(user=user_id) or {}).get("user", {}).get("tz") or "UTC"
    except Exception:
        return "UTC"
    return "UTC" if not isinstance(tz, str) or schedule_timezone_error(tz) else tz


def _dm(client, user_id: str, text: str) -> None:
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception as exc:
        logger.info("watercooler: could not DM %s: %s", user_id, exc)


def open_setup(client, trigger_id: str, team_id: str, user_id: str) -> None:
    if not may_manage(team_id, user_id):
        _dm(client, user_id, NOT_ALLOWED)
        return
    client.views_open(trigger_id=trigger_id, view=messages.setup_modal(user_tz(client, user_id)))


def handle_command(body: dict, client, respond, args_text: str) -> None:  # noqa: ANN001, ARG001
    """`/morgenruf watercooler`: the setup modal."""
    try:
        open_setup(client, body.get("trigger_id", ""), body.get("team_id", ""), body.get("user_id", ""))
    except Exception:
        logger.exception("watercooler: could not open the setup modal")


def handle_open(ack, body, client) -> None:  # noqa: ANN001
    ack()
    team_id = (body.get("team") or {}).get("id") or body["user"].get("team_id", "")
    try:
        open_setup(client, body.get("trigger_id", ""), team_id, body["user"]["id"])
    except Exception:
        logger.exception("watercooler: could not open the setup modal from Home")


def _values(view: dict) -> tuple[str, list[str], str]:
    values = (view or {}).get("state", {}).get("values", {})
    channel_id = (values.get("channel", {}).get(messages.CHANNEL_ACTION) or {}).get("selected_conversation") or ""
    days = [o["value"] for o in (values.get("days", {}).get(messages.DAYS_ACTION) or {}).get("selected_options") or []]
    time = (values.get("time", {}).get(messages.TIME_ACTION) or {}).get("selected_time") or ""
    return channel_id, days, time


def setup_errors(channel_id: str, days: list[str], time: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not channel_id or not channel_id.startswith(("C", "G")):
        errors["channel"] = "Pick a channel, not a direct message."
    if not days:
        errors["days"] = "Pick at least one day."
    if not time or schedule_time_error(time):
        errors["time"] = "Pick a time such as 10:00."
    return errors


def handle_submit(ack, body, view, client) -> None:  # noqa: ANN001
    import src.modules.watercooler.db as wdb  # noqa: PLC0415

    team_id = (body.get("team") or {}).get("id") or body["user"].get("team_id", "")
    user_id = body["user"]["id"]
    channel_id, days, time = _values(view)
    errors = setup_errors(channel_id, days, time)
    if not errors and not may_manage(team_id, user_id):
        errors["channel"] = NOT_ALLOWED
    if not errors:
        try:
            exists = wdb.get_channel(team_id, channel_id) is not None
            if not exists and wdb.count_channels(team_id) >= wdb.MAX_CHANNELS:
                errors["channel"] = f"A workspace can have watercooler in at most {wdb.MAX_CHANNELS} channels."
        except Exception as exc:
            logger.warning("watercooler: could not check channels for %s: %s", team_id, exc)
            errors["channel"] = "Couldn't check the channel, please try again."
    if errors:
        ack(response_action="errors", errors=errors)
        return
    ack()
    tz = (view or {}).get("private_metadata") or "UTC"
    if schedule_timezone_error(tz):
        tz = "UTC"
    day_spec = ",".join(d for d, _ in messages.DAY_OPTIONS if d in days)
    try:
        wdb.save_channel(
            team_id,
            channel_id,
            {"days": day_spec, "post_time": time, "timezone": tz, "active": True, "paused_reason": None},
            created_by=user_id,
        )
    except Exception:
        logger.exception("watercooler: could not save %s for %s", channel_id, team_id)
        _dm(client, user_id, "☕ I couldn't save the watercooler just now. Nothing was changed, please try again.")
        return
    text = messages.saved_text(channel_id, day_spec, time, tz)
    try:
        from src.core.standup_invites import bot_channel_ids  # noqa: PLC0415

        if channel_id not in bot_channel_ids(client):
            text += " One step left: add me to the channel (channel details, then Integrations, then Add apps)."
    except Exception:
        logger.info("watercooler: could not check whether I'm in %s", channel_id)
    _dm(client, user_id, text)


def home_blocks(team_id: str, user_id: str) -> list[dict]:
    import src.modules.watercooler.db as wdb  # noqa: PLC0415

    try:
        channels = wdb.list_channels(team_id)
    except Exception as exc:
        logger.warning("watercooler App Home unavailable for %s: %s", team_id, exc)
        channels = []
    can_set_up = may_manage(team_id, user_id)
    if not channels and not can_set_up:
        return []
    return messages.home_blocks(channels, can_set_up)


def start_default(team_id: str, channel_id: str, user_id: str, tz: str) -> None:
    """Quick start's "also post a watercooler question here": on, Mon/Wed/Fri at 10:00."""
    import src.core.db as db  # noqa: PLC0415
    import src.modules.watercooler.db as wdb  # noqa: PLC0415

    db.set_module_enabled(team_id, MODULE_NAME, True)
    if wdb.get_channel(team_id, channel_id) is None:
        wdb.save_channel(
            team_id,
            channel_id,
            {
                "days": wdb.DEFAULT_DAYS,
                "post_time": wdb.DEFAULT_POST_TIME,
                "timezone": tz or "UTC",
                "active": True,
                "paused_reason": None,
            },
            created_by=user_id,
        )


def register_handlers(app) -> None:
    app.action(messages.OPEN_ACTION)(handle_open)
    app.view(messages.SETUP_CALLBACK)(handle_submit)
