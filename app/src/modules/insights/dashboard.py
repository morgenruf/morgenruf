"""Insights HTTP API.

Blueprint is built inside register_routes so importing the registry does not
pull core's dashboard in as a side effect.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_routes(flask_app) -> None:
    from flask import Blueprint, jsonify, request, session

    import src.modules.insights.db as idb
    from src.core.dashboard import _login_required
    from src.modules.insights.rules import find_blocker_runs

    bp = Blueprint("insights", __name__)

    @bp.route("/dashboard/api/insights", methods=["GET"])
    @_login_required
    def api_insights():
        team_id = session["team_id"]
        days = max(7, min(90, int(request.args.get("days", 30))))
        min_days = max(2, min(10, int(request.args.get("min_blocker_days", 3))))

        unrecognised = idb.unrecognised_contributors(team_id, days=days)
        for row in unrecognised:
            if row.get("last_standup"):
                row["last_standup"] = row["last_standup"].isoformat()

        stuck = []
        for user_id, rows in idb.blocker_rows(team_id, days=min(days, 21)).items():
            for run in find_blocker_runs(rows, min_days=min_days):
                stuck.append({
                    "user_id": user_id,
                    "real_name": rows[0].get("real_name"),
                    "days": run["days"],
                    "first_seen": run["first_seen"].isoformat(),
                    "last_seen": run["last_seen"].isoformat(),
                    "text": run["text"],
                })
        stuck.sort(key=lambda r: (-r["days"], r["user_id"]))

        return jsonify({
            "window_days": days,
            "unrecognised": unrecognised,
            "stuck": stuck,
        })

    flask_app.register_blueprint(bp)
