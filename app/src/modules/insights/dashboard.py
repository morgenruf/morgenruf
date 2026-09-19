"""Insights HTTP API.

Blueprint is built inside register_routes so importing the registry does not
pull core's dashboard in as a side effect.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_routes(flask_app) -> None:
    from datetime import datetime, timezone

    from flask import session
    from flask_smorest import Blueprint

    import src.modules.insights.db as idb
    from src.core.api import api_errors, register_api_blueprint
    from src.core.dashboard import _login_required
    from src.core.roster import eligible_members
    from src.modules.insights import schemas
    from src.modules.insights.rules import find_blocker_runs
    from src.modules.insights.today import awaiting, blocked_from, expected_today, next_chat_date

    bp = Blueprint("insights", __name__)

    def _iso(value):
        return value.isoformat() if value is not None and hasattr(value, "isoformat") else value

    @bp.route("/dashboard/api/insights", methods=["GET"])
    @_login_required
    @bp.doc(operationId="getInsights", tags=["Insights"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.arguments(schemas.InsightsQuery, location="query", error_status_code=400)
    @bp.response(200, schemas.Insights)
    def api_insights(query):
        team_id = session["team_id"]
        days = max(7, min(90, int(query.get("days", 30))))
        min_days = max(2, min(10, int(query.get("min_blocker_days", 3))))

        unrecognised = idb.unrecognised_contributors(team_id, days=days)
        for row in unrecognised:
            if row.get("last_standup"):
                row["last_standup"] = row["last_standup"].isoformat()

        stuck = []
        for user_id, rows in idb.blocker_rows(team_id, days=min(days, 21)).items():
            for run in find_blocker_runs(rows, min_days=min_days):
                stuck.append(
                    {
                        "user_id": user_id,
                        "real_name": rows[0].get("real_name"),
                        "days": run["days"],
                        "first_seen": run["first_seen"].isoformat(),
                        "last_seen": run["last_seen"].isoformat(),
                        "text": run["text"],
                    }
                )
        stuck.sort(key=lambda r: (-r["days"], r["user_id"]))

        return {
            "window_days": days,
            "unrecognised": unrecognised,
            "stuck": stuck,
        }

    @bp.route("/dashboard/api/today", methods=["GET"])
    @_login_required
    @bp.doc(operationId="getToday", tags=["Insights"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.arguments(schemas.TodayQuery, location="query", error_status_code=400)
    @bp.response(200, schemas.Today)
    def api_today(query):
        """One morning, in one request.

        Every piece is optional on purpose. A workspace with no schedules, no
        kudos or no coffee chats still gets a page, because each query returns
        empty rather than raising and the counts fall out of whatever arrived.
        """
        team_id = session["team_id"]
        now = datetime.now(timezone.utc)

        responses = idb.todays_standups(team_id)
        for row in responses:
            row["standup_date"] = _iso(row.get("standup_date"))
            row["submitted_at"] = _iso(row.get("submitted_at"))

        blocked = blocked_from(responses)
        for row in blocked:
            row["submitted_at"] = _iso(row.get("submitted_at"))

        try:
            pool = eligible_members(team_id)
        except Exception as exc:
            logger.warning("api_today roster failed for %s: %s", team_id, exc)
            pool = []
        names = {m.user_id: m.name for m in pool}

        expected = expected_today(idb.active_schedules(team_id), names.keys(), now)
        answered = {row.get("user_id") for row in responses}
        waiting = [
            {"user_id": user_id, "real_name": names.get(user_id) or None} for user_id in awaiting(expected, answered)
        ]

        try:
            kudos_limit = max(1, min(20, int(query.get("kudos", 5))))
        except (TypeError, ValueError):
            kudos_limit = 5
        kudos = idb.recent_kudos(team_id, limit=kudos_limit)
        for row in kudos:
            row["created_at"] = _iso(row.get("created_at"))

        program = idb.connect_program_timing(team_id)
        chat_date = next_chat_date(program, now.date())
        next_chat = None
        if program and chat_date:
            # A due date in the past is not a forecast: the round was due and
            # has not run. Showing it as "next" told a Thursday its coffee
            # chat was on Wednesday.
            days_away = (chat_date - now.date()).days
            next_chat = {
                "program_id": program.get("program_id"),
                "name": program.get("name"),
                "date": chat_date.isoformat(),
                "days_away": days_away,
                "overdue": days_away < 0,
            }

        return {
            "date": now.date().isoformat(),
            "counts": {
                # Answered counts people, not rows, so it stays comparable with
                # expected when someone files two standups in one day.
                "expected": len(expected),
                "answered": len([u for u in answered if u]),
                "awaiting": len(waiting),
                "blocked": len(blocked),
            },
            "responses": responses,
            "awaiting": waiting,
            "blocked": blocked,
            "kudos": kudos,
            "next_chat": next_chat,
        }

    register_api_blueprint(flask_app, bp)
