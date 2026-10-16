"""Celebrations as MCP tools.

Upcoming dates come from the same plan the dashboard shows and the daily job
posts, so opted-out and departed people are already left out. A birthday is
the date it falls on this time round, which carries this year and never the
year someone was born.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.core.mcp_tools import identity, member_identities, window


def _today(settings: dict):
    from src.modules.celebrations import jobs  # noqa: PLC0415

    # An unusable stored timezone reads as UTC, as on the dashboard.
    return jobs.local_today(settings.get("timezone") or "UTC") or jobs.local_today("UTC")


def _upcoming(args: dict, team_id: str) -> Any:
    import src.core.db as db  # noqa: PLC0415
    import src.modules.celebrations.db as cdb  # noqa: PLC0415
    from src.core.workspace_calendar import from_rows  # noqa: PLC0415
    from src.modules.celebrations import jobs  # noqa: PLC0415
    from src.modules.celebrations.rules import upcoming  # noqa: PLC0415

    days, limit = window(args)
    settings = cdb.get_settings(team_id)
    today = _today(settings)
    cal = from_rows(db.get_working_days(team_id), db.list_holidays(team_id))
    people = member_identities(team_id)
    posted = cdb.posted_keys(team_id, today)
    out = []
    for posted_on, c in upcoming(
        jobs.people_from_rows(cdb.celebrants(team_id)),
        cal,
        today,
        days,
        birthdays=bool(settings.get("birthdays", True)),
        anniversaries=bool(settings.get("anniversaries", True)),
    ):
        for person in c.people:
            row = {
                **identity(people, person.user_id),
                "kind": c.kind,
                "date": c.day,
                "posted_on": posted_on,
                "posted": (c.kind, c.day) in posted,
            }
            if person.years:
                row["years"] = person.years
            out.append(row)
    return out[:limit]


def _history(args: dict, team_id: str) -> Any:
    import src.modules.celebrations.db as cdb  # noqa: PLC0415

    days, limit = window(args)
    since = _today(cdb.get_settings(team_id)) - timedelta(days=days)
    people = member_identities(team_id)
    return [
        {
            "kind": r["kind"],
            "date": r["celebration_date"],
            "posted_on": r["posted_on"],
            "channel_id": r["channel_id"],
            "people": [identity(people, u) for u in r["user_ids"] or []],
            "posted": r["ts"] is not None,
        }
        for r in cdb.recent_posts(team_id, since, limit)
    ]


def tools() -> list[dict[str, Any]]:
    window_props = {
        "days": {"type": "integer", "description": "Window in days (default: 30)"},
        "limit": {"type": "integer", "description": "How many to return (default: 50, max: 200)"},
    }
    return [
        {
            "name": "get_upcoming_celebrations",
            "description": (
                "Birthdays and work anniversaries in the next N days: who, the date, the working "
                "day it will be posted on, completed years for an anniversary, and whether the "
                "post has gone out. Never a birth year. People who opted out are not listed."
            ),
            "inputSchema": {"type": "object", "properties": window_props},
            "handler": _upcoming,
        },
        {
            "name": "get_celebration_history",
            "description": (
                "Birthday and anniversary posts from the last N days, newest first, with who was "
                "celebrated and whether Slack accepted the post."
            ),
            "inputSchema": {"type": "object", "properties": window_props},
            "handler": _history,
        },
    ]
