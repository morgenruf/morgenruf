"""Watercooler HTTP API.

Reading is open to anyone signed in. Every change needs a workspace admin or
a Watercooler admin (the delegable grant), so HR or a team lead can run it
without being a workspace admin. Built inside register_routes, like every
module, so importing the registry does not load core's dashboard.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_routes(flask_app) -> None:
    from flask import jsonify, session
    from flask_smorest import Blueprint

    import src.core.db as db
    import src.modules.watercooler.db as wdb
    from src.core.api import api_errors, register_api_blueprint
    from src.core.api_schemas import Ok
    from src.core.dashboard import _admin_required
    from src.core.schedule_validation import schedule_timezone_error
    from src.core.timezones import canonical_tz
    from src.modules.watercooler import bank, jobs, schemas

    bp = Blueprint("watercooler", __name__)
    module = "watercooler"
    write = [{"sessionCookie": [], "csrfHeader": []}]

    def _error(field: str, message: str, status: int = 400):
        return jsonify({"error": message, "details": {field: [message]}}), status

    def _channel(row: dict) -> dict:
        return {
            "channel_id": row["channel_id"],
            "days": [d for d in (row.get("days") or "").split(",") if d],
            "post_time": row.get("post_time") or wdb.DEFAULT_POST_TIME,
            "timezone": row.get("timezone") or "UTC",
            "source": row.get("source") or wdb.DEFAULT_SOURCE,
            "categories": [c for c in (row.get("categories") or wdb.DEFAULT_CATEGORIES).split(",") if c],
            "active": bool(row.get("active", True)),
            "paused_reason": row.get("paused_reason"),
        }

    def _question(row: dict) -> dict:
        return {"id": int(row["id"]), "text": row["text"], "archived": bool(row.get("archived"))}

    @bp.route("/dashboard/api/watercooler", methods=["GET"])
    @_admin_required("watercooler")
    @bp.doc(operationId="getWatercooler", tags=["Watercooler"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Overview)
    def overview():
        team_id = session["team_id"]
        try:
            hidden = wdb.hidden_keys(team_id)
            return {
                "channels": [_channel(r) for r in wdb.list_channels(team_id)],
                "questions": [_question(r) for r in wdb.list_questions(team_id)],
                "bank": [
                    {"key": q.key, "category": q.category, "text": q.text, "hidden": q.key in hidden}
                    for q in bank.QUESTIONS
                ],
                "categories": [{"key": k, "label": bank.CATEGORY_LABELS[k]} for k in bank.CATEGORIES],
                "can_manage": db.can_administer(team_id, session.get("user_id") or "", module) is True,
                "max_channels": wdb.MAX_CHANNELS,
                "max_questions": wdb.MAX_QUESTIONS,
            }
        except Exception as exc:
            logger.error("watercooler overview: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503

    @bp.route("/dashboard/api/watercooler/channels/<channel_id>", methods=["PUT"])
    @_admin_required("watercooler")
    @bp.doc(operationId="saveWatercoolerChannel", tags=["Watercooler"], security=write)
    @api_errors(bp)
    @bp.arguments(schemas.WatercoolerChannelInput, error_status_code=400)
    @bp.response(200, schemas.Channel)
    def save_channel(data, channel_id: str):
        team_id = session["team_id"]
        if not channel_id.startswith(("C", "G")) or len(channel_id) > 40:
            return _error("channel_id", "Pick a channel.")
        tz = canonical_tz(data.get("timezone") or "")
        problem = schedule_timezone_error(tz)
        if problem:
            return _error("timezone", problem)
        days = ",".join(d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if d in data["days"])
        categories = ",".join(c for c in bank.CATEGORIES if c in data.get("categories") or bank.CATEGORIES)
        try:
            if wdb.get_channel(team_id, channel_id) is None and wdb.count_channels(team_id) >= wdb.MAX_CHANNELS:
                return _error("channel_id", f"Watercooler can run in at most {wdb.MAX_CHANNELS} channels.")
            row = wdb.save_channel(
                team_id,
                channel_id,
                {
                    "days": days,
                    "post_time": data["post_time"],
                    "timezone": tz,
                    "source": data.get("source") or "both",
                    "categories": categories,
                    "active": bool(data.get("active", True)),
                    # Saving is also how a paused channel is resumed.
                    "paused_reason": None,
                },
                created_by=session.get("user_id") or "",
            )
        except Exception as exc:
            logger.error("watercooler save_channel: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return _channel(row)

    @bp.route("/dashboard/api/watercooler/channels/<channel_id>", methods=["DELETE"])
    @_admin_required("watercooler")
    @bp.doc(operationId="deleteWatercoolerChannel", tags=["Watercooler"], security=write)
    @api_errors(bp)
    @bp.response(200, Ok)
    def delete_channel(channel_id: str):
        try:
            removed = wdb.delete_channel(session["team_id"], channel_id)
        except Exception as exc:
            logger.error("watercooler delete_channel: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        if not removed:
            return jsonify({"error": "Not found"}), 404
        return {"ok": True}

    @bp.route("/dashboard/api/watercooler/channels/<channel_id>/post", methods=["POST"])
    @_admin_required("watercooler")
    @bp.doc(operationId="postWatercoolerNow", tags=["Watercooler"], security=write)
    @api_errors(bp)
    @bp.response(200, schemas.PostResult)
    def post_now(channel_id: str):
        """Post today's question now. It counts as today's post, so the scheduled one is skipped."""
        team_id = session["team_id"]
        try:
            if wdb.get_channel(team_id, channel_id) is None:
                return jsonify({"error": "Not found"}), 404
            ts = jobs.run_post(team_id, channel_id, force=True)
        except Exception as exc:
            logger.error("watercooler post_now: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return {"posted": bool(ts)}

    @bp.route("/dashboard/api/watercooler/questions", methods=["POST"])
    @_admin_required("watercooler")
    @bp.doc(operationId="addWatercoolerQuestion", tags=["Watercooler"], security=write)
    @api_errors(bp)
    @bp.arguments(schemas.WatercoolerQuestionInput, error_status_code=400)
    @bp.response(201, schemas.Question)
    def add_question(data):
        team_id = session["team_id"]
        text = " ".join(data["text"].split())
        if len(text) < 5:
            return _error("text", "Write a question of at least 5 characters.")
        try:
            if wdb.count_questions(team_id) >= wdb.MAX_QUESTIONS:
                return _error("text", f"A workspace can have at most {wdb.MAX_QUESTIONS} questions of its own.")
            row = wdb.add_question(team_id, text, session.get("user_id") or "")
        except Exception as exc:
            logger.error("watercooler add_question: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return _question(row), 201

    @bp.route("/dashboard/api/watercooler/questions/<int:question_id>", methods=["PATCH"])
    @_admin_required("watercooler")
    @bp.doc(operationId="updateWatercoolerQuestion", tags=["Watercooler"], security=write)
    @api_errors(bp)
    @bp.arguments(schemas.WatercoolerQuestionUpdate, error_status_code=400)
    @bp.response(200, schemas.Question)
    def update_question(data, question_id: int):
        text = " ".join(data["text"].split()) if "text" in data else None
        if text is not None and len(text) < 5:
            return _error("text", "Write a question of at least 5 characters.")
        try:
            row = wdb.update_question(session["team_id"], question_id, text=text, archived=data.get("archived"))
        except Exception as exc:
            logger.error("watercooler update_question: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        if not row:
            return jsonify({"error": "Not found"}), 404
        return _question(row)

    @bp.route("/dashboard/api/watercooler/bank/<key>", methods=["PUT"])
    @_admin_required("watercooler")
    @bp.doc(operationId="setWatercoolerHidden", tags=["Watercooler"], security=write)
    @api_errors(bp)
    @bp.arguments(schemas.WatercoolerHiddenInput, error_status_code=400)
    @bp.response(200, schemas.BankQuestion)
    def set_hidden(data, key: str):
        question = bank.BY_KEY.get(key)
        if question is None:
            return jsonify({"error": "Not found"}), 404
        try:
            wdb.set_hidden(session["team_id"], key, bool(data["hidden"]))
        except Exception as exc:
            logger.error("watercooler set_hidden: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return {"key": key, "category": question.category, "text": question.text, "hidden": bool(data["hidden"])}

    register_api_blueprint(flask_app, bp)
