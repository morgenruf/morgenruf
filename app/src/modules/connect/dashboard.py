"""Connect HTTP API.

Built inside register_routes rather than at import time, so importing the
registry does not pull core's dashboard in as a side effect.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_routes(flask_app) -> None:
    from flask import Blueprint, jsonify, request, session

    import src.core.db as db
    import src.modules.connect.db as cdb
    from src.core.dashboard import _admin_required, _login_required
    from src.core.roster import eligible_members
    from src.modules.connect.rounds import match_status

    bp = Blueprint("connect", __name__)

    @bp.route("/dashboard/api/connect/programs", methods=["GET"])
    @_login_required
    def list_programs():
        team_id = session["team_id"]
        try:
            programs = cdb.get_programs(team_id)
        except Exception as exc:
            logger.warning("connect list_programs: %s", exc)
            return jsonify([])
        for p in programs:
            p["created_at"] = p["created_at"].isoformat() if p.get("created_at") else None
            p["last_round"] = p["last_round"].isoformat() if p.get("last_round") else None
            try:
                # The same intersection the round itself does: people in the
                # channel who are also eligible and have not opted out.
                # Counting the whole workspace claimed a pool nobody would be
                # matched from.
                from slack_sdk import WebClient  # noqa: PLC0415

                import src.modules.connect.slack_api as api  # noqa: PLC0415

                inst = db.get_installation(team_id) or {}
                token = inst.get("bot_token") or ""
                in_channel = set(api.channel_member_ids(WebClient(token=token), p["channel_id"])) if token else None
                eligible = {m.user_id for m in eligible_members(team_id)}
                opted_out = cdb.optout_user_ids(team_id, p["id"])
                pool = eligible if in_channel is None else (eligible & in_channel)
                p["pool_size"] = len(pool - opted_out)
            except Exception as exc:
                # Slack being unreachable is not a reason to fail the page; the
                # number is simply unknown rather than wrong.
                logger.info("connect: could not size the pool for %s: %s", p["id"], exc)
                p["pool_size"] = None
        return jsonify(programs)

    @bp.route("/dashboard/api/connect/programs", methods=["POST"])
    @_admin_required
    def create_program():
        team_id = session["team_id"]
        data = request.get_json(silent=True) or {}
        channel_id = (data.get("channel_id") or "").strip()
        if not channel_id:
            return jsonify({"error": "Pick a channel to draw people from"}), 400
        try:
            interval = int(data.get("interval_weeks", 1))
        except (TypeError, ValueError):
            return jsonify({"error": "Cadence must be a number of weeks"}), 400
        if interval < 1 or interval > 8:
            return jsonify({"error": "Cadence must be between 1 and 8 weeks"}), 400
        program = cdb.create_program(
            team_id=team_id,
            channel_id=channel_id,
            name=(data.get("name") or "Coffee chats").strip()[:80],
            interval_weeks=interval,
            day_of_week=int(data.get("day_of_week", 1)),
            hour=int(data.get("hour", 10)),
            minute=int(data.get("minute", 0)),
            timezone=(data.get("timezone") or "UTC").strip(),
        )
        program["created_at"] = program["created_at"].isoformat() if program.get("created_at") else None
        return jsonify(program)

    @bp.route("/dashboard/api/connect/programs/<int:program_id>", methods=["POST"])
    @_admin_required
    def update_program(program_id: int):
        team_id = session["team_id"]
        data = request.get_json(silent=True) or {}
        cdb.set_program_enabled(team_id, program_id, bool(data.get("enabled")))
        return jsonify({"id": program_id, "enabled": bool(data.get("enabled"))})

    @bp.route("/dashboard/api/connect/programs/<int:program_id>", methods=["DELETE"])
    @_admin_required
    def delete_program(program_id: int):
        team_id = session["team_id"]
        if not cdb.delete_program(team_id, program_id):
            return jsonify({"error": "not found"}), 404
        return jsonify({"deleted": program_id})

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/run", methods=["POST"])
    @_admin_required
    def run_now(program_id: int):
        """Start a round immediately, rather than waiting for the cadence.

        Without this a programme could not be tried at all until its scheduled
        day came round, which is a poor way to find out whether it works.
        """
        team_id = session["team_id"]
        if not cdb.owns_program(team_id, program_id):
            return jsonify({"error": "not found"}), 404
        try:
            from src.modules.connect.jobs import run_round  # noqa: PLC0415

            run_round(program_id, force=True)
        except Exception as exc:
            logger.exception("connect run_now failed for %s", program_id)
            return jsonify({"error": str(exc)}), 500
        rounds = cdb.recent_rounds(team_id, program_id, 1)
        return jsonify({"started": True, "round": rounds[0]["id"] if rounds else None})

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/rounds", methods=["GET"])
    @_login_required
    def list_rounds(program_id: int):
        team_id = session["team_id"]
        try:
            rounds = cdb.recent_rounds(team_id, program_id)
        except Exception as exc:
            logger.warning("connect list_rounds: %s", exc)
            return jsonify([])
        for r in rounds:
            r["scheduled_for"] = r["scheduled_for"].isoformat() if r.get("scheduled_for") else None
            r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
        return jsonify(rounds)

    @bp.route("/dashboard/api/connect/rounds/<int:round_id>/matches", methods=["GET"])
    @_login_required
    def list_round_matches(round_id: int):
        """Who was put with whom, and whether it happened."""
        team_id = session["team_id"]
        try:
            matches = cdb.round_matches(team_id, round_id)
        except Exception as exc:
            logger.warning("connect list_round_matches: %s", exc)
            return jsonify([])
        out = []
        for m in matches:
            delivered = m.get("delivered_at")
            out.append(
                {
                    "id": m["id"],
                    "members": list(m["member_ids"] or []),
                    "status": match_status(m["met"], delivered),
                    "delivered_at": delivered.isoformat() if delivered else None,
                    "nudged_at": m["nudged_at"].isoformat() if m.get("nudged_at") else None,
                }
            )
        return jsonify(out)

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/participation", methods=["GET"])
    @_login_required
    def program_participation(program_id: int):
        team_id = session["team_id"]
        try:
            rounds = int(request.args.get("rounds", 6))
        except (TypeError, ValueError):
            rounds = 6
        rounds = max(1, min(rounds, 52))
        try:
            rows = cdb.participation(team_id, program_id, rounds)
        except Exception as exc:
            logger.warning("connect participation: %s", exc)
            return jsonify([])
        for r in rows:
            r["last_met"] = r["last_met"].isoformat() if r.get("last_met") else None
        return jsonify(rows)

    flask_app.register_blueprint(bp)
