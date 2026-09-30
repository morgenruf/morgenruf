"""Celebrations in Slack: the two buttons on the DM, and the channel join prompt."""

from __future__ import annotations

import logging

from src.modules.celebrations.messages import ADD_DATES_ACTION, SKIP_ACTION, SKIPPED_TEXT

logger = logging.getLogger(__name__)

MODULE_NAME = "celebrations"


def _team_id(body: dict) -> str:
    return (body.get("team") or {}).get("id") or (body.get("user") or {}).get("team_id", "")


def skip_me(team_id: str, user_id: str) -> None:
    """The "Skip me" button: no public celebration. Their dates, if any, stay."""
    import src.core.db as db  # noqa: PLC0415

    db.upsert_member_profile(team_id, user_id, {"celebrate": False}, updated_by=user_id)


def register_handlers(app) -> None:
    @app.action(ADD_DATES_ACTION)
    def handle_add_dates(ack, body, client):  # noqa: ANN001
        """Open the same profile modal as /morgenruf profile."""
        ack()
        from src.core.profile_slack import open_profile_modal  # noqa: PLC0415

        user_id = body["user"]["id"]
        try:
            open_profile_modal(client, body.get("trigger_id", ""), _team_id(body), user_id, source="celebrations")
        except Exception:
            logger.exception("celebrations: could not open the profile modal for %s", user_id)

    @app.action(SKIP_ACTION)
    def handle_skip(ack, body, client):  # noqa: ANN001
        ack()
        user_id = body["user"]["id"]
        try:
            skip_me(_team_id(body), user_id)
        except Exception:
            logger.exception("celebrations: could not record the opt-out for %s", user_id)
            try:
                client.chat_postMessage(channel=user_id, text="That did not save. Please try again.")
            except Exception:
                logger.info("celebrations: could not tell %s the opt-out failed", user_id)
            return
        channel = (body.get("channel") or {}).get("id")
        ts = (body.get("message") or {}).get("ts")
        if not channel or not ts:
            return
        try:
            client.chat_update(
                channel=channel,
                ts=ts,
                text=SKIPPED_TEXT,
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": SKIPPED_TEXT}}],
            )
        except Exception:
            logger.info("celebrations: could not update the DM for %s", user_id)


def on_channel_join(event, client) -> bool:  # noqa: ANN001
    """Someone joined the celebrations channel: ask for their dates if we have none.

    The same DM as the one-time ask, and it counts as one: nobody is asked
    twice within 30 days however often they leave and rejoin. Returns whether
    a DM was sent.
    """
    user_id = event.get("user", "")
    channel_id = event.get("channel", "")
    team_id = event.get("team", "") or ""
    if not user_id or not channel_id or not team_id:
        return False

    from src.core.modules import is_active_for  # noqa: PLC0415

    if not is_active_for(team_id, MODULE_NAME):
        return False

    import src.core.db as db  # noqa: PLC0415
    import src.modules.celebrations.db as cdb  # noqa: PLC0415
    from src.core.slack_users import is_human  # noqa: PLC0415
    from src.modules.celebrations.jobs import ASK_AGAIN_AFTER_DAYS, send_nudge  # noqa: PLC0415
    from src.modules.celebrations.messages import first_name  # noqa: PLC0415

    settings = cdb.get_settings(team_id)
    if not cdb.is_ready(settings) or settings.get("channel_id") != channel_id:
        return False

    profile = db.get_member_profile(team_id, user_id) or {}
    if profile.get("birth_month") or profile.get("start_date") or profile.get("celebrate") is False:
        return False

    try:
        user = (client.users_info(user=user_id) or {}).get("user") or {}
    except Exception:
        logger.info("celebrations: could not look up %s who joined %s", user_id, channel_id)
        return False
    if not is_human(user):
        return False

    if not db.claim_profile_nudges(team_id, [user_id], cooldown_days=ASK_AGAIN_AFTER_DAYS):
        return False
    info = user.get("profile") or {}
    name = first_name(info.get("first_name"), info.get("display_name"), user.get("real_name"))
    return send_nudge(client, user_id, name, channel_id)
