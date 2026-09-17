"""The scheduled work: start a round, deliver it, nudge, then close it.

Delivery is the part that has to be careful. A 200 person channel is 100 group
DMs in a burst, so each match is marked delivered as it succeeds and a restart
resumes from the undelivered ones rather than messaging everyone twice.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from slack_sdk import WebClient

from src.core.scheduler import JobSpec
from src.modules.connect import blocks as cblocks
from src.modules.connect import slack_api as api
from src.modules.connect.matcher import match
from src.modules.connect.rounds import is_round_due

logger = logging.getLogger(__name__)

NUDGE_AFTER_DAYS = 3
CLOSE_AFTER_DAYS = 6
MIN_POOL = 2


def plan_jobs(ctx: dict) -> list[JobSpec]:
    """One weekly trigger per programme for this workspace.

    Weekly rather than every-N-weeks because cron cannot express the latter
    cleanly; the job body decides whether today is a round day.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    team_id = ctx["team_id"]
    jobs: list[JobSpec] = []
    try:
        programs = [p for p in cdb.active_programs() if p["team_id"] == team_id]
    except Exception as exc:
        logger.warning("connect could not plan jobs for %s: %s", team_id, exc)
        return []

    for p in programs:
        jobs.append(
            JobSpec(
                key=f"round:{p['id']}",
                trigger=CronTrigger(
                    day_of_week=int(p["day_of_week"]),
                    hour=int(p["hour"]),
                    minute=int(p["minute"]),
                    timezone=p["timezone"] or "UTC",
                ),
                func=run_round,
                args=(p["id"], ctx.get("bot_token", "")),
            )
        )
    return jobs


def _client(bot_token: str, team_id: str) -> WebClient | None:
    if bot_token:
        return WebClient(token=bot_token)
    try:
        import src.core.db as db  # noqa: PLC0415

        inst = db.get_installation(team_id)
        return WebClient(token=inst["bot_token"]) if inst and inst.get("bot_token") else None
    except Exception:
        return None


def run_round(program_id: int, bot_token: str = "") -> None:
    """Start today's round: build the pool, match, then deliver."""
    import src.modules.connect.db as cdb  # noqa: PLC0415
    from src.core.roster import eligible_members  # noqa: PLC0415

    program = cdb.get_program(program_id)
    if not program or not program.get("enabled"):
        return

    today = date.today()
    if not is_round_due(program["interval_weeks"], program.get("last_round"), today):
        logger.info("connect: programme %s not due today", program_id)
        return

    team_id = program["team_id"]
    client = _client(bot_token, team_id)
    if client is None:
        logger.warning("connect: no usable token for %s", team_id)
        return

    # Pool: people in the channel, who are still around, minus opt-outs.
    try:
        in_channel = set(api.channel_member_ids(client, program["channel_id"]))
    except Exception as exc:
        logger.warning("connect: cannot read channel %s: %s", program["channel_id"], exc)
        return

    eligible = {m.user_id for m in eligible_members(team_id)}
    opted_out = cdb.optout_user_ids(team_id, program_id)
    pool = sorted(in_channel & eligible - opted_out)

    if len(pool) < MIN_POOL:
        # Nobody is ever told they were matched with no one.
        logger.info("connect: programme %s has %d eligible, skipping", program_id, len(pool))
        return

    scheduled_for = datetime.now(timezone.utc)
    round_row = cdb.create_round(program_id, team_id, scheduled_for)
    if round_row is None:
        logger.info("connect: a round already exists for programme %s today", program_id)
        return

    groups = match(pool, cdb.pair_history(program_id), seed=round_row["id"], current_round=round_row["id"])
    if not groups:
        cdb.set_round_state(round_row["id"], "closed", 0)
        return

    cdb.create_matches(round_row["id"], team_id, groups)
    cdb.record_pairs(program_id, round_row["id"], groups)
    cdb.set_round_state(round_row["id"], "matched", len(pool))

    deliver_round(round_row["id"], bot_token, team_id, program_id)
    _schedule_followups(round_row["id"], bot_token, team_id)


def deliver_round(round_id: int, bot_token: str, team_id: str, program_id: int) -> None:
    """Open a group DM per match and introduce people.

    Each match is marked delivered as it succeeds, so an interruption resumes
    instead of re-messaging anyone.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    client = _client(bot_token, team_id)
    if client is None:
        return

    pending = cdb.undelivered_matches(round_id)
    for m in pending:
        try:
            channel = api.open_group_dm(client, list(m["member_ids"]))
            text, blocks = cblocks.intro_message(
                list(m["member_ids"]), cblocks.random_seed_for(round_id, m["id"]), program_id
            )
            api.post(client, channel, text, blocks)
            cdb.mark_delivered(m["id"], channel)
        except api.PermanentSlackError as exc:
            # A deactivated member or a lost scope will not fix itself on
            # retry; mark it done so the round can finish.
            logger.warning("connect: match %s undeliverable (%s)", m["id"], exc)
            cdb.mark_delivered(m["id"], "")
        except Exception:
            logger.exception("connect: delivery failed for match %s, will retry", m["id"])
        finally:
            api.throttle()

    cdb.set_round_state(round_id, "delivered")


def nudge_round(round_id: int, bot_token: str, team_id: str) -> None:
    """One reminder to the pairs who have not spoken. Never more than one."""
    import src.modules.connect.db as cdb  # noqa: PLC0415

    client = _client(bot_token, team_id)
    if client is None:
        return
    for m in cdb.matches_for_nudge(round_id):
        try:
            if api.has_replies(client, m["mpim_channel_id"]):
                cdb.mark_nudged(m["id"])  # they are talking; nothing to do
                continue
            text, blocks = cblocks.nudge_message(cblocks.random_seed_for(round_id, m["id"]))
            api.post(client, m["mpim_channel_id"], text, blocks)
            cdb.mark_nudged(m["id"])
        except Exception:
            logger.exception("connect: nudge failed for match %s", m["id"])
        finally:
            api.throttle()


def close_round(round_id: int, bot_token: str, team_id: str) -> None:
    """Ask whether they met. That answer is the only metric worth having."""
    import src.modules.connect.db as cdb  # noqa: PLC0415

    client = _client(bot_token, team_id)
    if client is None:
        return
    for m in cdb.matches_for_close(round_id):
        try:
            text, blocks = cblocks.did_you_meet_message(m["id"])
            api.post(client, m["mpim_channel_id"], text, blocks)
        except Exception:
            logger.exception("connect: close prompt failed for match %s", m["id"])
        finally:
            api.throttle()
    cdb.set_round_state(round_id, "closed")


def _schedule_followups(round_id: int, bot_token: str, team_id: str) -> None:
    """Queue the nudge and the closing question for this round."""
    from src.core.scheduler import get_scheduler  # noqa: PLC0415

    scheduler = get_scheduler()
    if scheduler is None:
        return
    now = datetime.now(timezone.utc)
    scheduler.add_job(
        nudge_round,
        trigger=DateTrigger(run_date=now + timedelta(days=NUDGE_AFTER_DAYS)),
        args=(round_id, bot_token, team_id),
        id=f"connect:{team_id}:nudge:{round_id}",
        replace_existing=True,
    )
    scheduler.add_job(
        close_round,
        trigger=DateTrigger(run_date=now + timedelta(days=CLOSE_AFTER_DAYS)),
        args=(round_id, bot_token, team_id),
        id=f"connect:{team_id}:close:{round_id}",
        replace_existing=True,
    )
