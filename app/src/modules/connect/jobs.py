"""The scheduled work: start a round, deliver it, nudge, then close it.

Delivery is the part that has to be careful. A 200 person channel is 100 group
DMs in a burst, so each match is marked delivered as it succeeds, and the
follow-up sweep resumes a round left with undelivered matches (a pod killed
mid-delivery, Slack unavailable) rather than messaging everyone twice.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from slack_sdk import WebClient

from src.core.scheduler import JobSpec
from src.core.timezones import canonical_tz
from src.modules.connect import blocks as cblocks
from src.modules.connect import slack_api as api
from src.modules.connect.matcher import match
from src.modules.connect.rounds import _as_date, is_round_due

logger = logging.getLogger(__name__)

NUDGE_AFTER_DAYS = 3
CLOSE_AFTER_DAYS = 6
MIN_POOL = 2

# How often each workspace's follow-ups are checked. Five minutes is well
# inside the precision a "three days later" message needs.
FOLLOWUP_SWEEP_MINUTES = 5
# A claimed follow-up is left alone this long before another sweep may retry
# it, so a pod that died mid-send does not strand it.
FOLLOWUP_LEASE_MINUTES = 15
FOLLOWUP_MAX_ATTEMPTS = 5
# A follow-up this far past its due time is dropped rather than sent. A nudge
# more than a day late lands next to the closing question, and "did you meet?"
# days after the round ended reads as noise. This is also what the first sweep
# after this release does with rounds the old in-memory jobs left open: old
# ones close quietly instead of messaging every old group DM at once. Skipping
# a close still marks the round closed, without the stats post.
FOLLOWUP_STALE_AFTER = {"nudge": timedelta(days=1), "close": timedelta(days=3)}
# A missed round is started this long after its time at the earliest. Longer
# than the scheduler's misfire grace, so the cron firing, which may start up
# to five minutes late, is not raced by the catch-up.
CATCHUP_AFTER_MINUTES = 10
# A pod delivering a round renews its lease after every match, so a lease this
# old means the pod died. Long enough to cover one match's rate limit waits.
DELIVERY_LEASE_MINUTES = 10
# Matches still undelivered this long after the round's time are left alone:
# an introduction a day late is still useful, one after the nudge is not.
RESUME_DELIVERY_WITHIN_HOURS = 24


def plan_jobs(ctx: dict) -> list[JobSpec]:
    """One weekly trigger per programme for this workspace.

    Weekly rather than every-N-weeks because cron cannot express the latter
    cleanly; the job body decides whether today is a round day.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    team_id = ctx["team_id"]
    # The follow-up sweep is planned for every workspace with Connect active,
    # with or without a programme: a round from a programme paused since still
    # gets its nudge and closing question. Being planned here is also what
    # keeps it through module job reconciliation.
    jobs: list[JobSpec] = [
        JobSpec(
            key="followups",
            trigger=IntervalTrigger(minutes=FOLLOWUP_SWEEP_MINUTES, jitter=60),
            func=send_due_followups,
            args=(team_id,),
        )
    ]
    # A failed read raises rather than returning the sweep alone: module job
    # sync keeps a workspace's live jobs when its plan raises, but would
    # delete the round jobs missing from a partial plan.
    programs = [p for p in cdb.active_programs() if p["team_id"] == team_id]

    for p in programs:
        # One programme with an unusable timezone must not drop the other
        # programmes' rounds or this workspace's follow-up sweep.
        try:
            trigger = CronTrigger(
                day_of_week=int(p["day_of_week"]),
                hour=int(p["hour"]),
                minute=int(p["minute"]),
                timezone=canonical_tz(p["timezone"] or "UTC"),
            )
        except Exception:
            logger.exception("connect could not build a trigger for program %s (tz %r)", p["id"], p.get("timezone"))
            continue
        jobs.append(
            JobSpec(
                key=f"round:{p['id']}",
                trigger=trigger,
                func=run_round,
                # No token: bot tokens rotate every 12 hours and reconciliation
                # used to keep a job's args for as long as the job lived, so a
                # week later the round ran on an expired token and was skipped.
                args=(p["id"],),
            )
        )
    if programs:
        jobs.append(
            JobSpec(
                key="catchup",
                trigger=IntervalTrigger(minutes=FOLLOWUP_SWEEP_MINUTES, jitter=60),
                func=start_missed_rounds,
                args=(team_id,),
            )
        )
    return jobs


def _client(bot_token: str, team_id: str) -> WebClient | None:
    """A client on the installation's current token, refreshed if near expiry.

    The token passed in is only a fallback for when the database cannot be
    read. Preferring it would bring back the stale token bug for any caller
    still holding an old one.
    """
    try:
        from src.core.scheduler import _fresh_bot_token  # noqa: PLC0415

        token = _fresh_bot_token(team_id, bot_token)
    except Exception:
        token = bot_token
    return WebClient(token=token) if token else None


def run_round(program_id: int, bot_token: str = "", force: bool = False) -> None:
    """Start today's round: build the pool, match, then deliver.

    `bot_token` is kept so jobs planned before tokens were dropped from the
    args still run; the installation's current token is used whenever it can
    be read.

    `force` runs a round that is not due, for the "run it now" button. Everything
    after the cadence check is unchanged, so a forced round is an ordinary round
    in every other respect: same matching, same history, same idempotency guard
    on (programme, scheduled_for), which is what stops a second click producing
    a second set of introductions on the same day.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415
    from src.core.roster import eligible_members  # noqa: PLC0415

    program = cdb.get_program(program_id)
    if not program or not program.get("enabled"):
        return

    # The programme's calendar day, not the server's: the cron fires in the
    # programme's timezone and the same-day guard in create_round uses it too.
    try:
        today = datetime.now(ZoneInfo(program.get("timezone") or "UTC")).date()
    except (ZoneInfoNotFoundError, ValueError):
        today = date.today()
    # Manual rounds are extras, so the cadence counts scheduled rounds only.
    if not force and not is_round_due(
        program["interval_weeks"], program.get("last_scheduled_round"), today, program.get("next_round_date")
    ):
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
    round_row = cdb.create_round(program_id, team_id, scheduled_for, manual=force)
    if round_row is None:
        logger.info("connect: a round already exists for programme %s today", program_id)
        return

    # Only when the programme asks for it: a team spread across distant zones
    # shares no working day at all, and enforcing it by default would stop
    # matching them entirely.
    zones = _member_timezones(team_id) if program.get("match_working_hours") else {}
    groups = match(
        pool,
        cdb.pair_history(program_id),
        seed=round_row["id"],
        current_round=round_row["id"],
        timezones=zones,
        minimum_overlap_hours=1.0 if program.get("match_working_hours") else 0.0,
        group_size=int(program.get("group_size") or 2),
        strict_group_size=bool(program.get("strict_group_size")),
    )
    if not groups:
        cdb.set_round_state(round_row["id"], "closed", 0)
        return

    cdb.create_matches(round_row["id"], team_id, groups)
    cdb.record_pairs(program_id, round_row["id"], groups)

    from src.core.analytics import capture  # noqa: PLC0415

    capture("coffee_match_created", team_id, matches=len(groups), participants=len(pool))
    cdb.set_round_state(round_row["id"], "matched", len(pool))
    # A pinned date is the next scheduled round; a manual extra leaves it in place.
    if program.get("next_round_date") and not force:
        try:
            cdb.update_program(team_id, program_id, next_round_date=None)
        except Exception:
            logger.warning("connect: could not clear the pinned date on programme %s", program_id)

    deliver_round(round_row["id"], bot_token, team_id, program_id)
    _queue_followups(round_row["id"], team_id)


def _member_timezones(team_id: str) -> dict[str, str]:
    """user_id -> timezone, for working-hours decisions."""
    try:
        from src.core.roster import eligible_members  # noqa: PLC0415

        return {m.user_id: (getattr(m, "tz", "") or "") for m in eligible_members(team_id)}
    except Exception:
        logger.info("connect: no timezones available, times will not be suggested")
        return {}


def _suggest_times(members: list[str], zones: dict[str, str], minutes: int, meeting_link: str = "") -> list[dict]:
    """Hours inside everyone's working day, each with a calendar link.

    Only offered for a pair: with three people the overlap is usually empty and
    a wrong suggestion is worse than none.
    """
    if len(members) != 2:
        return []
    try:
        from src.modules.connect.calendar import google_link  # noqa: PLC0415
        from src.modules.connect.hours import local_label, next_slots, within_working_hours  # noqa: PLC0415

        slots = next_slots(zones.get(members[0], ""), zones.get(members[1], ""), 3, minutes)
        outside = not within_working_hours(zones.get(members[0], ""), zones.get(members[1], ""))
        tz_names = [zones.get(m, "") for m in members]
        return [
            {
                "outside_hours": outside,
                # Both readers' own clocks. A UTC time is one neither of them
                # thinks in, and tells them nothing about whether the slot is
                # their morning or their evening.
                "label": local_label(slot, tz_names),
                "utc": slot.replace(microsecond=0).isoformat(),
                "add_url": google_link(
                    slot,
                    minutes,
                    "Coffee chat",
                    "Your Morgenruf coffee chat.",
                    meeting_link,
                ),
            }
            for slot in slots
        ]
    except Exception:
        logger.info("connect: could not suggest times")
        return []


def deliver_round(round_id: int, bot_token: str, team_id: str, program_id: int) -> bool:
    """Open a group DM per match and introduce people.

    Each match is marked delivered as it succeeds, so an interruption resumes
    instead of re-messaging anyone. Only one pod delivers a round at a time
    (the delivery lease), because the sweep that resumes an interrupted round
    runs on every pod. Returns True when no match is left undelivered.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    client = _client(bot_token, team_id)
    if client is None:
        return False
    if not cdb.claim_round_delivery(round_id, DELIVERY_LEASE_MINUTES):
        logger.info("connect: round %s is being delivered elsewhere", round_id)
        return False
    try:
        return _deliver_matches(client, round_id, team_id, program_id)
    finally:
        try:
            cdb.release_round_delivery(round_id)
        except Exception:
            # The lease runs out on its own; this only frees it sooner.
            logger.warning("connect: could not release delivery of round %s", round_id)


def _deliver_matches(client, round_id: int, team_id: str, program_id: int) -> bool:  # noqa: ANN001
    import src.modules.connect.db as cdb  # noqa: PLC0415

    program = cdb.get_program(program_id) or {}
    # "How they meet" decides whether the shared room appears at all. It saved
    # and did nothing until now: a programme set to Zoom or to "they sort it
    # out" still had its meeting_link pasted into every introduction.
    video_mode = str(program.get("video_mode") or "link")
    meeting_link = (program.get("meeting_link") or "") if video_mode == "link" else ""
    meeting_minutes = int(program.get("meeting_minutes") or 30)
    # Both default on, so a programme predating these columns behaves as before.
    want_times = program.get("suggest_times", True) is not False
    want_icebreaker = program.get("use_icebreaker", True) is not False
    # Reading timezones is only worth it if the times are going to be offered.
    zones = _member_timezones(team_id) if want_times else {}

    pending = cdb.undelivered_matches(round_id)
    for m in pending:
        try:
            members = list(m["member_ids"])
            channel = api.open_group_dm(client, members)
            text, blocks = cblocks.intro_message(
                members,
                cblocks.random_seed_for(round_id, m["id"]),
                program_id,
                meeting_link=meeting_link,
                meeting_minutes=meeting_minutes,
                suggested_times=(
                    times := (_suggest_times(members, zones, meeting_minutes, meeting_link) if want_times else [])
                ),
                times_are_outside_hours=bool(times and times[0].get("outside_hours")),
                with_icebreaker=want_icebreaker,
                # The accept buttons carry the match, so the message needs it.
                match_id=m["id"],
                tone=str(program.get("intro_tone") or "hybrid"),
            )
            api.post(client, channel, text, blocks)
            if video_mode == "zoom":
                _offer_zoom(client, channel, team_id, members)
            cdb.mark_delivered(m["id"], channel)
        except api.PermanentSlackError as exc:
            # A deactivated member or a lost scope will not fix itself on
            # retry; mark it done so the round can finish.
            logger.warning("connect: match %s undeliverable (%s)", m["id"], exc)
            cdb.mark_delivered(m["id"], "")
        except Exception:
            # Left undelivered; the follow-up sweep retries it.
            logger.exception("connect: delivery failed for match %s, will retry", m["id"])
        finally:
            api.throttle()
            try:
                cdb.renew_round_delivery(round_id)
            except Exception:
                logger.warning("connect: could not renew delivery lease for round %s", round_id)

    if cdb.undelivered_matches(round_id):
        # Not "delivered" yet: the round stays resumable.
        return False
    cdb.set_round_state(round_id, "delivered")
    return True


def resume_undelivered_rounds(team_id: str) -> int:
    """Finish delivering recent rounds that were interrupted. Returns how many finished.

    deliver_round used to run only from run_round, and the same-day guard
    stops the catch-up from starting that round again, so a pod killed
    halfway through a delivery left the rest of the pairs unintroduced.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    try:
        rounds = cdb.rounds_with_undelivered(team_id, RESUME_DELIVERY_WITHIN_HOURS)
    except Exception:
        logger.exception("connect: could not look for undelivered rounds in %s", team_id)
        return 0
    finished = 0
    for r in rounds:
        try:
            logger.info("connect: resuming delivery of round %s", r["id"])
            if deliver_round(r["id"], "", team_id, r["program_id"]):
                finished += 1
        except Exception:
            logger.exception("connect: resuming round %s failed", r["id"])
    return finished


def nudge_round(round_id: int, bot_token: str, team_id: str) -> bool:
    """One reminder to the pairs who have not spoken. Never more than one.

    Returns False when some match was not handled (no usable token, or a
    failed post), so the caller retries. A retry only reaches the matches
    still without nudged_at, so nobody is nudged twice.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    client = _client(bot_token, team_id)
    if client is None:
        logger.warning("connect: no usable token to nudge round %s", round_id)
        return False
    done = True
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
            done = False
        finally:
            api.throttle()
    return done


def close_round(round_id: int, bot_token: str, team_id: str) -> bool:
    """Ask whether they met. That answer is the only metric worth having.

    Returns False when the round was not closed (no usable token), so the
    caller retries. A failed post for one match does not count: nothing
    records which matches were asked, so a retry would ask the others twice.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    client = _client(bot_token, team_id)
    if client is None:
        logger.warning("connect: no usable token to close round %s", round_id)
        return False
    for m in cdb.matches_for_close(round_id):
        try:
            text, blocks = cblocks.did_you_meet_message(m["id"])
            api.post(client, m["mpim_channel_id"], text, blocks)
        except Exception:
            logger.exception("connect: close prompt failed for match %s", m["id"])
        finally:
            api.throttle()
    cdb.set_round_state(round_id, "closed")
    _post_round_stats(client, round_id, team_id)
    return True


def _post_round_stats(client, round_id: int, team_id: str) -> None:
    """Post how the round went to the channel, when the programme asks for it.

    After closing rather than before: the check-in replies are what makes the
    number mean anything, and they only exist once the closing question has
    been out for a while.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415
    from src.modules.connect import blocks as cblocks  # noqa: PLC0415

    try:
        program = cdb.program_for_round(round_id) or {}
        if not program.get("post_stats"):
            return
        rounds = cdb.recent_rounds(team_id, program["id"], limit=20)
        row = next((r for r in rounds if r["id"] == round_id), None)
        if not row:
            return
        met, missed = int(row["met"]), int(row["missed"])
        text, blocks = cblocks.round_stats_message(met, met + missed, int(row["matches"]))
        api.post(client, program["channel_id"], text, blocks)
    except Exception:
        # A missing stats post must never be the reason a round fails to close.
        logger.exception("connect: could not post round stats for %s", round_id)


def _queue_followups(round_id: int, team_id: str) -> None:
    """Store this round's nudge and closing question for the sweep to send.

    A failure here costs nothing permanent: the sweep creates missing rows for
    every open round on each pass.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    try:
        cdb.queue_followups(team_id, NUDGE_AFTER_DAYS, CLOSE_AFTER_DAYS, round_id=round_id)
    except Exception:
        logger.exception("connect: could not queue follow-ups for round %s, the sweep will add them", round_id)


class _FollowupNotDone(Exception):
    """The sender ran but reported the follow-up was not done."""


def send_due_followups(team_id: str) -> int:
    """Send this workspace's due nudges and closing questions.

    Returns how many were finished (sent or skipped). Safe to run on several
    pods at once and as often as wanted: rows are claimed atomically before
    anything is sent, and a finished row is never taken again. The token is
    read from the installation each time rather than stored in the job, so a
    rotated token is picked up.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    resume_undelivered_rounds(team_id)
    try:
        cdb.queue_followups(team_id, NUDGE_AFTER_DAYS, CLOSE_AFTER_DAYS)
    except Exception:
        logger.exception("connect: could not backfill follow-ups for %s", team_id)
    try:
        due = cdb.claim_due_followups(team_id, FOLLOWUP_LEASE_MINUTES)
    except Exception:
        logger.exception("connect: could not claim follow-ups for %s", team_id)
        return 0

    finished = 0
    now = datetime.now(timezone.utc)
    for f in due:
        round_id, kind = f["round_id"], f["kind"]
        try:
            if now - f["due_at"] > FOLLOWUP_STALE_AFTER[kind]:
                logger.info("connect: %s for round %s is too late to send, skipping", kind, round_id)
                if kind == "close":
                    cdb.set_round_state(round_id, "closed")
                cdb.finish_followup(round_id, kind, "skipped_stale")
            else:
                send = nudge_round if kind == "nudge" else close_round
                if not send(round_id, "", team_id):
                    # Not an error to log with a traceback, but not done either:
                    # recording it as sent would hide a round that never closed.
                    raise _FollowupNotDone(f"{kind} for round {round_id} did not complete")
                cdb.finish_followup(round_id, kind, "sent")
            finished += 1
        except Exception:
            logger.exception("connect: %s for round %s failed (attempt %s)", kind, round_id, f.get("attempts"))
            # Left claimed, so it is retried once the lease runs out, up to a
            # limit, after which it is recorded as failed rather than sent.
            if int(f.get("attempts") or 0) >= FOLLOWUP_MAX_ATTEMPTS:
                try:
                    cdb.finish_followup(round_id, kind, "failed")
                except Exception:
                    logger.exception("connect: could not give up on %s for round %s", kind, round_id)
    return finished


def start_missed_rounds(team_id: str) -> int:
    """Start any round whose weekly firing was missed earlier today.

    The weekly cron firing is the only thing that starts a scheduled round, so
    a pod that was down at that minute, a firing dropped as a misfire, or a
    token error cost the whole week. This runs on the follow-up interval and
    starts the round later the same day instead.

    Only on the programme's weekday in its own timezone, and only once its
    time (plus a margin for the cron firing itself) has passed, so a round is
    never started on a day the programme does not run on. run_round checks the
    cadence again, and create_round's same-day guard means a round that did
    start is never started twice. Returns how many rounds it tried to start.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    try:
        programs = [p for p in cdb.get_programs(team_id) if p.get("enabled")]
    except Exception:
        logger.exception("connect: could not read programmes for %s to catch up", team_id)
        return 0

    now = datetime.now(timezone.utc)
    tried = 0
    for p in programs:
        try:
            if not _round_missed_today(p, now):
                continue
            logger.info("connect: programme %s missed its round today, starting it now", p["id"])
            tried += 1
            run_round(p["id"])
        except Exception:
            logger.exception("connect: catch-up round for programme %s failed", p.get("id"))
    return tried


def _round_missed_today(program: dict, now: datetime) -> bool:
    """Whether today is this programme's round day, its time has passed, and no
    scheduled round has run yet."""
    try:
        local = now.astimezone(ZoneInfo(program.get("timezone") or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        return False
    if local.weekday() != int(program["day_of_week"]):
        return False
    scheduled = local.replace(hour=int(program["hour"]), minute=int(program["minute"]), second=0, microsecond=0)
    if local < scheduled + timedelta(minutes=CATCHUP_AFTER_MINUTES):
        return False
    # A programme set up after today's time gets its first round next week,
    # which is what the dashboard told whoever created it.
    created = program.get("created_at")
    if getattr(created, "tzinfo", None) is not None and created > scheduled:
        return False
    return is_round_due(
        program.get("interval_weeks") or 1,
        _as_date(program.get("last_scheduled_round")),
        local.date(),
        _as_date(program.get("next_round_date")),
    )


def _offer_zoom(client, channel: str, team_id: str, members: list) -> None:
    """Offer Zoom linking to the people in this match who have not linked.

    Ephemeral, and only to those who need it: the person who already linked
    should not be shown an upsell, and neither should see the other's. Failing
    here must never cost the introduction, which has already been delivered.
    """
    try:
        import src.modules.connect.db as cdb  # noqa: PLC0415
        from src.modules.connect import zoom  # noqa: PLC0415
        from src.modules.connect.blocks import zoom_offer_blocks  # noqa: PLC0415
        from src.modules.connect.zoom_routes import mint_link_token  # noqa: PLC0415

        if not zoom.configured():
            return
        linked = set(cdb.zoom_linked_user_ids(team_id, members))
        base = (os.environ.get("APP_URL") or "").rstrip("/")
        for user_id in members:
            if user_id in linked:
                continue
            url = f"{base}/connect/zoom/start?t={mint_link_token(team_id, user_id)}"
            client.chat_postEphemeral(
                channel=channel, user=user_id, blocks=zoom_offer_blocks(url), text="Meet over Zoom"
            )
    except Exception:
        logger.info("connect: could not offer Zoom linking in %s", channel)
