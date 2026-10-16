"""Pulse as MCP tools.

Every result comes out of db.trend and then the dashboard's public_round, the
same two gates the dashboard uses: nothing from a round still open, nothing
but counts under privacy.MIN_GROUP respondents, and no breakdown or eNPS
under privacy.MIN_DETAIL. Pulse stores no names and no free text, so there
is nothing else to hold back.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.mcp_tools import window
from src.modules.pulse import privacy, questions
from src.modules.pulse.dashboard import public_round
from src.modules.pulse.handlers import _DAYS


def _surveys(args: dict, team_id: str) -> Any:
    import src.modules.pulse.db as pdb  # noqa: PLC0415

    program = pdb.get_program(team_id)
    latest = pdb.trend(team_id, 1)
    last = latest[-1] if latest else {}
    invited = int(last.get("invited") or 0)
    day = _DAYS[int(program.get("day_of_week") or 0) % 7]
    return [
        {
            "id": "weekly",
            "title": "Weekly pulse",
            "enabled": bool(program.get("enabled")),
            "cadence": f"weekly, {day} {int(program['hour']):02d}:{int(program['minute']):02d} {program['timezone']}",
            "anonymous": True,
            "questions": [
                {"id": questions.MOOD, "text": questions.MOOD_TEXT, "type": "scale", "min": 1, "max": 5},
                {
                    "id": questions.ENPS,
                    "text": questions.ENPS_TEXT,
                    "type": "scale",
                    "min": 0,
                    "max": 10,
                    "asked": f"every {questions.ENPS_EVERY}th round, starting with the first",
                },
            ],
            "last_sent_at": last.get("sent_on"),
            "last_response_rate": round(int(last.get("respondents") or 0) / invited * 100, 1) if invited else None,
            "min_respondents_shown": privacy.MIN_GROUP,
        }
    ]


def _results(args: dict, team_id: str) -> Any:
    import src.modules.pulse.db as pdb  # noqa: PLC0415

    days, limit = window(args)
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    rounds = [public_round(r) for r in pdb.trend(team_id, limit) if r["sent_on"] >= since]
    return {
        "days": days,
        "min_respondents_for_average": privacy.MIN_GROUP,
        "min_respondents_for_breakdown": privacy.MIN_DETAIL,
        "mood_scale": list(questions.MOOD_LABELS),
        "rounds": rounds,
    }


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_pulse_surveys",
            "description": (
                "The workspace's anonymous weekly pulse: when it is sent, its questions "
                "(mood 1 to 5 every round, eNPS 0 to 10 every fourth), when it last went out "
                "and what share of those asked answered."
            ),
            "inputSchema": {"type": "object", "properties": {}},
            "handler": _surveys,
        },
        {
            "name": "get_pulse_results",
            "description": (
                "Team results per closed round, oldest first: average mood, and from ten "
                "respondents up the mood breakdown and eNPS. A round still open, or answered "
                "by fewer than five people, returns only its date and counts. Answers are "
                "anonymous and buttons only, so there are no names and no text."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days (default: 30)"},
                    "limit": {"type": "integer", "description": "Most rounds to return (default: 50, max: 200)"},
                },
            },
            "handler": _results,
        },
    ]
