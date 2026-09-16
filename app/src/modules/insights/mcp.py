"""Insights as MCP tools.

These are the cross-signal questions: a blocker that has not moved in days, or
someone answering every standup and being thanked by nobody. Neither is
visible in standup data or kudos data alone, which is the whole point of the
module, and both are exactly what an assistant should be able to surface
without being asked twice.
"""

from __future__ import annotations

from typing import Any

from src.modules.insights.rules import find_blocker_runs


def _stuck(args: dict, team_id: str) -> Any:
    import src.modules.insights.db as idb  # noqa: PLC0415
    days = max(1, min(int(args.get("days") or 21), 120))
    min_days = max(2, int(args.get("min_days") or 3))
    grouped = idb.blocker_rows(team_id, days)
    out = []
    for user_id, rows in grouped.items():
        for run in find_blocker_runs(rows, min_days=min_days):
            out.append({
                "user_id": user_id,
                "blocker": run["text"],
                "days_running": run["days"],
                "first_seen": run["first_seen"],
                "last_seen": run["last_seen"],
            })
    out.sort(key=lambda r: r["days_running"], reverse=True)
    return {"window_days": days, "threshold_days": min_days, "stuck": out}


def _unrecognised(args: dict, team_id: str) -> Any:
    import src.modules.insights.db as idb  # noqa: PLC0415
    days = max(1, min(int(args.get("days") or 30), 365))
    min_standups = max(1, int(args.get("min_standups") or 8))
    return {
        "window_days": days,
        "min_standups": min_standups,
        "people": idb.unrecognised_contributors(team_id, days, min_standups),
    }


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_stuck_blockers",
            "description": (
                "Blockers the same person has raised on several consecutive working days. "
                "One mention is work; the same blocker three days running is someone stuck "
                "and nobody noticing. Weekends do not break a run."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "How far back to look (default: 21)"},
                    "min_days": {"type": "integer", "description": "Consecutive days before it counts (default: 3)"},
                },
            },
            "handler": _stuck,
        },
        {
            "name": "get_unrecognised_contributors",
            "description": (
                "People who have answered standup consistently and received no kudos at all "
                "in the window. Answers a question neither standups nor kudos can answer alone."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days (default: 30)"},
                    "min_standups": {"type": "integer", "description": "Standups answered before someone counts as consistent (default: 8)"},
                },
            },
            "handler": _unrecognised,
        },
    ]
