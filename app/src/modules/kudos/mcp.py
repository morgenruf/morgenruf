"""Kudos as MCP tools.

Recognition data answers questions standups cannot: who is carrying the team,
who is being carried, and whether anyone is going unnoticed. All of it is
already on screen in the dashboard; this makes it answerable in a sentence.
"""

from __future__ import annotations

from typing import Any


def _leaderboard(args: dict, team_id: str) -> Any:
    import src.modules.kudos.db as kdb  # noqa: PLC0415

    days = int(args.get("days") or 30)
    return {
        "days": days,
        "most_recognised": kdb.get_kudos_leaderboard(team_id, days),
        "most_generous": kdb.get_giver_leaderboard(team_id, days),
    }


def _recent(args: dict, team_id: str) -> Any:
    import src.modules.kudos.db as kdb  # noqa: PLC0415

    limit = max(1, min(int(args.get("limit") or 25), 200))
    return kdb.get_kudos(team_id, limit)


def _config(args: dict, team_id: str) -> Any:
    import src.modules.kudos.db as kdb  # noqa: PLC0415

    return kdb.get_config(team_id)


def tools() -> list[dict[str, Any]]:
    days = {"type": "integer", "description": "Window in days (default: 30)"}
    return [
        {
            "name": "get_kudos_leaderboard",
            "description": (
                "Who has been recognised most, and who gives out the most recognition, "
                "over a window of days. Both halves matter: the people who thank others "
                "are what keeps the habit alive."
            ),
            "inputSchema": {"type": "object", "properties": {"days": days}},
            "handler": _leaderboard,
        },
        {
            "name": "get_recent_kudos",
            "description": "The most recent kudos with who sent them, who received them, and the message.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "How many to return (default: 25, max: 200)"}
                },
            },
            "handler": _recent,
        },
        {
            "name": "get_kudos_settings",
            "description": "The workspace's kudos token and how many each person may give per day.",
            "inputSchema": {"type": "object", "properties": {}},
            "handler": _config,
        },
    ]
