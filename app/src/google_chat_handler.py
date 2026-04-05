"""Google Chat webhook handler."""
from __future__ import annotations

import logging
import os

import db
from flask import Blueprint, jsonify, request
from state import QUESTIONS, state_store

logger = logging.getLogger(__name__)
google_chat_bp = Blueprint("google_chat", __name__)

_MOOD_QUESTION = "🎭 *How are you feeling today?* _(😊 great · 😐 okay · 😔 rough — or type anything)_"
_GC_QUESTIONS = list(QUESTIONS) + [_MOOD_QUESTION]


def _gc_cache_key(team_id: str, user_id: str) -> str:
    return f"{team_id}:{user_id}"


def _get_adapter():
    """Return a GoogleChatAdapter or None if GOOGLE_CREDENTIALS is not set."""
    creds = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not creds:
        return None
    try:
        from adapters.google_chat import GoogleChatAdapter
        return GoogleChatAdapter(creds)
    except Exception as exc:
        logger.error("Failed to init GoogleChatAdapter: %s", exc)
        return None


@google_chat_bp.route("/google/events", methods=["POST"])
def google_events():
    try:
        payload = request.get_json(silent=True) or {}
        event_type = payload.get("type")

        if event_type == "MESSAGE":
            return _handle_message(payload)
        elif event_type == "ADDED_TO_SPACE":
            return jsonify({"text": "👋 Thanks for adding Morgenruf! Use `/standup` to start a standup."})

        return jsonify({}), 200
    except Exception as exc:
        logger.error("Unhandled error in google_events: %s", exc)
        return jsonify({"text": "An internal error occurred."}), 200


def _handle_message(payload: dict):
    sender = payload.get("sender", {})
    user_id = sender.get("name", "")  # "users/USER_ID"
    space = payload.get("space", {})
    space_name = space.get("name", "")
    text = (payload.get("message", {}).get("text", "") or "").strip().lower()

    # Use space name as team identifier for Google Chat
    team_id = space_name.replace("/", "_")
    cache_key = _gc_cache_key(team_id, user_id)

    if text in ("/standup", "standup"):
        session = state_store.start(
            cache_key,
            channel=space_name,
            team_id=team_id,
            questions=_GC_QUESTIONS,
        )
        return jsonify({"text": session.questions[0]})

    elif text in ("/skip", "skip"):
        try:
            db.skip_today(team_id, user_id)
        except Exception as exc:
            logger.warning("Could not skip standup for %s/%s: %s", team_id, user_id, exc)
        return jsonify({"text": "✅ You're skipped for today's standup."})

    elif text.startswith("/help") or text == "help":
        return jsonify({"text": (
            "*Morgenruf Standup Bot* 🌅\n"
            "• `/standup` — start your standup\n"
            "• `/skip` — skip today\n"
            "• `/help` — show this message"
        )})

    # Handle active standup session
    elif state_store.is_active(cache_key):
        session = state_store.record_answer(cache_key, text)
        if session is None:
            return jsonify({"text": "Session error. Please type `/standup` to start again."})

        total_questions = len(session.questions)
        if session.step >= total_questions:
            # Standup complete
            answers = session.answers
            mood = answers[3] if len(answers) > 3 else None
            state_store.clear(cache_key)

            try:
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

            # Post summary to space
            from datetime import datetime
            date_str = datetime.utcnow().strftime("%B %d, %Y")
            summary = (
                f"📋 *Standup from {user_id}* — {date_str}\n\n"
                f"*✅ Yesterday:*\n{answers[0] if len(answers) > 0 else '—'}\n\n"
                f"*🎯 Today:*\n{answers[1] if len(answers) > 1 else '—'}\n\n"
                f"*🚧 Blockers:*\n{answers[2] if len(answers) > 2 else '—'}"
            )
            if mood:
                summary += f"\n\n*🎭 Mood:* {mood}"

            adapter = _get_adapter()
            if adapter:
                try:
                    adapter.post_to_channel(space_name, summary)
                except Exception as exc:
                    logger.warning("Could not post summary to space %s: %s", space_name, exc)

            return jsonify({"text": "✅ Standup submitted! Summary posted to the space."})
        else:
            return jsonify({"text": session.questions[session.step]})

    return jsonify({"text": "Type `/standup` to start your daily standup, or `/help` for commands."})
