"""Standups waiting for the bot to be invited to their channel.

The quick start saves a standup for a channel the bot is not in as waiting
(awaiting_invite_by), because the bot cannot join a channel on its own.
member_joined_channel for the bot switches it on. Slack sends no such event
for a bot that was already a member, and an event can be dropped, so an
hourly sweep checks the bot's channels once per team and switches on
whatever it finds there.

Core, not the standup module, because the hourly job runs in core and core
does not import feature modules. The quick start re-exports activate_waiting.
"""

from __future__ import annotations

import logging

from slack_sdk import WebClient

from src.core.slack_users import filter_human_ids

logger = logging.getLogger(__name__)


def bot_channel_ids(client) -> set[str]:  # noqa: ANN001
    """Every channel the bot is in. Raises on any Slack error.

    Never a partial list: a channel missing from it would save a standup the
    bot can already run as waiting for an invite that never comes.
    """
    ids: set[str] = set()
    cursor = None
    while True:
        kwargs = {"types": "public_channel,private_channel", "exclude_archived": True, "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.users_conversations(**kwargs)
        ids.update(c["id"] for c in resp.get("channels", []))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            return ids


def channel_humans(client, channel_id: str) -> list[str]:  # noqa: ANN001
    """The people in a channel, bots and deactivated accounts left out. Raises on a Slack error."""
    members: list[str] = []
    cursor = None
    while True:
        kwargs = {"channel": channel_id, "limit": 500}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.conversations_members(**kwargs)
        members.extend(resp.get("members", []))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    humans = filter_human_ids(client, members)
    return [m for m in members if m in humans]


def when_text(schedule_time: str, schedule_tz: str | None) -> str:
    """When a quick start standup runs, as in: weekdays at 09:30 Europe/Berlin."""
    return f"weekdays at {schedule_time} {schedule_tz or 'UTC'}"


def activate_waiting(client, team_id: str, channel_id: str) -> int:  # noqa: ANN001
    """The bot is in `channel_id` now: switch on standups that were waiting for it.

    Returns how many were switched on. A standup is switched on, seeded with
    the channel's people and its creator told, only by the call that cleared
    its waiting flag, so an invite with nothing waiting, or a second invite,
    does nothing.
    """
    import src.core.db as db  # noqa: PLC0415

    switched = 0
    for row in db.waiting_standups(team_id, channel_id):
        if not db.activate_waiting_standup(row["id"]):
            continue
        switched += 1
        try:
            db.update_standup_schedule(team_id, row["id"], participants=channel_humans(client, channel_id))
        except Exception as exc:
            # The scheduler skips a synced run it cannot fill from the
            # channel, so an empty list never means "everyone".
            logger.info("standup invites: could not seed participants for schedule %s: %s", row["id"], exc)
        try:
            client.chat_postMessage(
                channel=row["awaiting_invite_by"],
                text=(
                    f"I'm in <#{channel_id}> now, so your standup is on: "
                    f"{when_text(row['schedule_time'], row.get('schedule_tz'))}."
                ),
            )
        except Exception:
            logger.info("standup invites: could not confirm activation for schedule %s", row["id"])
    return switched


def _bot_token(team_id: str, stored: str) -> str:
    from src.core.scheduler import _fresh_bot_token  # noqa: PLC0415

    return _fresh_bot_token(team_id, stored)


def sweep_waiting_standups() -> int:
    """Hourly: switch on waiting standups whose channel the bot is now in. Returns how many."""
    import src.core.db as db  # noqa: PLC0415

    switched = 0
    for team in db.teams_with_waiting_standups():
        team_id = team["team_id"]
        try:
            client = WebClient(token=_bot_token(team_id, team["bot_token"]))
            joined = bot_channel_ids(client)
            for channel_id in team.get("channel_ids") or []:
                if channel_id in joined:
                    switched += activate_waiting(client, team_id, channel_id)
        except Exception as exc:
            logger.info("standup invites: could not check %s: %s", team_id, exc)
    if switched:
        logger.info("Switched on %d waiting standups the bot is now in", switched)
    return switched
