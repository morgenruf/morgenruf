"""Keeping the kudos token in step with the workspace's emoji.

Runs daily rather than on every kudos: emoji.list is a workspace-wide call and
the answer changes about as often as someone edits their emoji, which is to
say almost never.
"""

from __future__ import annotations

import logging

from apscheduler.triggers.cron import CronTrigger

from src.core.scheduler import JobSpec

logger = logging.getLogger(__name__)


def plan_jobs(ctx: dict) -> list[JobSpec]:
    team_id = ctx["team_id"]
    return [
        JobSpec(
            key="token-sync",
            # Early morning UTC, away from the hours standups run in.
            trigger=CronTrigger(hour=4, minute=17),
            func=sync_token,
            args=(team_id, ctx.get("bot_token", "")),
        )
    ]


def _client(bot_token: str, team_id: str):
    from slack_sdk import WebClient  # noqa: PLC0415

    if bot_token:
        return WebClient(token=bot_token)
    try:
        import src.core.db as db  # noqa: PLC0415

        inst = db.get_installation(team_id)
        return WebClient(token=inst["bot_token"]) if inst and inst.get("bot_token") else None
    except Exception:
        return None


def sync_token(team_id: str, bot_token: str = "") -> None:
    """Upgrade to the branded token once the emoji exists, and back off if it goes."""
    import src.modules.kudos.db as kdb  # noqa: PLC0415
    from src.modules.kudos.token import resolve, workspace_has_brand_emoji  # noqa: PLC0415

    client = _client(bot_token, team_id)
    if client is None:
        return
    cfg = kdb.get_config(team_id)
    wanted = resolve(cfg["emoji"], cfg.get("token_auto", True), workspace_has_brand_emoji(client))
    if wanted is None:
        return
    try:
        kdb.set_token_automatically(team_id, wanted)
        logger.info("kudos: token for %s is now %s", team_id, wanted)
    except Exception:
        logger.exception("kudos: could not update the token for %s", team_id)
