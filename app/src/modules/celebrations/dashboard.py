"""Celebrations HTTP API.

Built inside register_routes, like every module, so importing the registry
does not load core's dashboard as a side effect.

Everything that changes something is open to a workspace admin or a
Celebrations admin (the delegable grant), which is how HR runs this without
being a workspace admin. That includes the working week and the holiday list,
which are core's workspace calendar but edited from this page for now.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

UPCOMING_DAYS = 30


def start_background(target, *args) -> None:
    """Run `target` off the request thread. A seam, so tests can run it inline."""
    threading.Thread(target=target, args=args, daemon=True).start()


def _ask_in_background(team_id: str, channel_id: str, user_ids: list[str], names: dict[str, str]) -> None:
    from src.modules.celebrations.jobs import bot_client, send_nudge  # noqa: PLC0415

    client = bot_client(team_id)
    if client is None:
        return
    import time  # noqa: PLC0415

    from src.modules.celebrations.jobs import DM_PAUSE_SECONDS  # noqa: PLC0415

    for index, uid in enumerate(user_ids):
        if index:
            time.sleep(DM_PAUSE_SECONDS)
        send_nudge(client, uid, names.get(uid, ""), channel_id)


def register_routes(flask_app) -> None:
    from datetime import date

    from flask import jsonify, session
    from flask_smorest import Blueprint

    import src.core.db as db
    import src.modules.celebrations.db as cdb
    from src.core.api import api_errors, register_api_blueprint
    from src.core.dashboard import _admin_required, _login_required
    from src.core.schedule_validation import schedule_time_error, schedule_timezone_error
    from src.core.timezones import canonical_tz
    from src.core.workspace_calendar import (
        CalendarError,
        clean_holiday_name,
        format_working_days,
        from_rows,
        parse_working_days,
        read_holiday_csv,
        working_day_keys,
    )
    from src.modules.celebrations import jobs, schemas
    from src.modules.celebrations.messages import nudge_text

    bp = Blueprint("celebrations", __name__)

    def _settings_payload(team_id: str, settings: dict) -> dict:
        return {
            "channel_id": settings.get("channel_id"),
            "timezone": settings.get("timezone"),
            "post_time": settings.get("post_time") or cdb.DEFAULT_POST_TIME,
            "birthdays": bool(settings.get("birthdays", True)),
            "anniversaries": bool(settings.get("anniversaries", True)),
            "banners": bool(settings.get("banners", True)),
            "working_days": working_day_keys(db.get_working_days(team_id)),
            "ready": cdb.is_ready(settings),
            "can_react": jobs.can_react(team_id),
            "updated_at": settings.get("updated_at"),
        }

    def _holidays(team_id: str) -> list[dict]:
        return [{"date": h["date"], "name": h["name"]} for h in db.list_holidays(team_id)]

    def _error(field: str, message: str):
        return jsonify({"error": message, "details": {field: [message]}}), 400

    @bp.route("/dashboard/api/celebrations/settings", methods=["GET"])
    @_login_required
    @bp.doc(operationId="getCelebrationSettings", tags=["Celebrations"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Settings)
    def get_settings():
        team_id = session["team_id"]
        try:
            return _settings_payload(team_id, cdb.get_settings(team_id))
        except Exception as exc:
            logger.error("celebrations get_settings: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503

    @bp.route("/dashboard/api/celebrations/settings", methods=["PUT"])
    @_admin_required("celebrations")
    @bp.doc(
        operationId="updateCelebrationSettings",
        tags=["Celebrations"],
        security=[{"sessionCookie": [], "csrfHeader": []}],
    )
    @api_errors(bp)
    @bp.arguments(schemas.SettingsInput, error_status_code=400)
    @bp.response(200, schemas.Settings)
    def update_settings(data):
        team_id = session["team_id"]
        timezone_name = canonical_tz(data.get("timezone") or "")
        problem = schedule_timezone_error(timezone_name)
        if problem:
            return _error("timezone", problem)
        post_time = (data.get("post_time") or cdb.DEFAULT_POST_TIME).strip()
        problem = schedule_time_error(post_time)
        if problem:
            return _error("post_time", problem)
        try:
            working_days = format_working_days(parse_working_days(data.get("working_days") or []))
        except CalendarError as exc:
            return _error("working_days", str(exc))
        try:
            settings = cdb.save_settings(
                team_id,
                {
                    "channel_id": data["channel_id"].strip(),
                    "timezone": timezone_name,
                    "post_time": post_time,
                    "birthdays": bool(data.get("birthdays", True)),
                    "anniversaries": bool(data.get("anniversaries", True)),
                    "banners": bool(data.get("banners", True)),
                },
                updated_by=session.get("user_id") or "",
            )
            db.set_working_days(team_id, working_days)
        except Exception as exc:
            logger.error("celebrations update_settings: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return _settings_payload(team_id, settings)

    @bp.route("/dashboard/api/celebrations/holidays", methods=["GET"])
    @_login_required
    @bp.doc(operationId="listHolidays", tags=["Celebrations"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Holiday(many=True))
    def list_holidays():
        try:
            return _holidays(session["team_id"])
        except Exception as exc:
            logger.error("celebrations list_holidays: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503

    @bp.route("/dashboard/api/celebrations/holidays", methods=["POST"])
    @_admin_required("celebrations")
    @bp.doc(operationId="addHoliday", tags=["Celebrations"], security=[{"sessionCookie": [], "csrfHeader": []}])
    @api_errors(bp)
    @bp.arguments(schemas.HolidayInput, error_status_code=400)
    @bp.response(200, schemas.Holiday(many=True))
    def add_holiday(data):
        """Add one holiday, or rename the one already on that date. Returns the list."""
        team_id = session["team_id"]
        try:
            name = clean_holiday_name(data.get("name"))
        except CalendarError as exc:
            return _error("name", str(exc))
        try:
            db.upsert_holidays(team_id, [{"date": data["date"], "name": name}])
            return _holidays(team_id)
        except Exception as exc:
            logger.error("celebrations add_holiday: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503

    @bp.route("/dashboard/api/celebrations/holidays/<day>", methods=["DELETE"])
    @_admin_required("celebrations")
    @bp.doc(operationId="deleteHoliday", tags=["Celebrations"], security=[{"sessionCookie": [], "csrfHeader": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Holiday(many=True))
    def delete_holiday(day: str):
        team_id = session["team_id"]
        try:
            when = date.fromisoformat(day)
        except ValueError:
            return jsonify({"error": "Use a YYYY-MM-DD date"}), 404
        try:
            db.delete_holiday(team_id, when)
            return _holidays(team_id)
        except Exception as exc:
            logger.error("celebrations delete_holiday: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503

    @bp.route("/dashboard/api/celebrations/holidays/import", methods=["POST"])
    @_admin_required("celebrations")
    @bp.doc(operationId="importHolidays", tags=["Celebrations"], security=[{"sessionCookie": [], "csrfHeader": []}])
    @api_errors(bp)
    @bp.arguments(schemas.HolidayImportInput, error_status_code=400)
    @bp.response(200, schemas.HolidayImportResult)
    def import_holidays(data):
        """Holidays from `date,name` lines. Preview (the default) writes nothing."""
        team_id = session["team_id"]
        preview = bool(data.get("preview", True))
        try:
            rows = read_holiday_csv(data["csv"])
        except CalendarError as exc:
            return _error("csv", str(exc))
        ready = [r for r in rows if r["status"] == "ready"]
        written = 0
        if not preview and ready:
            try:
                written = db.upsert_holidays(team_id, ready)
            except Exception as exc:
                logger.error("celebrations import_holidays: %s", exc)
                return jsonify({"error": "Service unavailable"}), 503
        return {
            "preview": preview,
            "ready": len(ready),
            "invalid": len(rows) - len(ready),
            "written": written,
            "rows": rows,
        }

    @bp.route("/dashboard/api/celebrations/upcoming", methods=["GET"])
    @_admin_required("celebrations")
    @bp.doc(operationId="listUpcomingCelebrations", tags=["Celebrations"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Upcoming(many=True))
    def upcoming():
        """What the next 30 days will post, and on which day. Admins only: it lists birthdays."""
        from src.modules.celebrations.rules import upcoming as plan  # noqa: PLC0415

        team_id = session["team_id"]
        try:
            settings = cdb.get_settings(team_id)
            # An unusable stored timezone reads as UTC rather than the server clock.
            today = jobs.local_today(settings.get("timezone") or "UTC") or jobs.local_today("UTC")
            cal = from_rows(db.get_working_days(team_id), db.list_holidays(team_id))
            people = jobs.people_from_rows(cdb.celebrants(team_id))
        except Exception as exc:
            logger.error("celebrations upcoming: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        out = []
        for posted_on, c in plan(
            people,
            cal,
            today,
            UPCOMING_DAYS,
            birthdays=bool(settings.get("birthdays", True)),
            anniversaries=bool(settings.get("anniversaries", True)),
        ):
            for person in c.people:
                out.append(
                    {
                        "kind": c.kind,
                        "date": c.day,
                        "posted_on": posted_on,
                        "user_id": person.user_id,
                        "years": person.years,
                    }
                )
        return out

    def _ask_targets(team_id: str):
        from src.modules.celebrations.jobs import ASK_AGAIN_AFTER_DAYS, bot_client, missing_dates, workspace_people

        people = workspace_people(bot_client(team_id), team_id)
        return people, missing_dates(team_id, people, cooldown_days=ASK_AGAIN_AFTER_DAYS)

    @bp.route("/dashboard/api/celebrations/ask-dates", methods=["GET"])
    @_admin_required("celebrations")
    @bp.doc(operationId="previewAskForDates", tags=["Celebrations"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.AskPreview)
    def preview_ask():
        """How many people would be asked, and the message they would get. Sends nothing."""
        team_id = session["team_id"]
        try:
            settings = cdb.get_settings(team_id)
            _people, targets = _ask_targets(team_id)
        except Exception as exc:
            logger.error("celebrations preview_ask: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return {
            "count": len(targets),
            "message": nudge_text("Priya", settings.get("channel_id") or "C0CELEBRATE"),
            "ready": cdb.is_ready(settings),
        }

    @bp.route("/dashboard/api/celebrations/ask-dates", methods=["POST"])
    @_admin_required("celebrations")
    @bp.doc(operationId="askForDates", tags=["Celebrations"], security=[{"sessionCookie": [], "csrfHeader": []}])
    @api_errors(bp)
    @bp.response(200, schemas.AskResult)
    def ask():
        """DM everyone still missing dates, at most once per person per 30 days.

        The people are claimed before anything is sent, so a double click or a
        second admin sends nothing more. The DMs go out in the background.
        """
        team_id = session["team_id"]
        try:
            settings = cdb.get_settings(team_id)
            if not cdb.is_ready(settings):
                return jsonify({"error": "Choose a channel and a timezone first"}), 409
            people, targets = _ask_targets(team_id)
            claimed = db.claim_profile_nudges(team_id, targets, cooldown_days=jobs.ASK_AGAIN_AFTER_DAYS)
        except Exception as exc:
            logger.error("celebrations ask: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        if claimed:
            start_background(_ask_in_background, team_id, settings["channel_id"], claimed, people)
        return {"count": len(claimed)}

    register_api_blueprint(flask_app, bp)
    from src.modules.celebrations.banners import register_route  # noqa: PLC0415

    register_route(flask_app)
