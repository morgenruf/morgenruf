"""Scheduler — per-workspace standup cron jobs backed by PostgreSQL config."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from slack_sdk import WebClient
from state import state_store

# Refresh bot tokens this many seconds before their stated expiry.
_TOKEN_REFRESH_LEEWAY_SECS = 15 * 60

# Error substrings Slack returns when a bot token is no longer usable.
_AUTH_ERROR_MARKERS = ("token_expired", "invalid_auth", "token_revoked", "not_authed")

logger = logging.getLogger(__name__)

# Module-level scheduler reference so oauth.py can access it after startup
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler


def _refresh_bot_token_if_needed(team_id: str, inst: dict) -> str | None:
    """Proactively refresh an expiring/expired bot token via oauth.v2.access.

    Returns the new bot_token on success, None if refresh wasn't possible/needed.
    """
    refresh_token = inst.get("bot_refresh_token")
    expires_at = inst.get("bot_token_expires_at")
    if not refresh_token or not expires_at:
        return None
    try:
        if isinstance(expires_at, datetime):
            expiry_epoch = expires_at.timestamp()
        else:
            expiry_epoch = float(expires_at)
    except Exception:
        return None
    if expiry_epoch - time.time() > _TOKEN_REFRESH_LEEWAY_SECS:
        return None

    client_id = os.environ.get("SLACK_CLIENT_ID", "")
    client_secret = os.environ.get("SLACK_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("Cannot refresh bot token for %s: SLACK_CLIENT_ID/SECRET missing", team_id)
        return None

    try:
        resp = WebClient().oauth_v2_access(
            client_id=client_id,
            client_secret=client_secret,
            grant_type="refresh_token",
            refresh_token=refresh_token,
        )
    except Exception as exc:
        logger.warning("Token refresh failed for team %s: %s", team_id, exc)
        return None

    new_token = resp.get("access_token")
    new_refresh = resp.get("refresh_token") or refresh_token
    expires_in = int(resp.get("expires_in") or 0)
    if not new_token:
        return None

    new_expires_at = (
        datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc).isoformat() if expires_in > 0 else None
    )
    try:
        import db  # noqa: PLC0415

        db.save_installation(
            team_id=team_id,
            team_name=inst.get("team_name") or "",
            bot_token=new_token,
            bot_user_id=inst.get("bot_user_id") or "",
            app_id=inst.get("app_id") or "",
            installed_by_user_id=inst.get("installed_by_user_id"),
            bot_refresh_token=new_refresh,
            bot_token_expires_at=new_expires_at,
        )
        logger.info("Refreshed bot token for team %s (expires in %ss)", team_id, expires_in)
    except Exception as exc:
        logger.warning("Refreshed bot token but failed to persist for %s: %s", team_id, exc)
    return new_token


def _fresh_bot_token(team_id: str, fallback_token: str) -> str:
    """Return the latest bot_token from the DB, refreshing via OAuth if near/past expiry."""
    try:
        import db  # noqa: PLC0415

        inst = db.get_installation(team_id)
        if inst:
            refreshed = _refresh_bot_token_if_needed(team_id, inst)
            if refreshed:
                return refreshed
            if inst.get("bot_token"):
                return inst["bot_token"]
    except Exception:
        pass
    return fallback_token


def _is_auth_error(exc: Exception) -> bool:
    """True if a Slack API exception looks like an auth/token failure."""
    msg = str(exc).lower()
    return any(marker in msg for marker in _AUTH_ERROR_MARKERS)


def _force_refresh_bot_token(team_id: str) -> str | None:
    """Force a refresh regardless of stored expiry. Returns new bot_token or None."""
    try:
        import db  # noqa: PLC0415

        inst = db.get_installation(team_id)
        if not inst:
            return None
        inst = dict(inst)
        # Lie about the expiry so _refresh_bot_token_if_needed always fires.
        inst["bot_token_expires_at"] = datetime.now(tz=timezone.utc)
        return _refresh_bot_token_if_needed(team_id, inst)
    except Exception as exc:
        logger.warning("Force refresh failed for %s: %s", team_id, exc)
        return None


def _alert_token_refresh_failure(team_id: str, reason: str) -> None:
    """Loud alert when a refresh attempt fails — workspace likely needs to reinstall."""
    logger.error(
        "TOKEN_REFRESH_FAILURE team=%s reason=%s — workspace may need to reinstall Morgenruf",
        team_id,
        reason,
    )
    ops_email = os.environ.get("MORGENRUF_OPS_EMAIL", "").strip()
    if not ops_email:
        return
    try:
        import resend  # type: ignore[import]  # noqa: PLC0415
    except ImportError:
        return
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return
    try:
        resend.api_key = api_key
        resend.Emails.send(
            {
                "from": "alerts@morgenruf.dev",
                "to": ops_email,
                "subject": f"[Morgenruf] Token refresh failed for team {team_id}",
                "html": (
                    f"<p>Bot-token refresh failed for team <code>{team_id}</code>.</p>"
                    f"<p><b>Reason:</b> {reason}</p>"
                    "<p>Scheduled standups for this workspace will fail until the workspace reinstalls Morgenruf.</p>"
                ),
            }
        )
    except Exception as exc:
        logger.warning("Failed to send ops alert email for %s: %s", team_id, exc)


def _call_with_auth_retry(team_id: str, client: WebClient, func):
    """Invoke func(client); on auth error, refresh the token and retry once with the same client.

    The retry mutates `client.token` in place so follow-on calls from the caller also benefit.
    """
    try:
        return func(client)
    except Exception as exc:
        if not _is_auth_error(exc):
            raise
        new_token = _force_refresh_bot_token(team_id)
        if not new_token:
            _alert_token_refresh_failure(team_id, str(exc))
            raise
        client.token = new_token
        return func(client)


def _schedule_standup_retry(
    team_id: str, bot_token: str, channel_id: str, schedule_id: int | None, delay_seconds: int = 60
) -> None:
    """Enqueue a one-shot retry of a failed standup run after the token has been refreshed."""
    if _scheduler is None:
        return
    retry_id = f"standup_retry_{team_id}_{schedule_id or 'workspace'}_{int(time.time())}"
    try:
        _scheduler.add_job(
            _send_standup_to_workspace,
            trigger=DateTrigger(run_date=datetime.now(tz=timezone.utc) + timedelta(seconds=delay_seconds)),
            args=[team_id, bot_token, channel_id, schedule_id],
            id=retry_id,
            name=f"Retry standup — {team_id}/{schedule_id or 'workspace'}",
            replace_existing=False,
        )
        logger.info("Queued retry for standup %s/%s in %ss", team_id, schedule_id, delay_seconds)
    except Exception as exc:
        logger.warning("Could not queue standup retry for %s/%s: %s", team_id, schedule_id, exc)


def _refresh_all_tokens_job() -> None:
    """Background job: refresh any bot tokens nearing expiry across all installations."""
    try:
        import db  # noqa: PLC0415

        installations = db.get_all_installations()
    except Exception as exc:
        logger.warning("Background token refresh: could not load installations: %s", exc)
        return
    refreshed = 0
    for inst in installations:
        team_id = inst.get("team_id")
        if not team_id:
            continue
        try:
            if _refresh_bot_token_if_needed(team_id, inst):
                refreshed += 1
        except Exception as exc:
            logger.warning("Background token refresh for %s failed: %s", team_id, exc)
    if refreshed:
        logger.info("Background token refresh: refreshed %d token(s)", refreshed)


def _slack_dm_with_retry(
    client: WebClient,
    user_id: str,
    max_retries: int = 2,
    team_id: str | None = None,
    **msg_kwargs,
) -> bool:
    """Open a DM and send a message, retrying on transient failures. Returns True on success.

    If `team_id` is provided, a Slack auth error (expired/invalid token) triggers a single
    force-refresh of the bot token and an immediate retry with the new token.
    """
    auth_refresh_tried = False
    for attempt in range(max_retries + 1):
        try:
            dm = client.conversations_open(users=user_id)
            dm_channel = dm["channel"]["id"]
            client.chat_postMessage(channel=dm_channel, **msg_kwargs)
            return True
        except Exception as exc:
            # Reactive token refresh on auth error — try once, then retry the same attempt.
            if team_id and not auth_refresh_tried and _is_auth_error(exc):
                auth_refresh_tried = True
                new_token = _force_refresh_bot_token(team_id)
                if new_token:
                    client.token = new_token
                    continue  # retry without burning an attempt
                _alert_token_refresh_failure(team_id, str(exc))
                raise
            if attempt == max_retries:
                raise
            time.sleep(1.5**attempt)  # 1s, 1.5s
    return False


def _notify_delivery_failure(client: WebClient, channel_id: str, failed_count: int, total_count: int) -> None:
    """Post a warning to the standup channel when DM delivery fails."""
    if not channel_id or failed_count == 0:
        return
    try:
        client.chat_postMessage(
            channel=channel_id,
            text=(
                f"⚠️ *Standup delivery issue:* Failed to send standup DMs to {failed_count}/{total_count} members. "
                "This is usually a temporary Slack API issue — standups will retry on the next scheduled run."
            ),
        )
    except Exception as exc:
        logger.warning("Could not post delivery failure notice to %s: %s", channel_id, exc)


def _send_standup_to_workspace(team_id: str, bot_token: str, channel_id: str, schedule_id: int | None = None) -> None:
    """DM participants of a standup schedule (or all active members if no schedule)."""
    bot_token = _fresh_bot_token(team_id, bot_token)
    try:
        import db  # noqa: PLC0415

        if schedule_id:
            schedule = db.get_standup_schedule(team_id, schedule_id)
            if not schedule or not schedule.get("active"):
                logger.info("Schedule %s inactive, skipping", schedule_id)
                return
            questions_raw = schedule.get("questions") or []
            if isinstance(questions_raw, str):
                import json as _json

                try:
                    questions_raw = _json.loads(questions_raw)
                except Exception:
                    questions_raw = []
            questions = questions_raw if questions_raw else None
            participants_filter = schedule.get("participants") or []
            channel_id = schedule.get("channel_id") or channel_id
            standup_name = schedule.get("name", "Team Standup")
        else:
            config = db.get_workspace_config(team_id) or {}
            qs = config.get("questions") or []
            if isinstance(qs, str):
                import json as _json

                try:
                    qs = _json.loads(qs)
                except Exception:
                    qs = []
            questions = qs if qs else None
            participants_filter = []
            standup_name = config.get("standup_name", "Team Standup")

        members = db.get_active_members(team_id)
        if participants_filter:
            members = [m for m in members if m["user_id"] in participants_filter]
    except Exception as exc:
        logger.error("Could not load data for standup %s/%s: %s", team_id, schedule_id, exc)
        return

    logger.info("Triggering standup for team %s (%d members)", team_id, len(members))

    # Verify bot token is still valid before DMing members. If the token is stale,
    # force-refresh once and retry with the new token before giving up.
    client = WebClient(token=bot_token)
    try:
        _call_with_auth_retry(team_id, client, lambda c: c.auth_test())
    except Exception as exc:
        logger.error("Bot token invalid for team %s — skipping standup: %s", team_id, exc)
        _schedule_standup_retry(team_id, bot_token, channel_id, schedule_id)
        return
    bot_token = client.token  # pick up any refreshed token

    # Channel member sync: auto-add/remove participants based on Slack channel membership
    if schedule_id and channel_id:
        try:
            schedule = db.get_standup_schedule(team_id, schedule_id)
            if schedule and schedule.get("sync_with_channel"):
                channel_members = set()
                cursor = None
                while True:
                    resp = client.conversations_members(channel=channel_id, limit=500, cursor=cursor or "")
                    channel_members.update(resp.get("members", []))
                    cursor = resp.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
                # Filter out bots by checking each user (cached per team)
                for uid in channel_members:
                    try:
                        db.upsert_member(team_id, uid)
                    except Exception:
                        pass
                # Update participants list to match channel
                if channel_members:
                    db.update_standup_schedule(
                        team_id,
                        schedule_id,
                        participants=list(channel_members),
                    )
                    members = db.get_active_members(team_id)
                    members = [m for m in members if m["user_id"] in channel_members]
                logger.info("Synced %d channel members for schedule %s", len(channel_members), schedule_id)
        except Exception as exc:
            logger.warning("Channel member sync failed for %s/%s: %s", team_id, schedule_id, exc)

    failed_count = 0
    dm_count = 0
    for member in members:
        user_id = member["user_id"]
        cache_key = f"{team_id}:{user_id}"
        try:
            if state_store.is_active(cache_key):
                logger.debug("Skipping %s — already has active session", user_id)
                continue

            # Check if user skipped today
            try:
                import db  # noqa: PLC0415

                if db.is_skipped_today(team_id, user_id):
                    logger.debug("Skipping %s — user opted out today", user_id)
                    continue
            except Exception as e:
                logger.warning(
                    "Unexpected error in _send_standup_to_workspace checking skip status for %s: %s", user_id, e
                )

            try:
                import db  # noqa: PLC0415

                if db.is_on_vacation(team_id, user_id):
                    logger.debug("Skipping %s — on vacation", user_id)
                    continue
            except Exception as e:
                logger.warning(
                    "Unexpected error in _send_standup_to_workspace checking vacation for %s: %s", user_id, e
                )

            dm_count += 1

            # Send DM first — only start session if delivery succeeds
            from blocks import standup_dm_message  # noqa: PLC0415

            default_questions = questions or [
                "What did you complete yesterday?",
                "What are you working on today?",
                "Any blockers?",
            ]
            dm_msg = standup_dm_message(default_questions, standup_name)
            _slack_dm_with_retry(
                client, user_id, team_id=team_id, text=f"🌅 Time for your standup! — {standup_name}", **dm_msg
            )

            state_store.start(cache_key, channel_id, team_id=team_id, questions=questions, standup_name=standup_name)
            logger.info("Sent standup DM to %s / %s", team_id, user_id)
        except Exception as exc:
            failed_count += 1
            logger.error("Failed to DM %s / %s: %s", team_id, user_id, exc)

    if failed_count > 0:
        _notify_delivery_failure(client, channel_id, failed_count, dm_count)


def _send_reminder_to_workspace(
    team_id: str, bot_token: str, reminder_minutes: int, schedule_id: int | None = None
) -> None:
    """DM active members a heads-up before standup time."""
    bot_token = _fresh_bot_token(team_id, bot_token)
    try:
        import db  # noqa: PLC0415

        members = db.get_active_members(team_id)
        standup_label: str | None = None

        # Filter to schedule participants if this is a schedule-specific reminder
        if schedule_id is not None:
            sched = db.get_standup_schedule(team_id, schedule_id)
            if sched:
                # Prefer the schedule's display name; fall back to channel + time
                # so the reminder is always identifiable when a user belongs to
                # multiple schedules.
                name = (sched.get("name") or "").strip()
                if name:
                    standup_label = name
                else:
                    chan = sched.get("channel_id") or ""
                    when = sched.get("schedule_time") or ""
                    parts = []
                    if chan:
                        parts.append(f"<#{chan}>")
                    if when:
                        parts.append(f"at {when}")
                    if parts:
                        standup_label = " ".join(parts)
                participants = sched.get("participants") or []
                if participants:
                    participant_set = set(participants)
                    members = [m for m in members if m["user_id"] in participant_set]
    except Exception as exc:
        logger.error("Could not load members for reminder %s: %s", team_id, exc)
        return
    client = WebClient(token=bot_token)
    for member in members:
        user_id = member["user_id"]
        try:
            import db  # noqa: PLC0415

            if db.is_skipped_today(team_id, user_id):
                continue
            label = f" for *{standup_label}*" if standup_label else ""
            _slack_dm_with_retry(
                client,
                user_id,
                team_id=team_id,
                text=f"⏰ Standup{label} starts in *{reminder_minutes} minutes*. Get ready! 🚀",
            )
        except Exception as exc:
            logger.warning("Failed reminder DM to %s / %s: %s", team_id, user_id, exc)

    # Evaluate low_participation workflow rules
    try:
        import db  # noqa: PLC0415
        from workflow import evaluate_rules  # noqa: PLC0415

        stats = db.get_participation_stats(team_id, days=1)
        total = len(stats)
        responded = sum(1 for s in stats if (s.get("responses") or 0) > 0)
        pct = int((responded / total * 100) if total else 100)
        evaluate_rules(team_id, "low_participation", {"participation_pct": pct, "team": team_id}, client)
    except Exception as exc:
        logger.warning("Participation workflow rules failed for %s: %s", team_id, exc)


def _send_weekly_digest(team_id: str, bot_token: str) -> None:
    """Send a weekly summary email to the workspace admin."""
    try:
        import db  # noqa: PLC0415
        from mailer import send_weekly_digest  # noqa: PLC0415

        inst = db.get_installation(team_id)
        if not inst:
            return
        stats = db.get_dashboard_stats(team_id)
        participation = db.get_participation_stats(team_id, days=7)
        email = db.get_member_email(team_id, inst.get("installed_by_user_id", "")) or ""
        send_weekly_digest(
            to_email=email,
            team_name=inst.get("team_name", team_id),
            stats=stats,
            participation=participation,
        )
    except Exception as exc:
        logger.warning("Weekly digest failed for %s: %s", team_id, exc)


def _send_manager_digest(team_id: str) -> None:
    """Send today's standup digest to the configured manager email (if enabled)."""
    try:
        import db  # noqa: PLC0415
        from mailer import send_manager_digest  # noqa: PLC0415

        config = db.get_workspace_config(team_id)
        if not config:
            return
        if not config.get("manager_digest_enabled"):
            return
        manager_email = config.get("manager_email") or ""
        if not manager_email:
            return
        inst = db.get_installation(team_id)
        workspace_name = inst.get("team_name", team_id) if inst else team_id
        standups = db.get_standups(team_id, days=1)
        date_str = datetime.now().strftime("%Y-%m-%d")
        send_manager_digest(
            manager_email=manager_email,
            workspace_name=workspace_name,
            standups=standups,
            date_str=date_str,
        )
    except Exception as exc:
        logger.warning("Manager digest failed for %s: %s", team_id, exc)


def _post_scheduled_report(team_id: str, bot_token: str, channel_id: str, schedule_id: int | None = None) -> None:
    """Post the standup report at the scheduled report_time, regardless of completion."""
    bot_token = _fresh_bot_token(team_id, bot_token)
    try:
        import json as _json

        import db  # noqa: PLC0415

        today_standups = db.get_today_standups(team_id)
        if not today_standups:
            logger.info("No submissions for team %s — skipping report", team_id)
            return

        client = WebClient(token=bot_token)
        try:
            _call_with_auth_retry(team_id, client, lambda c: c.auth_test())
        except Exception as exc:
            logger.error("Bot token invalid for report %s: %s", team_id, exc)
            return
        bot_token = client.token

        sched_cfg = {}
        if schedule_id:
            sched_cfg = db.get_standup_schedule(team_id, schedule_id) or {}
        if not sched_cfg:
            try:
                sched_cfg = db.get_standup_schedule_for_channel(team_id, channel_id) or {}
            except Exception:
                pass

        # Filter standups to only include this schedule's participants
        participants = sched_cfg.get("participants") or []
        if participants:
            participant_set = set(participants)
            today_standups = [s for s in today_standups if s.get("user_id") in participant_set]
            if not today_standups:
                logger.info(
                    "No submissions from schedule participants for %s/%s — skipping report", team_id, schedule_id
                )
                return

        # Honor per-schedule opt-out for the end-of-day summary.
        if sched_cfg.get("post_summary") is False:
            logger.info("Summary disabled for %s/%s — skipping report", team_id, schedule_id)
            return

        group_by = sched_cfg.get("group_by", "member")
        # Use schedule-specific questions, falling back to workspace config
        questions = sched_cfg.get("questions") or []
        if isinstance(questions, str):
            try:
                questions = _json.loads(questions)
            except Exception:
                questions = []
        if not questions:
            config = db.get_workspace_config(team_id) or {}
            questions = config.get("questions") or []
            if isinstance(questions, str):
                try:
                    questions = _json.loads(questions)
                except Exception:
                    questions = []

        # Only fetch profiles for relevant members
        relevant_user_ids = {s.get("user_id") for s in today_standups}
        active_members = [m for m in db.get_active_members(team_id) if m["user_id"] in relevant_user_ids]
        user_profiles = {}
        for m in active_members:
            try:
                info = client.users_info(user=m["user_id"]).get("user", {})
                profile = info.get("profile", {})
                user_profiles[m["user_id"]] = {
                    "display_name": profile.get("real_name") or m.get("real_name", ""),
                    "avatar_url": profile.get("image_48", ""),
                }
            except Exception:
                user_profiles[m["user_id"]] = {"display_name": m.get("real_name", ""), "avatar_url": ""}

        import blocks as _blocks  # noqa: PLC0415

        if group_by == "question":
            summary_blocks = _blocks.build_summary_by_question(today_standups, questions, user_profiles=user_profiles)
        else:
            summary_blocks = _blocks.build_summary_by_member(today_standups, questions, user_profiles=user_profiles)

        # Thread the summary under today's daily thread parent to reduce
        # channel clutter. Prefer the DB-backed lookup (survives pod restarts)
        # and fall back to the in-memory cache used by the Bolt handler.
        thread_ts = None
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            thread_ts = db.get_daily_thread_ts(team_id, channel_id, today_str)
        except Exception:
            thread_ts = None
        if not thread_ts:
            try:
                from handlers import _daily_thread_cache  # noqa: PLC0415

                thread_ts = _daily_thread_cache.get(f"{team_id}:{channel_id}:{today_str}")
            except Exception:
                thread_ts = None

        post_kwargs = {"channel": channel_id, "text": "📋 Daily Standup Summary", "blocks": summary_blocks}
        if thread_ts:
            post_kwargs["thread_ts"] = thread_ts
        summary_resp = client.chat_postMessage(**post_kwargs)
        summary_thread_ts = thread_ts or summary_resp.get("ts")
        logger.info(
            "Posted scheduled report for team %s to %s (%d submissions)", team_id, channel_id, len(today_standups)
        )

        # AI summary
        try:
            from ai_summary import generate_summary  # noqa: PLC0415

            ws_config = db.get_workspace_config(team_id) or {}
            if ws_config.get("ai_summary_enabled"):
                inst = db.get_installation(team_id)
                team_name = (inst or {}).get("team_name", "")
                summary_text = generate_summary(today_standups, team_name)
                if summary_text:
                    ai_kwargs = {"channel": channel_id, "text": f"✨ *AI Summary*\n\n{summary_text}"}
                    if summary_thread_ts:
                        ai_kwargs["thread_ts"] = summary_thread_ts
                    client.chat_postMessage(**ai_kwargs)
        except Exception as exc:
            logger.warning("AI summary in scheduled report failed: %s", exc)

    except Exception as exc:
        logger.error("Scheduled report failed for %s: %s", team_id, exc)


def register_workspace_job(
    scheduler: BackgroundScheduler,
    team_id: str,
    bot_token: str,
    config: dict,
) -> None:
    """Add or replace a cron job for a single workspace."""
    schedule_time: str = config.get("schedule_time", "09:00")
    schedule_tz: str = config.get("schedule_tz", "UTC")
    schedule_days: str = config.get("schedule_days", "mon,tue,wed,thu,fri")
    channel_id: str = config.get("channel_id") or ""

    try:
        hour, minute = schedule_time.split(":")
        tz = pytz.timezone(schedule_tz)
    except Exception as exc:
        logger.error("Invalid schedule config for %s: %s", team_id, exc)
        return

    trigger = CronTrigger(
        hour=int(hour),
        minute=int(minute),
        day_of_week=schedule_days,
        timezone=tz,
    )

    scheduler.add_job(
        _send_standup_to_workspace,
        trigger=trigger,
        args=[team_id, bot_token, channel_id],
        id=f"standup_{team_id}",
        name=f"Standup — {team_id}",
        replace_existing=True,
    )
    logger.info(
        "Registered standup job for %s at %s %s (%s)",
        team_id,
        schedule_time,
        schedule_tz,
        schedule_days,
    )

    # Reminder job
    reminder_minutes = int(config.get("reminder_minutes") or 0)
    if reminder_minutes > 0:
        standup_dt = datetime(2000, 1, 1, int(hour), int(minute))
        reminder_dt = standup_dt - timedelta(minutes=reminder_minutes)
        reminder_days = schedule_days
        if reminder_dt.date() < standup_dt.date():
            day_map = {"mon": "sun", "tue": "mon", "wed": "tue", "thu": "wed", "fri": "thu", "sat": "fri", "sun": "sat"}
            reminder_days = ",".join(day_map.get(d, d) for d in schedule_days.split(","))
        scheduler.add_job(
            _send_reminder_to_workspace,
            trigger=CronTrigger(
                hour=reminder_dt.hour,
                minute=reminder_dt.minute,
                day_of_week=reminder_days,
                timezone=tz,
            ),
            args=[team_id, bot_token, reminder_minutes],
            id=f"reminder_{team_id}",
            name=f"Reminder — {team_id}",
            replace_existing=True,
        )
        logger.info("Registered reminder job for %s (%d min before)", team_id, reminder_minutes)

    # Weekly digest job (Sunday 18:00 in workspace tz)
    scheduler.add_job(
        _send_weekly_digest,
        trigger=CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=tz),
        args=[team_id, bot_token],
        id=f"digest_{team_id}",
        name=f"Weekly Digest — {team_id}",
        replace_existing=True,
    )

    # Manager digest job — runs daily at standup time (after standup completes)
    # Use a 30-minute offset after the standup time so responses are in by then
    standup_plus_30 = datetime(2000, 1, 1, int(hour), int(minute)) + timedelta(minutes=30)
    scheduler.add_job(
        _send_manager_digest,
        trigger=CronTrigger(
            hour=standup_plus_30.hour,
            minute=standup_plus_30.minute,
            day_of_week=schedule_days,
            timezone=tz,
        ),
        args=[team_id],
        id=f"manager_digest_{team_id}",
        name=f"Manager Digest — {team_id}",
        replace_existing=True,
    )

    # Scheduled report job — posts summary at report_time regardless of completion
    report_time = config.get("report_time") or schedule_time
    try:
        r_hour, r_minute = report_time.split(":")
    except Exception:
        r_hour, r_minute = hour, minute
    scheduler.add_job(
        _post_scheduled_report,
        trigger=CronTrigger(
            hour=int(r_hour),
            minute=int(r_minute),
            day_of_week=schedule_days,
            timezone=tz,
        ),
        args=[team_id, bot_token, channel_id],
        id=f"report_{team_id}",
        name=f"Report — {team_id}",
        replace_existing=True,
    )
    logger.info("Registered report job for %s at %s %s", team_id, report_time, schedule_tz)


def register_workspace_digests_only(
    scheduler: BackgroundScheduler,
    team_id: str,
    bot_token: str,
    config: dict,
) -> None:
    """Register only digest jobs for a workspace that has schedule-level standups.

    Skips standup DMs, reminders, and reports — those are handled per-schedule.
    """
    schedule_time: str = config.get("schedule_time", "09:00")
    schedule_tz: str = config.get("schedule_tz", "UTC")
    schedule_days: str = config.get("schedule_days", "mon,tue,wed,thu,fri")
    try:
        hour, minute = schedule_time.split(":")
        tz = pytz.timezone(schedule_tz)
    except Exception as exc:
        logger.error("Invalid schedule config for %s: %s", team_id, exc)
        return

    # Weekly digest
    scheduler.add_job(
        _send_weekly_digest,
        trigger=CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=tz),
        args=[team_id, bot_token],
        id=f"digest_{team_id}",
        name=f"Weekly Digest — {team_id}",
        replace_existing=True,
    )

    # Manager digest
    standup_plus_30 = datetime(2000, 1, 1, int(hour), int(minute)) + timedelta(minutes=30)
    scheduler.add_job(
        _send_manager_digest,
        trigger=CronTrigger(
            hour=standup_plus_30.hour,
            minute=standup_plus_30.minute,
            day_of_week=schedule_days,
            timezone=tz,
        ),
        args=[team_id],
        id=f"manager_digest_{team_id}",
        name=f"Manager Digest — {team_id}",
        replace_existing=True,
    )
    logger.info("Registered digest-only jobs for %s (schedule-level standups active)", team_id)


def register_schedule_job(scheduler: BackgroundScheduler, schedule: dict) -> None:
    """Register a cron job for a standup_schedules row."""
    team_id = schedule["team_id"]
    bot_token = schedule["bot_token"]
    schedule_id = schedule["id"]
    schedule_time = schedule.get("schedule_time", "09:00")
    schedule_tz = schedule.get("schedule_tz", "UTC")
    schedule_days = schedule.get("schedule_days", "mon,tue,wed,thu,fri")
    channel_id = schedule.get("channel_id") or ""
    reminder_minutes = int(schedule.get("reminder_minutes") or 0)

    try:
        hour, minute = schedule_time.split(":")
        tz = pytz.timezone(schedule_tz)
    except Exception as exc:
        logger.error("Invalid schedule config %s: %s", schedule_id, exc)
        return

    trigger = CronTrigger(hour=int(hour), minute=int(minute), day_of_week=schedule_days, timezone=tz)
    job_id = f"schedule_{team_id}_{schedule_id}"
    scheduler.add_job(
        _send_standup_to_workspace,
        trigger=trigger,
        args=[team_id, bot_token, channel_id, schedule_id],
        id=job_id,
        name=f"{schedule.get('name', 'Standup')} — {team_id}",
        replace_existing=True,
    )
    logger.info(
        "Registered schedule job %s (%s) at %s %s", schedule_id, schedule.get("name"), schedule_time, schedule_tz
    )

    if reminder_minutes > 0:
        standup_dt = datetime(2000, 1, 1, int(hour), int(minute))
        reminder_dt = standup_dt - timedelta(minutes=reminder_minutes)
        reminder_days = schedule_days
        if reminder_dt.date() < standup_dt.date():
            day_map = {"mon": "sun", "tue": "mon", "wed": "tue", "thu": "wed", "fri": "thu", "sat": "fri", "sun": "sat"}
            reminder_days = ",".join(day_map.get(d, d) for d in schedule_days.split(","))
        scheduler.add_job(
            _send_reminder_to_workspace,
            trigger=CronTrigger(
                hour=reminder_dt.hour, minute=reminder_dt.minute, day_of_week=reminder_days, timezone=tz
            ),
            args=[team_id, bot_token, reminder_minutes, schedule_id],
            id=f"reminder_schedule_{team_id}_{schedule_id}",
            replace_existing=True,
        )

    weekend_reminder = bool(schedule.get("weekend_reminder")) or reminder_minutes == -1
    if weekend_reminder:
        scheduler.add_job(
            _send_reminder_to_workspace,
            trigger=CronTrigger(hour=int(hour), minute=int(minute), day_of_week="fri", timezone=tz),
            args=[team_id, bot_token, reminder_minutes if reminder_minutes > 0 else 0],
            id=f"weekend_reminder_schedule_{team_id}_{schedule_id}",
            name=f"Weekend Reminder — {schedule.get('name', 'Standup')} — {team_id}",
            replace_existing=True,
        )
        logger.info(
            "Registered weekend reminder job %s (%s) on Fridays at %s", schedule_id, schedule.get("name"), schedule_time
        )

    # Scheduled report job — posts summary at report_time regardless of completion
    report_time = schedule.get("report_time") or schedule_time
    try:
        r_hour, r_minute = report_time.split(":")
    except Exception:
        r_hour, r_minute = hour, minute
    scheduler.add_job(
        _post_scheduled_report,
        trigger=CronTrigger(
            hour=int(r_hour),
            minute=int(r_minute),
            day_of_week=schedule_days,
            timezone=tz,
        ),
        args=[team_id, bot_token, channel_id, schedule_id],
        id=f"report_schedule_{team_id}_{schedule_id}",
        name=f"Report — {schedule.get('name', 'Standup')} — {team_id}",
        replace_existing=True,
    )
    logger.info("Registered report job for schedule %s at %s %s", schedule_id, report_time, schedule_tz)


def build_scheduler(installations: list[tuple[str, str, dict]]) -> BackgroundScheduler:
    """Build scheduler from a list of (team_id, bot_token, config) tuples."""
    global _scheduler
    scheduler = BackgroundScheduler()

    # Collect teams that have schedule-level standups so we skip
    # duplicate workspace-level standup/report jobs for them.
    teams_with_schedules: set[str] = set()
    try:
        import db  # noqa: PLC0415

        all_schedules = db.get_all_active_schedules()
        for sched in all_schedules:
            teams_with_schedules.add(sched["team_id"])
            register_schedule_job(scheduler, sched)
    except Exception as exc:
        logger.warning("Could not load standup_schedules: %s", exc)

    for team_id, bot_token, config in installations:
        if team_id in teams_with_schedules:
            # Only register digest/manager jobs — standup + report handled by schedules
            register_workspace_digests_only(scheduler, team_id, bot_token, config)
        else:
            register_workspace_job(scheduler, team_id, bot_token, config)

    # Background bot-token maintenance: refresh any token nearing expiry every 30 minutes.
    # Runs once shortly after startup so freshly-booted pods don't wait half an hour.
    scheduler.add_job(
        _refresh_all_tokens_job,
        trigger=IntervalTrigger(minutes=30),
        id="token_maintenance",
        name="Background bot-token refresh",
        replace_existing=True,
        next_run_time=datetime.now(tz=timezone.utc) + timedelta(minutes=1),
    )

    _scheduler = scheduler
    return scheduler
