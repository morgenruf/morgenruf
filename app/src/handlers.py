"""Standup message handlers — DM conversation and channel posting."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import pytz
import requests
from slack_bolt import App
from state import state_store

logger = logging.getLogger(__name__)

# Cache daily thread parent message ts per channel: "team:channel:YYYY-MM-DD" -> ts
_daily_thread_cache: dict[str, str] = {}


def _clean_thread_cache() -> None:
    """Remove stale entries from the thread cache (keep only today)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stale = [k for k in _daily_thread_cache if not k.endswith(today)]
    for k in stale:
        del _daily_thread_cache[k]


# Track which users are in configure mode: "team_id:user_id"
_configure_mode_users: set[str] = set()

_MOOD_QUESTION = "🎭 *How are you feeling today?* _(😊 great · 😐 okay · 😔 rough — or type anything)_"


def _send_mood_block(client, user_id: str) -> None:
    """Send the mood question as Block Kit buttons."""
    client.chat_postMessage(
        channel=user_id,
        text=_MOOD_QUESTION,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "🎭 *How are you feeling today?*"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "😊 Great"},
                        "action_id": "mood_great",
                        "value": "great",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "😐 Okay"},
                        "action_id": "mood_okay",
                        "value": "okay",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "😔 Rough"},
                        "action_id": "mood_rough",
                        "value": "rough",
                    },
                ],
            },
        ],
    )


def _get_bot_channels(client) -> list[dict]:
    """Return channels where the bot is a member: [{"id": ..., "name": ...}].

    Uses ``users_conversations`` which reliably returns only channels the
    calling bot user has joined — unlike ``conversations_list`` + ``is_member``
    which can be unreliable with refreshable (xoxe) tokens.
    """
    channels = []
    cursor = None
    try:
        while True:
            kwargs = {"types": "public_channel,private_channel", "exclude_archived": True, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = client.users_conversations(**kwargs)
            for c in result.get("channels", []):
                channels.append({"id": c["id"], "name": c["name"]})
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as exc:
        logger.warning("_get_bot_channels error: %s", exc)
    return channels


_DEFAULT_LABELS = ["✅ Yesterday", "🎯 Today", "🚧 Blockers"]


def _format_standup(
    user_id: str, answers: list[str], mood: str | None = None, questions: list[str] | None = None
) -> str:
    """Format collected answers into a structured standup post."""
    import blocks as _blocks  # noqa: PLC0415

    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

    labels = questions or _DEFAULT_LABELS
    parts = [f"📋 *Standup from <@{user_id}>* — {date_str}\n"]
    for i, label in enumerate(labels):
        raw = answers[i] if i < len(answers) else "—"
        # Detect "no blockers" only for the last default question
        if not questions and i == 2 and raw.strip().lower() in ("none", "no", "nope", "-", "n/a", ""):
            formatted_answer = "_None_ ✅"
        else:
            formatted_answer = _blocks.linkify_issues(raw) if raw != "—" else raw
        parts.append(f"*{label}:*\n{formatted_answer}")

    text = "\n\n".join(parts)
    if mood:
        text += f"\n\n*🎭 Mood:* {mood}"
    return text


def _persist_standup(team_id: str, user_id: str, answers: list[str], mood: str | None = None) -> int | None:
    """Best-effort persist to DB; log and continue on failure. Returns standup ID."""
    try:
        import db  # noqa: PLC0415

        return db.save_standup(
            team_id=team_id,
            user_id=user_id,
            yesterday=answers[0] if len(answers) > 0 else "",
            today=answers[1] if len(answers) > 1 else "",
            blockers=answers[2] if len(answers) > 2 else "",
            mood=mood,
        )
    except Exception as exc:
        logger.warning("Could not persist standup for %s/%s: %s", team_id, user_id, exc)
        return None


def _send_question_block(client, user_id: str, question: str, step: int, initial_value: str | None = None) -> None:
    """Send a standup question as a Block Kit input block plus a Submit button.

    Uses rich_text_input so users get the formatting toolbar (bold, italic,
    bullets, etc.). The handler reads the answer out of state.values via
    rich_text_value rather than action.value. When `initial_value` is provided
    (edit flow) the previous answer is pre-filled so the user can tweak it.
    """
    import blocks as _blocks  # noqa: PLC0415

    element: dict = {
        "type": "rich_text_input",
        "action_id": f"standup_answer_{step}",
    }
    if initial_value:
        element["initial_value"] = _blocks.mrkdwn_to_rich_text(initial_value)
    client.chat_postMessage(
        channel=user_id,
        text=question,  # fallback for notifications
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{question}*"},
            },
            {
                "type": "input",
                "block_id": f"answer_{step}",
                "dispatch_action": True,
                "element": element,
                "label": {"type": "plain_text", "text": "Your answer"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Submit"},
                        "action_id": f"submit_answer_{step}",
                        "value": str(step),
                        "style": "primary",
                    }
                ],
            },
        ],
    )


def _initial_answer_for(session, step: int) -> str | None:
    """Return the previous answer for `step` when the session is an edit of an existing standup."""
    if not getattr(session, "editing_standup_id", None):
        return None
    answers = getattr(session, "edit_initial_answers", None) or []
    if 0 <= step < len(answers):
        return answers[step] or None
    return None


def _start_standup_session(user_id: str, team_id: str, client, schedule_id: int | None = None) -> None:
    """Look up workspace config, create a session, and send the first question block.

    When `schedule_id` is provided (e.g. user clicked the per-schedule App Home
    button) we use that exact schedule and skip the user-to-schedule guess so
    members of multiple schedules land in the one they actually picked.
    """
    cache_key = f"{team_id}:{user_id}"
    # An explicit "standup"/"start" from the user means they want to begin
    # (or restart) now. Silently clear any prior session — the old behavior
    # of blocking left users stuck when a scheduled session was never
    # completed or when they belong to multiple schedules.
    if state_store.is_active(cache_key):
        state_store.clear(cache_key)

    channel = ""
    questions = None
    standup_name = "Team Standup"
    resolved_schedule_id: int | None = schedule_id
    try:
        import db  # noqa: PLC0415

        sched = None
        if schedule_id is not None:
            # Explicit schedule from a per-schedule UI (App Home button etc.)
            sched = db.get_standup_schedule(team_id, schedule_id)
        if sched is None:
            # Fall back to the user-to-schedule heuristic for paths that don't
            # carry an explicit schedule (DM "standup", /standup command).
            sched = db.get_schedule_for_user(team_id, user_id)
        if sched:
            channel = sched.get("channel_id", "") or ""
            qs = sched.get("questions") or []
            standup_name = sched.get("name") or standup_name
            resolved_schedule_id = sched.get("id")
        else:
            config = db.get_workspace_config(team_id) or {}
            channel = config.get("channel_id", "")
            qs = config.get("questions") or []

        if isinstance(qs, str):
            import json as _json  # noqa: PLC0415

            try:
                qs = _json.loads(qs)
            except Exception:
                qs = []
        if qs:
            questions = qs
    except Exception as e:
        logger.warning("Unexpected error in _start_standup_session loading config: %s", e)

    session = state_store.start(
        cache_key,
        channel,
        team_id=team_id,
        questions=questions,
        standup_name=standup_name,
        schedule_id=resolved_schedule_id,
    )
    client.chat_postMessage(channel=user_id, text="📋 Starting your standup!")
    _send_question_block(client, user_id, session.questions[0], 0, _initial_answer_for(session, 0))


def _complete_standup(user_id: str, session, client) -> None:
    """Finalize a completed standup: send Block Kit confirmation, post to channel, persist, fire events."""
    _clean_thread_cache()
    n_questions = len(session.questions)
    question_answers = session.answers[:n_questions]
    mood = session.answers[n_questions] if len(session.answers) > n_questions else None

    # If this is an edit of a prior submission, update the existing row in place
    # instead of creating a duplicate standup record.
    is_edit = bool(getattr(session, "editing_standup_id", None))
    standup_id: int | None = None
    if is_edit:
        try:
            import db  # noqa: PLC0415

            update_fields: dict = {
                "yesterday": question_answers[0] if len(question_answers) > 0 else "",
                "today": question_answers[1] if len(question_answers) > 1 else "",
                "blockers": question_answers[2] if len(question_answers) > 2 else "",
            }
            if mood is not None:
                update_fields["mood"] = mood
            db.update_standup(user_id=user_id, team_id=session.team_id, **update_fields)
            standup_id = session.editing_standup_id
        except Exception as exc:
            logger.warning("Could not update standup %s for %s: %s", session.editing_standup_id, user_id, exc)
    else:
        # Persist first so we have the standup ID for the edit button
        standup_id = _persist_standup(session.team_id, user_id, question_answers, mood=mood)

    confirmation_text = (
        "✏️ *Standup updated!* Your edits have been saved."
        if is_edit
        else "✅ *Standup submitted!* You can edit your responses within 30 minutes."
    )
    # Block Kit confirmation with edit button
    client.chat_postMessage(
        channel=user_id,
        text="✏️ Standup updated!" if is_edit else "✅ Standup submitted!",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": confirmation_text,
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✏️ Edit responses"},
                        "action_id": "standup_edit",
                        "value": str(standup_id) if standup_id else "0",
                        "style": "primary",
                    }
                ],
            },
        ],
    )

    formatted = _format_standup(user_id, question_answers, mood=mood, questions=session.questions)
    channel = session.channel
    if channel:
        try:
            import db as _db  # noqa: PLC0415

            sched_config = {}
            try:
                # Prefer an exact schedule_id lookup so workspaces with multiple
                # schedules sharing one channel (e.g. morning + evening standups)
                # don't get the wrong schedule's name / notify_on_report / flags.
                if getattr(session, "schedule_id", None):
                    sched_config = _db.get_standup_schedule(session.team_id, session.schedule_id) or {}
                if not sched_config:
                    sched_config = _db.get_standup_schedule_for_channel(session.team_id, channel) or {}
            except Exception as e:
                logger.warning("Unexpected error in _complete_standup fetching schedule config: %s", e)

            notify_on_report = sched_config.get("notify_on_report", True)
            if not notify_on_report:
                # Replace Slack mention with plain display name to avoid notifying the user
                member_name = user_id
                try:
                    for m in _db.get_active_members(session.team_id):
                        if m["user_id"] == user_id:
                            member_name = m.get("real_name") or user_id
                            break
                except Exception as e:
                    logger.warning("Unexpected error in _complete_standup resolving member name: %s", e)
                formatted = formatted.replace(f"<@{user_id}>", member_name)

            try:
                from autolink import autolink  # noqa: PLC0415

                cfg = _db.get_workspace_config(session.team_id) or {}
                formatted = autolink(formatted, cfg)
            except Exception as e:
                logger.warning("Unexpected error in _complete_standup applying autolink: %s", e)

            # Always post individual standups in a daily thread, scoped by
            # schedule so Morning and Evening standups don't share a thread.
            now_utc = datetime.now(timezone.utc)
            today_str = now_utc.strftime("%Y-%m-%d")
            schedule_id = int(getattr(session, "schedule_id", 0) or sched_config.get("id") or 0)
            thread_key = f"{session.team_id}:{channel}:{today_str}:{schedule_id}"
            parent_ts = _daily_thread_cache.get(thread_key)

            if not parent_ts:
                # Check DB first — the in-memory cache is lost on pod restart.
                try:
                    parent_ts = _db.get_daily_thread_ts(session.team_id, channel, today_str, schedule_id)
                except Exception:
                    parent_ts = None

            if not parent_ts:
                # Create parent message for today's thread — polished like competitors
                standup_name = sched_config.get("name") or session.standup_name or "Team Standup"
                display_date = now_utc.strftime("%a, %b %d.")
                parent = client.chat_postMessage(
                    channel=channel,
                    text=f"✨ {standup_name} Completed - {display_date} ✨",
                )
                parent_ts = parent["ts"]
                try:
                    _db.upsert_daily_thread(session.team_id, channel, today_str, parent_ts, schedule_id)
                except Exception as e:
                    logger.warning("Could not persist daily thread ts: %s", e)

            _daily_thread_cache[thread_key] = parent_ts

            # Mark edits so teammates can tell which message is the latest version;
            # we don't have the original reply's ts to update in place, so post
            # the updated version as a new thread reply with a clear indicator.
            channel_text = f"✏️ *Updated standup*\n{formatted}" if is_edit else formatted
            client.chat_postMessage(
                channel=channel,
                text=channel_text,
                thread_ts=parent_ts,
                unfurl_links=False,
            )
            logger.info(
                "Posted %s for %s to %s (thread)",
                "standup update" if is_edit else "standup",
                user_id,
                channel,
            )
        except Exception as exc:
            logger.error("Failed to post standup for %s: %s", user_id, exc)
            client.chat_postMessage(
                channel=user_id,
                text=f"⚠️ Could not post to channel — please paste manually:\n\n{formatted}",
            )

    # Ensure member exists in DB for reports/participation
    try:
        import db  # noqa: PLC0415

        user_info = client.users_info(user=user_id).get("user", {})
        profile = user_info.get("profile", {})
        db.upsert_member(
            team_id=session.team_id,
            user_id=user_id,
            real_name=profile.get("real_name", ""),
            email=profile.get("email", ""),
            tz=user_info.get("tz", "UTC"),
        )
    except Exception as e:
        logger.warning("Could not upsert member during standup: %s", e)

    state_store.clear(f"{session.team_id}:{user_id}")

    # Build answers dict keyed by question text
    answers_dict = {}
    for i, q in enumerate(session.questions):
        answers_dict[q] = question_answers[i] if i < len(question_answers) else ""
    # Also include legacy keys for backwards compatibility
    if len(question_answers) > 0:
        answers_dict["yesterday"] = question_answers[0]
    if len(question_answers) > 1:
        answers_dict["today"] = question_answers[1]
    if len(question_answers) > 2:
        answers_dict["blockers"] = question_answers[2]

    fire_webhooks(
        session.team_id,
        "standup.completed",
        {
            "team_id": session.team_id,
            "user_id": user_id,
            "answers": answers_dict,
            "mood": mood,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Report posting is handled by the scheduled report job (_post_scheduled_report)
    # which fires at report_time regardless of whether all members submitted.

    try:
        from workflow import evaluate_rules  # noqa: PLC0415

        # Check last answer for blockers (convention: last question is usually blockers)
        blocker_text = question_answers[-1] if question_answers else ""
        has_blockers = bool(blocker_text.strip()) and blocker_text.strip().lower() not in (
            "none",
            "no",
            "nope",
            "-",
            "n/a",
        )
        evaluate_rules(
            session.team_id,
            "blocker_detected",
            {"has_blockers": has_blockers, "blockers": blocker_text, "team": session.team_id},
            client,
        )
        evaluate_rules(session.team_id, "standup_complete", {"team": session.team_id}, client)
    except Exception as exc:
        logger.warning("Workflow rules evaluation failed: %s", exc)


def fire_webhooks(team_id: str, event_type: str, payload: dict) -> None:
    """POST payload to every registered webhook for team_id.

    Adds ``X-Morgenruf-Event`` and (when a secret is configured)
    ``X-Morgenruf-Signature`` headers to each request.
    Failures are logged but never raised so they can't break the main flow.
    """
    try:
        import db  # noqa: PLC0415

        webhooks = db.get_webhooks(team_id)
    except Exception as exc:
        logger.warning("Could not fetch webhooks for %s: %s", team_id, exc)
        return

    if not webhooks:
        return

    body = json.dumps(payload, default=str).encode()

    for hook in webhooks:
        events: list[str] = hook.get("events") or ["standup.completed"]
        if event_type not in events:
            continue

        headers = {
            "Content-Type": "application/json",
            "X-Morgenruf-Event": event_type,
        }

        secret: str | None = hook.get("secret")
        if secret:
            sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Morgenruf-Signature"] = f"sha256={sig}"

        try:
            resp = requests.post(hook["webhook_url"], data=body, headers=headers, timeout=10)
            logger.info(
                "Webhook %s fired for %s → HTTP %s",
                hook["webhook_url"],
                event_type,
                resp.status_code,
            )
        except Exception as exc:
            logger.warning("Webhook delivery failed for %s: %s", hook["webhook_url"], exc)


def can_edit_response(team_id: str, user_id: str, standup_id: int) -> bool:
    """Return True if the user is still within their edit window.

    The edit window is controlled by ``edit_window_hours`` in workspace_config:
      * ``0``    — editable until the report time (treated as no time limit here)
      * positive — that many hours after submission
      * ``None`` — no limit
    """
    try:
        import db  # noqa: PLC0415

        standup = db.get_standup_by_id(standup_id)
        if not standup:
            return False
        if standup["user_id"] != user_id or standup["team_id"] != team_id:
            return False

        config = db.get_workspace_config(team_id) or {}
        edit_window_hours = config.get("edit_window_hours", 4)

        if edit_window_hours is None:
            return True
        if edit_window_hours == 0:
            return True

        submitted_at: datetime = standup["submitted_at"]
        if submitted_at.tzinfo is None:
            submitted_at = submitted_at.replace(tzinfo=timezone.utc)
        cutoff = submitted_at + timedelta(hours=edit_window_hours)
        return datetime.now(tz=timezone.utc) <= cutoff

    except Exception as exc:
        logger.warning("can_edit_response check failed for %s/%s: %s", team_id, user_id, exc)
        return False


def register_handlers(app: App) -> None:
    """Register all Slack event handlers."""

    # ----- External select: timezone search -----
    @app.options("timezone")
    def handle_timezone_options(ack, payload):  # noqa: ANN001
        """Server-side search for timezone external_select."""
        import blocks as _blocks  # noqa: PLC0415

        query = payload.get("value", "")
        ack(options=_blocks.timezone_search(query))

    @app.event("tokens_revoked")
    def handle_tokens_revoked(event, logger) -> None:  # noqa: ANN001
        """Handle token revocation — remove workspace installation and all data."""
        import db  # noqa: PLC0415

        team_id = event.get("team_id") or (event.get("authorizations") or [{}])[0].get("team_id", "")
        if not team_id:
            logger.warning("tokens_revoked received with no team_id: %s", event)
            return
        deleted = db.delete_installation(team_id)
        if deleted:
            logger.info("tokens_revoked: deleted installation and all data for team %s", team_id)
        else:
            logger.warning("tokens_revoked: no installation found for team %s", team_id)

    @app.event("app_uninstalled")
    def handle_app_uninstalled(event, logger) -> None:  # noqa: ANN001
        """Handle app uninstall — remove workspace installation and all data."""
        import db  # noqa: PLC0415

        team_id = event.get("team_id", "")
        if not team_id:
            logger.warning("app_uninstalled received with no team_id: %s", event)
            return
        deleted = db.delete_installation(team_id)
        if deleted:
            logger.info("app_uninstalled: deleted installation and all data for team %s", team_id)
        else:
            logger.warning("app_uninstalled: no installation found for team %s", team_id)

    @app.event("message")
    def handle_dm(event, say, client, logger):  # noqa: ANN001
        """Handle incoming DMs — collect standup answers step by step."""
        if event.get("channel_type") != "im":
            return
        if event.get("subtype"):
            return

        user_id: str = event["user"]
        team_id: str = event.get("team", "")
        text: str = event.get("text", "").strip()
        cache_key = f"{team_id}:{user_id}"

        session = state_store.get(cache_key)
        if not session:
            return

        session = state_store.record_answer(cache_key, text)
        n_questions = len(session.questions)

        if session.step < n_questions:
            # Still collecting question answers — send next question as Block Kit
            _send_question_block(
                client,
                user_id,
                session.questions[session.step],
                session.step,
                _initial_answer_for(session, session.step),
            )
        elif session.step == n_questions:
            # All questions answered — ask mood
            _send_mood_block(client, user_id)
        else:
            # Mood answered — finalize
            _complete_standup(user_id, session, client)

    @app.event("app_home_opened")
    def handle_app_home(event, client, body=None):  # noqa: ANN001
        """Render the App Home tab when a user opens it."""
        user_id = event["user"]
        team_id = (
            event.get("view", {}).get("team_id") or (body.get("team_id") if body else None) or event.get("team") or ""
        )
        logger.info("app_home_opened: user=%s team=%s", user_id, team_id)

        import blocks as _blocks  # noqa: PLC0415

        workspace_name = ""
        on_vacation = False
        streak = 0
        is_admin = False
        all_other_standups: list[dict] = []
        standups: list[dict] = []

        # Fetch user timezone and Slack admin status FIRST so is_admin is available below
        user_tz = ""
        try:
            user_info = client.users_info(user=user_id)
            user_data = user_info.get("user", {})
            user_tz = user_data.get("tz", "")
            is_admin = user_data.get("is_admin", False) or user_data.get("is_owner", False)
        except Exception:
            pass

        try:
            import db  # noqa: PLC0415

            on_vacation = db.is_on_vacation(team_id, user_id)
            streak = db.get_standup_streak(team_id, user_id)

            # Get today's submissions for this user
            today_standups = db.get_today_standups(team_id)
            user_today = [s for s in today_standups if s.get("user_id") == user_id]
            user_responded_today = len(user_today) > 0
            user_last_response = user_today[-1] if user_today else None

            # Load standup schedules for this workspace
            all_other_standups: list[dict] = []
            schedules = db.get_standup_schedules(team_id)
            for s in schedules:
                # Parse schedule_days into a list
                days = s.get("schedule_days", "mon,tue,wed,thu,fri")
                if isinstance(days, str):
                    days = [d.strip() for d in days.split(",") if d.strip()]
                participants = s.get("participants") or []
                is_participant = not participants or user_id in participants
                # Parse questions from DB (stored as JSON string or list)
                raw_q = s.get("questions") or []
                if isinstance(raw_q, str):
                    try:
                        raw_q = json.loads(raw_q)
                    except Exception:
                        raw_q = []

                entry = {
                    "standup_id": str(s["id"]),
                    "standup_name": s.get("name", "Team Standup"),
                    "channel_id": s.get("channel_id", ""),
                    "report_time": s.get("schedule_time", "09:00"),
                    "timezone": s.get("schedule_tz", "UTC"),
                    "days": days,
                    "members": participants,
                    "active": s.get("active", True),
                    "questions": raw_q,
                    "is_participant": is_participant,
                    "user_responded_today": user_responded_today if is_participant else False,
                    "user_last_response_time": (
                        user_last_response["submitted_at"].strftime("%-I:%M %p")
                        if user_last_response and user_last_response.get("submitted_at")
                        else None
                    ),
                }
                if is_participant:
                    standups.append(entry)
                elif is_admin:
                    all_other_standups.append(entry)

            try:
                info = client.team_info()
                workspace_name = info.get("team", {}).get("name", "")
            except Exception:
                pass
        except Exception as e:
            logger.warning("handle_app_home error loading data: %s", e)

        view = _blocks.app_home_view(
            standups=standups,
            user_id=user_id,
            on_vacation=on_vacation,
            streak=streak,
            workspace_name=workspace_name,
            user_tz=user_tz,
            is_admin=is_admin,
            other_standups=all_other_standups if is_admin else [],
        )

        try:
            client.views_publish(user_id=user_id, view=view)
        except Exception as exc:
            logger.warning("Failed to publish App Home for %s: %s", user_id, exc)

    @app.action("vacation_return")
    def handle_vacation_return(ack, body, client):  # noqa: ANN001
        ack()
        user_id = body["user"]["id"]
        team_id = body["user"]["team_id"]
        try:
            import db  # noqa: PLC0415

            db.set_vacation(team_id, user_id, False)
        except Exception as e:
            logger.warning("Unexpected error in handle_vacation_return clearing vacation: %s", e)
        handle_app_home({"user": user_id, "team": team_id}, client, body={"team_id": team_id})

    @app.action("im_away")
    def handle_im_away(ack, body, client):  # noqa: ANN001
        """Handle 'I'm away' button from DM or App Home."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["user"]["team_id"]
        try:
            import db  # noqa: PLC0415

            db.set_vacation(team_id, user_id, True)
        except Exception as e:
            logger.warning("im_away handler error: %s", e)
        # Clear any active session
        cache_key = f"{team_id}:{user_id}"
        state_store.clear(cache_key)
        client.chat_postMessage(
            channel=user_id,
            text="🏖️ Got it! You're marked as away. I won't send you standups until you're back.\nMessage me *I'm back* or click the button in App Home when you return.",
        )
        # Refresh App Home to show "I'm back" state
        handle_app_home({"user": user_id, "team": team_id}, client, body={"team_id": team_id})

    @app.action("skip_standup")
    def handle_skip_standup_button(ack, body, client):  # noqa: ANN001
        """Handle 'Skip today' button from standup DM."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        try:
            import db  # noqa: PLC0415

            db.skip_today(team_id, user_id)
        except Exception as e:
            logger.warning("skip_standup button error: %s", e)
        cache_key = f"{team_id}:{user_id}"
        state_store.clear(cache_key)
        client.chat_postMessage(channel=user_id, text="✅ Got it! You've skipped today's standup. See you tomorrow! 👋")

    @app.action("fill_in_form")
    def handle_fill_in_form(ack, body, client):  # noqa: ANN001
        """Handle 'Fill in form' button — open modal with all questions at once."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        cache_key = f"{team_id}:{user_id}"
        session = state_store.get(cache_key)
        if not session:
            client.chat_postMessage(
                channel=user_id,
                text="⚠️ Your standup session expired. Run `/standup` to start a new one.",
            )
            return

        import blocks as _blocks  # noqa: PLC0415

        # Try to prefill with previous answers (if enabled for this standup)
        previous_answers = []
        try:
            import db  # noqa: PLC0415

            sched = db.get_standup_schedule_for_channel(team_id, session.channel)
            if sched and sched.get("prepopulate_answers", False):
                prev = db.get_latest_standup(user_id, team_id)
                if prev:
                    previous_answers = [
                        prev.get("yesterday", ""),
                        prev.get("today", ""),
                        prev.get("blockers", ""),
                    ]
        except Exception as e:
            logger.warning("fill_in_form: could not load previous answers: %s", e)

        modal = _blocks.standup_form_modal(
            session.questions, session.standup_name or "Standup", previous_answers=previous_answers
        )
        modal["private_metadata"] = cache_key
        client.views_open(trigger_id=body["trigger_id"], view=modal)

    @app.action("open_create_standup")
    def handle_open_create_standup(ack, body, client):  # noqa: ANN001
        """Handle 'Create a standup' button from App Home."""
        ack()
        import blocks as _blocks  # noqa: PLC0415

        # Default new standup timezone to user's Slack timezone
        user_tz = ""
        try:
            user_id = body["user"]["id"]
            user_info = client.users_info(user=user_id)
            user_tz = user_info.get("user", {}).get("tz", "")
        except Exception:
            pass

        bot_channels = _get_bot_channels(client)
        modal = _blocks.create_standup_modal(
            existing_config={"timezone": user_tz} if user_tz else None,
            bot_channels=bot_channels,
        )
        client.views_open(trigger_id=body["trigger_id"], view=modal)

    @app.action("open_dashboard")
    def handle_open_dashboard(ack):  # noqa: ANN001
        """Acknowledge dashboard link button (URL buttons still need ack)."""
        ack()

    @app.action("open_configure_mode")
    def handle_open_configure_mode(ack, body, client):  # noqa: ANN001
        """Switch App Home to configuration mode (admin only)."""
        ack()
        user_id = body["user"]["id"]
        team_id = body["user"]["team_id"]

        import db as _db  # noqa: PLC0415

        if _db.get_member_role(team_id, user_id) != "admin":
            return
        _configure_mode_users.add(f"{team_id}:{user_id}")
        _publish_configure_view(team_id, user_id, client)

    @app.action("close_configure_mode")
    def handle_close_configure_mode(ack, body, client):  # noqa: ANN001
        """Switch App Home back to normal mode."""
        ack()
        user_id = body["user"]["id"]
        team_id = body["user"]["team_id"]
        _configure_mode_users.discard(f"{team_id}:{user_id}")
        handle_app_home({"user": user_id, "team": team_id}, client, body={"team_id": team_id})

    @app.action("app_home_help")
    def handle_app_home_help(ack, body, client):  # noqa: ANN001
        """Open help modal from App Home."""
        ack()
        import blocks as _blocks  # noqa: PLC0415

        client.views_open(trigger_id=body["trigger_id"], view=_blocks.help_modal())

    def _refresh_home(team_id: str, user_id: str, client) -> None:  # noqa: ANN001
        """Refresh App Home — respects configure mode."""
        if f"{team_id}:{user_id}" in _configure_mode_users:
            _publish_configure_view(team_id, user_id, client)
        else:
            handle_app_home({"user": user_id, "team": team_id}, client, body={"team_id": team_id})

    def _publish_configure_view(team_id: str, user_id: str, client) -> None:  # noqa: ANN001
        """Render and publish the configure mode App Home."""
        import blocks as _blocks  # noqa: PLC0415
        import db  # noqa: PLC0415

        standups: list[dict] = []
        workspace_name = ""
        try:
            schedules = db.get_standup_schedules(team_id)
            for s in schedules:
                days = s.get("schedule_days", "mon,tue,wed,thu,fri")
                if isinstance(days, str):
                    days = [d.strip() for d in days.split(",") if d.strip()]
                participants = s.get("participants") or []
                raw_q = s.get("questions") or []
                if isinstance(raw_q, str):
                    try:
                        raw_q = json.loads(raw_q)
                    except Exception:
                        raw_q = []
                standups.append(
                    {
                        "standup_id": str(s["id"]),
                        "standup_name": s.get("name", "Team Standup"),
                        "channel_id": s.get("channel_id", ""),
                        "report_time": s.get("schedule_time", "09:00"),
                        "timezone": s.get("schedule_tz", "UTC"),
                        "days": days,
                        "members": participants,
                        "active": s.get("active", True),
                        "questions": raw_q,
                    }
                )
            try:
                info = client.team_info()
                workspace_name = info.get("team", {}).get("name", "")
            except Exception:
                pass
        except Exception as e:
            logger.warning("_publish_configure_view error: %s", e)

        view = _blocks.app_home_configure_view(standups, user_id, workspace_name)
        try:
            client.views_publish(user_id=user_id, view=view)
        except Exception as exc:
            logger.warning("Failed to publish configure view for %s: %s", user_id, exc)

    @app.action("start_standup_now")
    def handle_start_standup_now(ack, body, client):  # noqa: ANN001
        """Handle 'Start standup' button from App Home.

        The button is rendered per-schedule and carries the schedule id in
        `value`. We pass it through so users belonging to multiple schedules
        get the exact one they clicked instead of a heuristic guess.
        """
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["user"]["team_id"]
        schedule_id: int | None = None
        try:
            raw = body.get("actions", [{}])[0].get("value", "")
            if raw:
                schedule_id = int(raw)
        except (ValueError, TypeError):
            schedule_id = None
        _start_standup_session(user_id, team_id, client, schedule_id=schedule_id)

    @app.action("view_previous_standups")
    def handle_view_previous_standups(ack, body, client):  # noqa: ANN001
        """Handle 'Previous standups' button — open modal with recent history."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["user"]["team_id"]
        try:
            import blocks as _blocks  # noqa: PLC0415
            import db  # noqa: PLC0415

            standups = db.get_standups(team_id, days=14)
            user_standups = [s for s in standups if s["user_id"] == user_id]
            standup_name = "Standup"
            schedule_id = body["actions"][0].get("value", "")
            if schedule_id:
                try:
                    sched = db.get_standup_schedule(team_id, int(schedule_id))
                    if sched:
                        standup_name = sched.get("name", "Standup")
                except Exception:
                    pass
            modal = _blocks.previous_standups_modal(user_standups, standup_name)
            client.views_open(trigger_id=body["trigger_id"], view=modal)
        except Exception as exc:
            logger.warning("view_previous_standups error: %s", exc)

    @app.action("edit_standup")
    def handle_edit_standup_button(ack, body, client):  # noqa: ANN001
        """Handle 'Edit' button on App Home standup card."""
        ack()
        standup_id = body["actions"][0].get("value", "")
        team_id = body["user"]["team_id"]
        try:
            import blocks as _blocks  # noqa: PLC0415
            import db  # noqa: PLC0415

            schedule = db.get_standup_schedule(team_id, int(standup_id))
            if schedule:
                questions = schedule.get("questions") or []
                if isinstance(questions, str):
                    try:
                        questions = json.loads(questions)
                    except Exception:
                        questions = []
                days = schedule.get("schedule_days", "mon,tue,wed,thu,fri")
                if isinstance(days, str):
                    days = [d.strip() for d in days.split(",") if d.strip()]
                cfg = {
                    "standup_id": str(schedule["id"]),
                    "channel_id": schedule.get("channel_id", ""),
                    "questions": questions,
                    "report_time": schedule.get("schedule_time", "09:00"),
                    "timezone": schedule.get("schedule_tz", "UTC"),
                    "reminder_minutes": schedule.get("reminder_minutes", 0),
                    "days": days,
                    "members": schedule.get("participants") or [],
                    "sync_with_channel": schedule.get("sync_with_channel", False),
                    "report_destination": "thread" if schedule.get("post_to_thread") else "channel",
                    "group_by": schedule.get("group_by", "member"),
                    "standup_name": schedule.get("name", ""),
                    "prepopulate_answers": schedule.get("prepopulate_answers", False),
                    "allow_edit_after_report": schedule.get("allow_edit_after_report", False),
                    "active": schedule.get("active", True),
                }
                bot_channels = _get_bot_channels(client)
                modal = _blocks.create_standup_modal(cfg, bot_channels=bot_channels)
                client.views_open(trigger_id=body["trigger_id"], view=modal)
        except Exception as exc:
            logger.warning("edit_standup_button error: %s", exc)

    @app.action("delete_standup")
    def handle_delete_standup_button(ack, body, client):  # noqa: ANN001
        """Handle 'Delete' button on App Home standup card."""
        ack()
        standup_id = body["actions"][0].get("value", "")
        user_id = body["user"]["id"]
        team_id = body["user"]["team_id"]
        try:
            import db  # noqa: PLC0415

            db.delete_standup_schedule(team_id, int(standup_id))
            # Remove from scheduler
            try:
                from scheduler import get_scheduler  # noqa: PLC0415

                sched_obj = get_scheduler()
                if sched_obj:
                    for prefix in ("schedule_", "reminder_schedule_", "weekend_reminder_schedule_"):
                        try:
                            sched_obj.remove_job(f"{prefix}{team_id}_{standup_id}")
                        except Exception:
                            pass
            except Exception:
                pass
            # Refresh App Home (respects configure mode)
            _refresh_home(team_id, user_id, client)
        except Exception as exc:
            logger.warning("delete_standup_button error: %s", exc)

    @app.action("standup_overflow")
    def handle_standup_overflow(ack, body, client):  # noqa: ANN001
        """Handle overflow menu or button clicks on App Home standup cards."""
        ack()
        action = body["actions"][0]
        # Support both overflow menu (selected_option.value) and button (value)
        action_value = action.get("value", "") or action.get("selected_option", {}).get("value", "")
        user_id = body["user"]["id"]
        team_id = body["user"]["team_id"]

        if action_value.startswith("delete_"):
            standup_id = action_value.split("_", 1)[1]
            try:
                import db  # noqa: PLC0415

                db.delete_standup_schedule(team_id, int(standup_id))
                _refresh_home(team_id, user_id, client)
            except Exception as exc:
                logger.warning("overflow delete error: %s", exc)
        elif action_value.startswith("pause_"):
            standup_id = action_value.split("_", 1)[1]
            try:
                import db  # noqa: PLC0415

                db.update_standup_schedule(team_id, int(standup_id), active=False)
                # Remove from scheduler
                try:
                    from scheduler import get_scheduler  # noqa: PLC0415

                    sched_obj = get_scheduler()
                    if sched_obj:
                        for prefix in ("schedule_", "reminder_schedule_", "weekend_reminder_schedule_"):
                            try:
                                sched_obj.remove_job(f"{prefix}{team_id}_{standup_id}")
                            except Exception:
                                pass
                except Exception:
                    pass
                _refresh_home(team_id, user_id, client)
            except Exception as exc:
                logger.warning("overflow pause error: %s", exc)
        elif action_value.startswith("enable_"):
            standup_id = action_value.split("_", 1)[1]
            try:
                import db  # noqa: PLC0415

                schedule = db.update_standup_schedule(team_id, int(standup_id), active=True)
                # Re-register in scheduler
                if schedule:
                    try:
                        from scheduler import get_scheduler, register_schedule_job  # noqa: PLC0415

                        inst = db.get_installation(team_id)
                        sched_obj = get_scheduler()
                        if inst and sched_obj:
                            sched_with_token = dict(schedule)
                            sched_with_token["bot_token"] = inst["bot_token"]
                            register_schedule_job(sched_obj, sched_with_token)
                    except Exception:
                        pass
                _refresh_home(team_id, user_id, client)
            except Exception as exc:
                logger.warning("overflow enable error: %s", exc)
        elif action_value.startswith("edit_"):
            standup_id = action_value.split("_", 1)[1]
            # Trigger the edit flow
            body["actions"][0]["value"] = standup_id
            handle_edit_standup_button(lambda: None, body, client)

    @app.event("app_mention")
    def handle_mention(event, say):  # noqa: ANN001
        say(
            "👋 I'm Morgenruf, your standup bot! Use `/help` to see available commands or check your *App Home* tab for settings and history."
        )

    @app.event("member_joined_channel")
    def handle_member_joined(event, client):  # noqa: ANN001
        """Welcome new members and register them for standups."""
        user_id: str = event.get("user", "")
        team_id: str = event.get("team", "")
        if not user_id or not team_id:
            return
        try:
            import db  # noqa: PLC0415

            user_info = client.users_info(user=user_id).get("user", {})
            profile = user_info.get("profile", {})
            db.upsert_member(
                team_id=team_id,
                user_id=user_id,
                real_name=profile.get("real_name", ""),
                email=profile.get("email", ""),
                tz=user_info.get("tz", "UTC"),
            )
            client.chat_postMessage(
                channel=user_id,
                text=(
                    "👋 Welcome to the team! I'm Morgenruf, your daily standup bot.\n\n"
                    "I'll DM you each morning with a few quick questions to share with your team. "
                    "Use `/standup` to try a standup now, or `/help` to learn more."
                ),
            )
        except Exception as exc:
            logger.warning("member_joined_channel error: %s", exc)

    @app.message("help")
    def handle_help(message, say):  # noqa: ANN001
        if message.get("channel_type") != "im":
            return
        say(
            "🤖 *Standup Bot Help*\n\n"
            "I'll ask you your team's standup questions at the scheduled time. "
            "Type `standup` to start now. 🚀\n\n"
            "*Commands:*\n"
            "• `standup` — start a standup manually\n"
            "• `skip` — skip today's standup\n"
            "• `timezone <tz>` — set your timezone (e.g. `timezone America/New_York`)\n"
            "• `kudos @teammate Great job!` — recognise a teammate 🏆\n"
            "• `help` — show this message"
        )

    @app.message("standup")
    def handle_manual_standup(message, say, client):  # noqa: ANN001
        """Allow team members to trigger their own standup manually."""
        if message.get("channel_type") != "im":
            return
        user_id: str = message["user"]
        team_id: str = message.get("team", "")
        _start_standup_session(user_id, team_id, client)

    @app.action(re.compile(r"submit_answer_\d+"))
    def handle_submit_answer(ack, body, client):  # noqa: ANN001
        """Handle Submit button click for each standup question.

        The typed answer lives in body['state']['values'][block_id][action_id]['value']
        because the dispatching element is the button, not the input itself.
        """
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        action = body["actions"][0]
        try:
            step = int(action.get("value", "0"))
        except (TypeError, ValueError):
            step = 0

        block_id = f"answer_{step}"
        input_action_id = f"standup_answer_{step}"
        answer = ""
        try:
            import blocks as _blocks  # noqa: PLC0415

            field = body.get("state", {}).get("values", {}).get(block_id, {}).get(input_action_id, {})
            rt = field.get("rich_text_value")
            answer = _blocks.rich_text_to_mrkdwn(rt) if rt else (field.get("value") or "")
        except Exception as e:
            logger.warning("submit_answer: could not read input value: %s", e)

        cache_key = f"{team_id}:{user_id}"
        session = state_store.get(cache_key)
        if not session:
            client.chat_postMessage(
                channel=user_id,
                text="⚠️ Your standup session expired. Run `/standup` to start a new one.",
            )
            return

        session = state_store.record_answer(cache_key, answer)
        n_questions = len(session.questions)

        if session.step < n_questions:
            _send_question_block(
                client,
                user_id,
                session.questions[session.step],
                session.step,
                _initial_answer_for(session, session.step),
            )
        elif session.step == n_questions:
            # All main questions answered — ask mood
            _send_mood_block(client, user_id)
        # else: mood comes via button click or plain-text DM fallback

    # Backwards-compat: older messages still in user DMs use the old action_id
    # via dispatch_action. Accept those events so they don't 404 against Bolt.
    @app.action(re.compile(r"standup_answer_\d+"))
    def handle_standup_answer_legacy(ack):  # noqa: ANN001
        ack()

    @app.action(re.compile(r"mood_(great|okay|rough)"))
    def handle_mood_button(ack, body, client):  # noqa: ANN001
        """Handle mood button click to finalize standup."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        mood: str = body["actions"][0].get("value", "")

        cache_key = f"{team_id}:{user_id}"
        session = state_store.get(cache_key)
        if not session:
            return

        session = state_store.record_answer(cache_key, mood)
        _complete_standup(user_id, session, client)

    @app.command("/standup")
    def handle_standup_command(ack, body, client):  # noqa: ANN001
        """Slash command to start a standup session."""
        ack()
        user_id: str = body["user_id"]
        team_id: str = body["team_id"]
        _start_standup_session(user_id, team_id, client)

    @app.command("/skip")
    def handle_skip_command(ack, body, client):  # noqa: ANN001
        """Slash command to skip today's standup."""
        ack()
        user_id: str = body["user_id"]
        team_id: str = body["team_id"]
        try:
            import db  # noqa: PLC0415

            db.skip_today(team_id, user_id)
        except Exception as e:
            logger.warning("Unexpected error in handle_skip_action recording skip: %s", e)
        cache_key = f"{team_id}:{user_id}"
        state_store.clear(cache_key)
        client.chat_postMessage(channel=user_id, text="✅ Got it! You've skipped today's standup. See you tomorrow! 👋")

    @app.command("/help")
    def handle_help_command(ack, body, client):  # noqa: ANN001
        """Slash command to show available commands and help."""
        ack()
        user_id: str = body["user_id"]
        client.chat_postMessage(
            channel=user_id,
            text="Morgenruf Help",
            blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "🌅 Morgenruf — Commands"}},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "*Standup commands:*\n"
                            "• `/standup` — Start your standup right now\n"
                            "• `/skip` — Skip today's standup\n"
                            "• `/kudos @teammate message` — Give a shoutout\n"
                            "• `/help` — Show this message\n\n"
                            "*Other ways to interact:*\n"
                            "• Reply to a standup DM at any time to start\n"
                            "• Use the *App Home* tab to see your history and settings\n"
                            "• Mention `@Morgenruf` in any channel for help\n\n"
                            "📖 Full docs: <https://docs.morgenruf.dev|docs.morgenruf.dev>"
                        ),
                    },
                },
            ],
        )

    @app.command("/kudos")
    def handle_kudos_command(ack, body, client):  # noqa: ANN001
        """Slash command to give kudos to a teammate."""
        ack()
        user_id: str = body["user_id"]
        team_id: str = body["team_id"]
        text: str = (body.get("text") or "").strip()

        if not text:
            client.chat_postMessage(
                channel=user_id,
                text="Usage: `/kudos @teammate Great job on the release! 🚀`",
            )
            return

        # Parse @mention and message from text (e.g. "@user Great job!")
        mention_match = re.match(r"<@([A-Z0-9]+)(?:\|[^>]*)?>\s+(.+)", text)
        to_user = mention_match.group(1) if mention_match else ""
        kudos_message = mention_match.group(2).strip() if mention_match else text

        try:
            import db  # noqa: PLC0415

            config = db.get_workspace_config(team_id) or {}
            channel_id = config.get("channel_id", "")

            # Persist kudos to database
            if to_user:
                db.save_kudos(team_id, user_id, to_user, kudos_message, channel_id)

            if channel_id:
                client.chat_postMessage(
                    channel=channel_id,
                    text=f"🏆 <@{user_id}> gives kudos: {text}",
                )
            client.chat_postMessage(channel=user_id, text=f"✅ Kudos sent: {text}")
        except Exception as exc:
            logger.warning("kudos command error: %s", exc)
            client.chat_postMessage(channel=user_id, text="❌ Couldn't send kudos. Please try again.")

    @app.view("create_standup_modal")
    def handle_create_standup_modal(ack, body, client):  # noqa: ANN001
        """Handle submission of the create/edit standup modal from App Home."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        values = body["view"]["state"]["values"]
        private_metadata = body["view"].get("private_metadata", "")

        standup_ch = values.get("standup_channel", {}).get("standup_channel", {})
        channel_id = (
            standup_ch.get("selected_option", {}).get("value")
            or standup_ch.get("selected_conversation")
            or standup_ch.get("selected_channel")
            or ""
        )
        questions_text = values.get("questions", {}).get("questions", {}).get("value", "")
        questions = [q.strip() for q in questions_text.split("\n") if q.strip()]
        report_time = (
            values.get("report_time", {}).get("report_time", {}).get("selected_option", {}).get("value", "09:00")
        )
        timezone = values.get("timezone", {}).get("timezone", {}).get("selected_option", {}).get("value", "UTC")
        reminder_val = values.get("reminder", {}).get("reminder", {}).get("selected_option", {}).get("value", "0")
        members = values.get("members", {}).get("members", {}).get("selected_users", [])
        days_opts = values.get("days", {}).get("days", {}).get("selected_options", [])
        days = [o["value"] for o in days_opts]
        report_dest = (
            values.get("report_destination", {})
            .get("report_destination", {})
            .get("selected_option", {})
            .get("value", "channel")
        )
        group_by = values.get("group_by", {}).get("group_by", {}).get("selected_option", {}).get("value", "member")
        standup_name = values.get("standup_name", {}).get("standup_name", {}).get("value", "") or "Team Standup"
        sync_opts = values.get("sync_channel", {}).get("sync_channel", {}).get("selected_options", [])
        sync_with_channel = bool(sync_opts)

        # Prepopulate answers (available in both create and edit)
        prepop_opts = values.get("prepopulate_answers", {}).get("prepopulate_answers", {}).get("selected_options", [])
        prepopulate_answers = bool(prepop_opts)

        # Edit-only fields
        allow_edit_opts = (
            values.get("allow_edit_after_report", {}).get("allow_edit_after_report", {}).get("selected_options", [])
        )
        allow_edit_after_report = bool(allow_edit_opts)
        active_val = (
            values.get("standup_active", {}).get("standup_active", {}).get("selected_option", {}).get("value", "true")
        )

        try:
            import db  # noqa: PLC0415

            kwargs = {
                "name": standup_name,
                "channel_id": channel_id,
                "schedule_time": report_time,
                "schedule_tz": timezone,
                "schedule_days": ",".join(days) if days else "mon,tue,wed,thu,fri",
                "questions": questions,
                "participants": members,
                "reminder_minutes": int(reminder_val),
                "post_to_thread": report_dest == "thread",
                "group_by": group_by,
                "sync_with_channel": sync_with_channel,
                "prepopulate_answers": prepopulate_answers,
            }

            if private_metadata:
                # Editing existing schedule — include edit-only fields
                kwargs["allow_edit_after_report"] = allow_edit_after_report
                kwargs["active"] = active_val == "true"
                schedule = db.update_standup_schedule(team_id, int(private_metadata), **kwargs)
            else:
                # Creating new schedule
                schedule = db.create_standup_schedule(team_id, **kwargs)

            # Register/update in scheduler
            if schedule:
                try:
                    from scheduler import get_scheduler, register_schedule_job  # noqa: PLC0415

                    inst = db.get_installation(team_id)
                    sched_obj = get_scheduler()
                    if inst and sched_obj:
                        sched_with_token = dict(schedule)
                        sched_with_token["bot_token"] = inst["bot_token"]
                        register_schedule_job(sched_obj, sched_with_token)
                except Exception as exc2:
                    logger.warning("Could not register schedule job from modal: %s", exc2)

                # Ensure members are in the DB
                for uid in members:
                    try:
                        user_info = client.users_info(user=uid).get("user", {})
                        profile = user_info.get("profile", {})
                        db.upsert_member(
                            team_id=team_id,
                            user_id=uid,
                            real_name=profile.get("real_name", ""),
                            email=profile.get("email", ""),
                            tz=user_info.get("tz", "UTC"),
                        )
                    except Exception:
                        pass

            # Refresh App Home (respects configure mode)
            _refresh_home(team_id, user_id, client)
        except Exception as exc:
            logger.error("create_standup_modal error: %s", exc)

    @app.view("standup_form_modal")
    def handle_standup_form_submit(ack, body, client):  # noqa: ANN001
        """Handle submission of the fill-in standup form modal."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        values = body["view"]["state"]["values"]
        cache_key = body["view"].get("private_metadata", f"{team_id}:{user_id}")

        session = state_store.get(cache_key)
        if not session:
            client.chat_postMessage(
                channel=user_id,
                text="⚠️ Your standup session expired. Run `/standup` to start a new one.",
            )
            return

        # Collect answers from all question fields (rich_text_input)
        import blocks as _blocks  # noqa: PLC0415

        for i in range(len(session.questions)):
            block_id = f"question_{i}"
            action_id = f"answer_{i}"
            field = values.get(block_id, {}).get(action_id, {})
            # rich_text_input → rich_text_value; fallback to plain value
            rt = field.get("rich_text_value")
            answer = _blocks.rich_text_to_mrkdwn(rt) if rt else field.get("value", "")
            session = state_store.record_answer(cache_key, answer)

        # Ask mood after form submission
        _send_mood_block(client, user_id)

    @app.action("standup_edit")
    def handle_standup_edit(ack, body, say, client):  # noqa: ANN001
        """Handle 'Edit my standup' button — re-open DM session for edits."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body.get("team", {}).get("id", "")
        standup_id_str: str = body.get("actions", [{}])[0].get("value", "")

        try:
            standup_id = int(standup_id_str)
        except (ValueError, TypeError):
            say("⚠️ Could not identify your standup. Please try again.")
            return

        if not can_edit_response(team_id, user_id, standup_id):
            say("⏰ Sorry, the edit window for your standup has closed.")
            return

        cache_key = f"{team_id}:{user_id}"
        channel = ""
        questions = None
        schedule_id: int | None = None
        standup_name = "Team Standup"
        try:
            import db  # noqa: PLC0415

            # Resolve the user's schedule first so edits post to the same
            # channel as the original standup (see _start_standup_session).
            sched = db.get_schedule_for_user(team_id, user_id)
            if sched:
                channel = sched.get("channel_id", "") or ""
                qs = sched.get("questions") or []
                schedule_id = sched.get("id")
                standup_name = sched.get("name") or standup_name
            else:
                config = db.get_workspace_config(team_id) or {}
                channel = config.get("channel_id", "")
                qs = config.get("questions") or []

            if isinstance(qs, str):
                import json as _json

                try:
                    qs = _json.loads(qs)
                except Exception:
                    qs = []
            if qs:
                questions = qs
        except Exception as e:
            logger.warning("Unexpected error in handle_edit_standup loading config: %s", e)

        # Load the user's previous answers so each question block pre-fills
        # with what they submitted — requested by users who didn't want to
        # retype everything just to correct a typo.
        initial_answers: list[str] = []
        try:
            import db  # noqa: PLC0415

            prev = db.get_standup_by_id(standup_id)
            if prev:
                initial_answers = [
                    prev.get("yesterday") or "",
                    prev.get("today") or "",
                    prev.get("blockers") or "",
                ]
        except Exception as e:
            logger.warning("Could not load previous standup %s for edit: %s", standup_id, e)

        session = state_store.start(
            cache_key,
            channel,
            team_id=team_id,
            questions=questions,
            standup_name=standup_name,
            schedule_id=schedule_id,
            editing_standup_id=standup_id,
            edit_initial_answers=initial_answers,
        )
        client.chat_postMessage(
            channel=user_id,
            text="✏️ Let's update your standup — your previous answers are pre-filled, edit what you need.",
        )
        _send_question_block(client, user_id, session.questions[0], 0, _initial_answer_for(session, 0))

    @app.message("skip")
    def handle_skip(message, say):  # noqa: ANN001
        """Allow users to skip today's standup."""
        if message.get("channel_type") != "im":
            return
        user_id = message["user"]
        team_id = message.get("team", "")
        try:
            import db  # noqa: PLC0415

            db.skip_today(team_id, user_id)
        except Exception as e:
            logger.warning("Unexpected error in handle_skip recording skip: %s", e)
        # Also clear any active session
        cache_key = f"{team_id}:{user_id}"
        state_store.clear(cache_key)
        say("✅ Got it! You've skipped today's standup. See you tomorrow! 👋")

    @app.message(re.compile(r"i'?m back(?: from vacation)?|back from vacation|im back", re.IGNORECASE))
    def handle_back_from_vacation(message, say):  # noqa: ANN001
        """Handle messages indicating the user is back from vacation."""
        if message.get("channel_type") != "im":
            return
        user_id = message["user"]
        team_id = message.get("team", "")
        try:
            import db  # noqa: PLC0415

            db.set_vacation(team_id, user_id, False)
        except Exception as e:
            logger.warning("Unexpected error in handle_back_from_vacation clearing vacation: %s", e)
        say("🎉 Welcome back! You're all set for standups again.")

    @app.message(
        re.compile(r"i'?m (?:going on vacation|away|on vacation)|going on vacation|on vacation", re.IGNORECASE)
    )
    def handle_going_on_vacation(message, say):  # noqa: ANN001
        """Handle messages indicating the user is going on vacation."""
        if message.get("channel_type") != "im":
            return
        user_id = message["user"]
        team_id = message.get("team", "")
        try:
            import db  # noqa: PLC0415

            db.set_vacation(team_id, user_id, True)
        except Exception as e:
            logger.warning("Unexpected error in handle_going_on_vacation setting vacation: %s", e)
        say("🌴 Enjoy your vacation! I won't bother you until you're back. Message me *I'm back* when you return.")

    @app.message(re.compile(r"^kudos\s+<@([A-Z0-9]+)>\s+(.+)$", re.IGNORECASE))
    def handle_kudos(message, say, client, context, logger):
        """Handle kudos messages: kudos <@USER> Great work!"""
        from_user = message["user"]
        team_id = message.get("team", "")
        to_user = context["matches"][0]
        kudos_message = context["matches"][1].strip()
        channel_type = message.get("channel_type", "")
        channel_id = message.get("channel", "")

        if from_user == to_user:
            say("😄 Nice try, but you can't give kudos to yourself!")
            return

        try:
            import db  # noqa: PLC0415

            db.save_kudos(team_id, from_user, to_user, kudos_message, channel_id)
        except Exception as exc:
            logger.warning("Could not save kudos: %s", exc)

        kudos_card = f"🏆 *Kudos!*\n\n<@{from_user}> gave kudos to <@{to_user}>\n\n> {kudos_message}"

        try:
            if channel_type == "im":
                try:
                    import db  # noqa: PLC0415

                    config = db.get_workspace_config(team_id) or {}
                    post_channel = config.get("channel_id", "")
                    if post_channel:
                        client.chat_postMessage(channel=post_channel, text=kudos_card)
                        say(f"✅ Kudos posted to <#{post_channel}>! 🎉")
                    else:
                        say(kudos_card + "\n\n_(Configure a standup channel in the dashboard to post kudos there)_")
                except Exception:
                    say(kudos_card)
            else:
                client.chat_postMessage(channel=channel_id, text=kudos_card)
        except Exception as exc:
            logger.error("Failed to post kudos: %s", exc)
            say(f"✅ Kudos saved! <@{to_user}> has been recognised. 🎉")

    @app.message(re.compile(r"^timezone\s+(\S+)$", re.IGNORECASE))
    def handle_set_timezone(message, say, context):  # noqa: ANN001
        """Allow users to set their personal timezone."""
        if message.get("channel_type") != "im":
            return
        user_id = message["user"]
        team_id = message.get("team", "")
        tz_str = context["matches"][0]
        try:
            pytz.timezone(tz_str)  # validate
        except Exception:
            say(
                f"❌ Unknown timezone `{tz_str}`. Use a TZ name like `America/New_York` or `Europe/London`.\n"
                "See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
            )
            return
        try:
            import db  # noqa: PLC0415

            db.upsert_member(team_id, user_id, tz=tz_str)
        except Exception as exc:
            say(f"⚠️ Could not save timezone: {exc}")
            return
        say(f"✅ Your timezone has been updated to *{tz_str}*.")
