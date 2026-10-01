"""Pulse HTTP API.

Built inside register_routes, like every module. The trend goes through
privacy once more on the way out: a round under MIN_GROUP respondents leaves
with its date and counts only, whatever storage handed back.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_HIDDEN_KEYS = ("sent_on", "respondents", "invited")


def public_round(row: dict) -> dict:
    """One trend row for the browser, through the privacy rules once more.

    A round still open, or under MIN_GROUP respondents, leaves with its date
    and counts only. Under MIN_DETAIL the breakdown and eNPS are dropped and
    only the average stays.
    """
    from src.modules.pulse import privacy  # noqa: PLC0415

    respondents = row.get("respondents") or 0
    if row.get("open") or row.get("hidden") or not privacy.visible(respondents):
        return {
            **{k: row.get(k) for k in _HIDDEN_KEYS},
            **privacy.hidden_payload(respondents, open_round=bool(row.get("open"))),
        }
    keep = ["sent_on", "respondents", "invited", "hidden", "includes_enps", "mood_avg"]
    if privacy.detailed(respondents):
        keep += ["mood_dist", "enps"]
    return {k: row.get(k) for k in keep}


def register_routes(flask_app) -> None:
    from flask import jsonify, session
    from flask_smorest import Blueprint

    import src.modules.pulse.db as pdb
    from src.core.api import api_errors, register_api_blueprint
    from src.core.dashboard import _admin_required, _get_bot_token, _login_required
    from src.core.schedule_validation import schedule_timezone_error
    from src.core.timezones import canonical_tz
    from src.modules.pulse import schemas

    bp = Blueprint("pulse", __name__)

    def _settings(program: dict) -> dict:
        return {
            "enabled": bool(program.get("enabled")),
            "day_of_week": int(program.get("day_of_week") or 0),
            "hour": int(program.get("hour") or 0),
            "minute": int(program.get("minute") or 0),
            "timezone": program.get("timezone") or "UTC",
            "audience_channel_id": program.get("audience_channel_id") or None,
            "updated_at": program.get("updated_at"),
        }

    def _error(field: str, message: str):
        return jsonify({"error": message, "details": {field: [message]}}), 400

    @bp.route("/dashboard/api/pulse/settings", methods=["GET"])
    @_login_required
    @bp.doc(operationId="getPulseSettings", tags=["Pulse"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Settings)
    def get_settings():
        try:
            return _settings(pdb.get_program(session["team_id"]))
        except Exception as exc:
            logger.error("pulse get_settings: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503

    @bp.route("/dashboard/api/pulse/settings", methods=["PUT"])
    @_admin_required("pulse")
    @bp.doc(operationId="updatePulseSettings", tags=["Pulse"], security=[{"sessionCookie": [], "csrfHeader": []}])
    @api_errors(bp)
    @bp.arguments(schemas.SettingsInput, error_status_code=400)
    @bp.response(200, schemas.Settings)
    def update_settings(data):
        timezone_name = canonical_tz((data.get("timezone") or "").strip())
        problem = schedule_timezone_error(timezone_name)
        if problem:
            return _error("timezone", problem)
        audience = (data.get("audience_channel_id") or "").strip() or None
        if audience and not audience.startswith(("C", "G")):
            return _error("audience_channel_id", "Choose a channel from the list")
        if audience:
            # The audience is read from the channel's members, which the bot
            # can only do in a channel it is in.
            from slack_sdk import WebClient  # noqa: PLC0415

            from src.core.standup_invites import bot_channel_ids  # noqa: PLC0415

            token = _get_bot_token()
            try:
                if not token:
                    raise RuntimeError("no bot token")
                member = audience in bot_channel_ids(WebClient(token=token))
            except Exception as exc:
                logger.warning("pulse settings could not check the audience channel: %s", exc)
                return jsonify(
                    {"error": "Could not check that channel with Slack just now. Try again in a minute."}
                ), 502
            if not member:
                return _error("audience_channel_id", "Invite @Morgenruf to that channel first")
        fields = {
            "enabled": bool(data["enabled"]),
            "day_of_week": int(data["day_of_week"]),
            "hour": int(data["hour"]),
            "minute": int(data["minute"]),
            "timezone": timezone_name,
            "audience_channel_id": audience,
        }
        try:
            program = pdb.save_program(session["team_id"], fields, updated_by=session.get("user_id") or "")
        except Exception as exc:
            logger.error("pulse update_settings: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return _settings(program)

    @bp.route("/dashboard/api/pulse/trend", methods=["GET"])
    @_login_required
    @bp.doc(operationId="getPulseTrend", tags=["Pulse"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Round(many=True))
    def get_trend():
        """Team results per round, oldest first. Rounds under five carry counts only."""
        # Close what is due before reading, so a round whose tick has not run
        # yet (the module switched off, say) is not shown from live rows.
        try:
            pdb.close_due_rounds(session["team_id"])
        except Exception as exc:
            logger.warning("pulse get_trend could not close due rounds: %s", exc)
        try:
            rows = pdb.trend(session["team_id"])
        except Exception as exc:
            logger.error("pulse get_trend: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return [public_round(row) for row in rows]

    register_api_blueprint(flask_app, bp)
