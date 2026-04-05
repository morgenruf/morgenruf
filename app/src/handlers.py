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

_MOOD_QUESTION = "🎭 *How are you feeling today?* _(😊 great · 😐 okay · 😔 rough — or type anything)_"


def _format_standup(user_id: str, answers: list[str], mood: str | None = None) -> str:
    """Format collected answers into a structured standup post."""
    date_str = datetime.utcnow().strftime("%B %d, %Y")
    yesterday = answers[0] if len(answers) > 0 else "—"
    today = answers[1] if len(answers) > 1 else "—"
    blockers = answers[2] if len(answers) > 2 else "—"

    blocker_text = (
        "_None_ ✅"
        if blockers.strip().lower() in ("none", "no", "nope", "-", "n/a", "")
        else blockers
    )

    text = (
        f"📋 *Standup from <@{user_id}>* — {date_str}\n\n"
        f"*✅ Yesterday:*\n{yesterday}\n\n"
        f"*🎯 Today:*\n{today}\n\n"
        f"*🚧 Blockers:*\n{blocker_text}"
    )
    if mood:
        text += f"\n\n*🎭 Mood:* {mood}"
    return text


def _persist_standup(team_id: str, user_id: str, answers: list[str], mood: str | None = None) -> None:
    """Best-effort persist to DB; log and continue on failure."""
    try:
        import db  # noqa: PLC0415
        db.save_standup(
            team_id=team_id,
            user_id=user_id,
            yesterday=answers[0] if len(answers) > 0 else "",
            today=answers[1] if len(answers) > 1 else "",
            blockers=answers[2] if len(answers) > 2 else "",
            mood=mood,
        )
    except Exception as exc:
        logger.warning("Could not persist standup for %s/%s: %s", team_id, user_id, exc)


def _send_question_block(client, user_id: str, question: str, step: int) -> None:
    """Send a standup question as a Block Kit input block with dispatch_action."""
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
                "element": {
                    "type": "plain_text_input",
                    "action_id": f"standup_answer_{step}",
                    "placeholder": {"type": "plain_text", "text": "Type your answer..."},
                    "multiline": True,
                },
                "label": {"type": "plain_text", "text": "Your answer"},
            },
        ],
    )


def _start_standup_session(user_id: str, team_id: str, client) -> None:
    """Look up workspace config, create a session, and send the first question block."""
    cache_key = f"{team_id}:{user_id}"
    if state_store.is_active(cache_key):
        client.chat_postMessage(
            channel=user_id,
            text="You already have an active standup session. Answer the current question or wait for it to reset.",
        )
        return

    channel = ""
    questions = None
    try:
        import db  # noqa: PLC0415
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
    except Exception:
        pass

    session = state_store.start(cache_key, channel, team_id=team_id, questions=questions)
    client.chat_postMessage(channel=user_id, text="📋 Starting your standup!")
    _send_question_block(client, user_id, session.questions[0], 0)


def _complete_standup(user_id: str, session, client) -> None:
    """Finalize a completed standup: send Block Kit confirmation, post to channel, persist, fire events."""
    n_questions = len(session.questions)
    question_answers = session.answers[:n_questions]
    mood = session.answers[n_questions] if len(session.answers) > n_questions else None

    # Block Kit confirmation with edit button
    client.chat_postMessage(
        channel=user_id,
        text="✅ Standup submitted!",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ *Standup submitted!* You can edit your responses within 30 minutes.",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✏️ Edit responses"},
                        "action_id": "edit_standup",
                        "style": "primary",
                    }
                ],
            },
        ],
    )

    formatted = _format_standup(user_id, question_answers, mood=mood)
    channel = session.channel
    if channel:
        try:
            try:
                import db as _db  # noqa: PLC0415
                from autolink import autolink  # noqa: PLC0415
                cfg = _db.get_workspace_config(session.team_id) or {}
                formatted = autolink(formatted, cfg)
            except Exception:
                pass
            client.chat_postMessage(channel=channel, text=formatted)
            logger.info("Posted standup for %s to %s", user_id, channel)
        except Exception as exc:
            logger.error("Failed to post standup for %s: %s", user_id, exc)
            client.chat_postMessage(
                channel=user_id,
                text=f"⚠️ Could not post to channel — please paste manually:\n\n{formatted}",
            )

    _persist_standup(session.team_id, user_id, question_answers, mood=mood)
    state_store.clear(f"{session.team_id}:{user_id}")

    fire_webhooks(session.team_id, "standup.completed", {
        "team_id": session.team_id,
        "user_id": user_id,
        "answers": {
            "yesterday": question_answers[0] if len(question_answers) > 0 else "",
            "today": question_answers[1] if len(question_answers) > 1 else "",
            "blockers": question_answers[2] if len(question_answers) > 2 else "",
        },
        "mood": mood,
        "timestamp": datetime.utcnow().isoformat(),
    })

    try:
        import db as _db  # noqa: PLC0415
        from ai_summary import generate_summary  # noqa: PLC0415
        config = _db.get_workspace_config(session.team_id) or {}
        if config.get("ai_summary_enabled") and channel:
            today_standups = _db.get_today_standups(session.team_id)
            active_members = _db.get_active_members(session.team_id)
            submitted_users = {s["user_id"] for s in today_standups}
            all_submitted = all(m["user_id"] in submitted_users for m in active_members)
            if all_submitted and len(today_standups) > 1:
                inst = _db.get_installation(session.team_id)
                team_name = (inst or {}).get("team_name", "")
                summary_text = generate_summary(today_standups, team_name)
                if summary_text:
                    client.chat_postMessage(
                        channel=channel,
                        text=f"✨ *AI Summary*\n\n{summary_text}",
                    )
    except Exception as exc:
        logger.warning("AI summary failed: %s", exc)

    try:
        from workflow import evaluate_rules  # noqa: PLC0415
        blocker_text = question_answers[2] if len(question_answers) > 2 else ""
        has_blockers = bool(blocker_text.strip())
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
                hook["webhook_url"], event_type, resp.status_code,
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
            _send_question_block(client, user_id, session.questions[session.step], session.step)
        elif session.step == n_questions:
            # All questions answered — ask mood (plain text, no block needed)
            say(_MOOD_QUESTION)
        else:
            # Mood answered — finalize
            _complete_standup(user_id, session, client)

    @app.event("app_home_opened")
    def handle_app_home(event, client):  # noqa: ANN001
        """Render the App Home tab when a user opens it."""
        user_id = event["user"]
        team_id = event.get("team", "")

        workspace_name = ""
        channel_name = ""
        standup_time = ""
        try:
            import db  # noqa: PLC0415
            config = db.get_workspace_config(team_id) or {}
            channel_name = config.get("channel_id", "")
            standup_time = config.get("standup_time", "")
            info = client.team_info()
            workspace_name = info.get("team", {}).get("name", "")
        except Exception:
            pass

        status_text = (
            f"✅ Active — posting to <#{channel_name}> at *{standup_time}*"
            if channel_name and standup_time
            else "⚠️ Not configured — visit the dashboard to set up your standup."
        )

        try:
            client.views_publish(
                user_id=user_id,
                view={
                    "type": "home",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "☀️ Morgenruf Standup Bot"},
                        },
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"*Workspace:* {workspace_name or team_id}\n"
                                    f"*Status:* {status_text}"
                                ),
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Quick actions*\nSend me `standup` in a DM to start your standup manually.",
                            },
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "🔧 Open Dashboard"},
                                    "url": "https://api.morgenruf.dev/dashboard",
                                    "action_id": "open_dashboard",
                                }
                            ],
                        },
                    ],
                },
            )
        except Exception as exc:
            logger.warning("Failed to publish App Home for %s: %s", user_id, exc)

    @app.event("app_mention")
    def handle_mention(event, say):  # noqa: ANN001
        say("👋 I'm the standup bot! I'll DM you at your team's standup time. Type `help` in a DM to me for more info.")

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

    @app.action(re.compile(r"standup_answer_\d+"))
    def handle_standup_answer(ack, body, client):  # noqa: ANN001
        """Handle Block Kit input submission for each standup question."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        action = body["actions"][0]
        answer: str = action.get("value", "")

        cache_key = f"{team_id}:{user_id}"
        session = state_store.get(cache_key)
        if not session:
            return

        session = state_store.record_answer(cache_key, answer)
        n_questions = len(session.questions)

        if session.step < n_questions:
            _send_question_block(client, user_id, session.questions[session.step], session.step)
        elif session.step == n_questions:
            # All main questions answered — ask mood as plain text
            client.chat_postMessage(channel=user_id, text=_MOOD_QUESTION)
        # else: mood comes via plain-text DM (handle_dm fallback)

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
        except Exception:
            pass
        cache_key = f"{team_id}:{user_id}"
        state_store.clear(cache_key)
        client.chat_postMessage(channel=user_id, text="✅ Got it! You've skipped today's standup. See you tomorrow! 👋")

    @app.action("edit_standup")
    def handle_edit_standup(ack, body, client):  # noqa: ANN001
        """Handle 'Edit responses' button — open a pre-filled modal within the 30-minute window."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]

        import db  # noqa: PLC0415
        standup = db.get_latest_standup(user_id, team_id)
        if not standup:
            client.chat_postMessage(channel=user_id, text="No standup found to edit.")
            return

        submitted = standup.get("submitted_at")
        if submitted:
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - submitted > timedelta(minutes=30):
                client.chat_postMessage(
                    channel=user_id,
                    text="⏰ Edit window has closed (30 minutes after submission).",
                )
                return

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "edit_standup_modal",
                "title": {"type": "plain_text", "text": "Edit Standup"},
                "submit": {"type": "plain_text", "text": "Save"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "q1",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "answer",
                            "initial_value": standup.get("yesterday") or "",
                            "multiline": True,
                        },
                        "label": {"type": "plain_text", "text": "Yesterday"},
                    },
                    {
                        "type": "input",
                        "block_id": "q2",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "answer",
                            "initial_value": standup.get("today") or "",
                            "multiline": True,
                        },
                        "label": {"type": "plain_text", "text": "Today"},
                    },
                    {
                        "type": "input",
                        "block_id": "q3",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "answer",
                            "initial_value": standup.get("blockers") or "",
                            "multiline": True,
                        },
                        "label": {"type": "plain_text", "text": "Blockers"},
                    },
                ],
            },
        )

    @app.view("edit_standup_modal")
    def handle_edit_modal_submit(ack, body, client):  # noqa: ANN001
        """Handle modal submission for standup editing."""
        ack()
        user_id: str = body["user"]["id"]
        team_id: str = body["team"]["id"]
        values = body["view"]["state"]["values"]
        yesterday = values["q1"]["answer"]["value"] or ""
        today = values["q2"]["answer"]["value"] or ""
        blockers = values["q3"]["answer"]["value"] or ""
        import db  # noqa: PLC0415
        db.update_standup(user_id, team_id, yesterday=yesterday, today=today, blockers=blockers)
        client.chat_postMessage(channel=user_id, text="✅ Standup updated!")

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
        try:
            import db  # noqa: PLC0415
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
        except Exception:
            pass

        session = state_store.start(cache_key, channel, team_id=team_id, questions=questions)
        say(f"✏️ Let's update your standup!\n\n{session.questions[0]}")

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
        except Exception:
            pass
        # Also clear any active session
        cache_key = f"{team_id}:{user_id}"
        state_store.clear(cache_key)
        say("✅ Got it! You've skipped today's standup. See you tomorrow! 👋")

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

        kudos_card = (
            f"🏆 *Kudos!*\n\n"
            f"<@{from_user}> gave kudos to <@{to_user}>\n\n"
            f"> {kudos_message}"
        )

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
