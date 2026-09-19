"""Kudos HTTP API.

These endpoints moved out of core/dashboard.py. Leaving them there would have
forced core to import a feature module for get_kudos, which the module
contract forbids: core must not know any module by name.

The blueprint and its routes are built inside register_routes rather than at
import time. Importing this module must not pull in src.core.dashboard,
because src.modules imports every module eagerly, and that would make core's
dashboard load as a side effect of touching any module. Tests that stub the
database before importing core.dashboard depend on that not happening.

The routes keep their original paths, so the dashboard front end is unchanged.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_routes(flask_app) -> None:
    """Build the kudos blueprint and attach it to the Flask app."""
    from flask import jsonify, session
    from flask_smorest import Blueprint

    import src.modules.kudos.db as kudos_db
    from src.core import api_schemas as common
    from src.core.api import api_errors, register_api_blueprint
    from src.core.dashboard import _admin_required, _login_required
    from src.modules.kudos import schemas

    kudos_bp = Blueprint("kudos", __name__)

    @kudos_bp.route("/dashboard/api/kudos", methods=["GET"])
    @_login_required
    @kudos_bp.doc(operationId="listKudos", tags=["Kudos"], security=[{"sessionCookie": []}])
    @api_errors(kudos_bp)
    @kudos_bp.arguments(common.LimitQuery, location="query", error_status_code=400)
    @kudos_bp.response(200, schemas.Kudos(many=True))
    def api_list_kudos(query):
        team_id = session["team_id"]
        limit = int(query.get("limit", 50))
        try:
            kudos = kudos_db.get_kudos(team_id, limit)
            for k in kudos:
                if k.get("created_at"):
                    k["created_at"] = k["created_at"].isoformat()
            return kudos
        except Exception as exc:
            logger.warning("api_list_kudos: %s", exc)
            return []

    @kudos_bp.route("/dashboard/api/kudos/leaderboard", methods=["GET"])
    @_login_required
    @kudos_bp.doc(operationId="getLeaderboard", tags=["Kudos"], security=[{"sessionCookie": []}])
    @api_errors(kudos_bp)
    @kudos_bp.arguments(common.DaysQuery, location="query", error_status_code=400)
    @kudos_bp.response(200, schemas.Receiver(many=True))
    def api_kudos_leaderboard(query):
        team_id = session["team_id"]
        days = int(query.get("days", 30))
        try:
            board = kudos_db.get_kudos_leaderboard(team_id, days)
            for row in board:
                if row.get("last_kudos"):
                    row["last_kudos"] = row["last_kudos"].isoformat()
                row["received"] = int(row.get("received") or 0)
            return board
        except Exception as exc:
            logger.warning("api_kudos_leaderboard: %s", exc)
            return []

    @kudos_bp.route("/dashboard/api/kudos/givers", methods=["GET"])
    @_login_required
    @kudos_bp.doc(operationId="getGivers", tags=["Kudos"], security=[{"sessionCookie": []}])
    @api_errors(kudos_bp)
    @kudos_bp.arguments(common.DaysQuery, location="query", error_status_code=400)
    @kudos_bp.response(200, schemas.Giver(many=True))
    def api_kudos_givers(query):
        """Who is doing the recognising. The half most tools leave out."""
        team_id = session["team_id"]
        days = int(query.get("days", 30))
        try:
            board = kudos_db.get_giver_leaderboard(team_id, days)
        except Exception as exc:
            logger.warning("api_kudos_givers: %s", exc)
            return []
        for row in board:
            if row.get("last_given"):
                row["last_given"] = row["last_given"].isoformat()
            row["given"] = int(row.get("given") or 0)
        return board

    @kudos_bp.route("/dashboard/api/kudos/config", methods=["GET"])
    @_login_required
    @kudos_bp.doc(operationId="getConfig", tags=["Kudos"], security=[{"sessionCookie": []}])
    @api_errors(kudos_bp)
    @kudos_bp.response(200, schemas.Config)
    def api_kudos_config():
        return kudos_db.get_config(session["team_id"])

    @kudos_bp.route("/dashboard/api/kudos/config", methods=["POST"])
    @_admin_required("kudos")
    @kudos_bp.doc(operationId="updateConfig", tags=["Kudos"], security=[{"sessionCookie": [], "csrfHeader": []}])
    @api_errors(kudos_bp)
    @kudos_bp.arguments(schemas.ConfigInput, error_status_code=400)
    @kudos_bp.response(200, schemas.Config)
    def api_set_kudos_config(data):

        emoji = (data.get("emoji") or "").strip()
        if not emoji or len(emoji) > 16:
            return jsonify({"error": "Pick a single emoji for your team to give"}), 400
        try:
            allowance = int(data.get("daily_allowance", 5))
        except (TypeError, ValueError):
            return jsonify({"error": "Daily allowance must be a whole number"}), 400
        if allowance < 0 or allowance > 50:
            return jsonify({"error": "Daily allowance must be between 0 and 50"}), 400
        return kudos_db.set_config(session["team_id"], emoji, allowance)

    register_api_blueprint(flask_app, kudos_bp)
