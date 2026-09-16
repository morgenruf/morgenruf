"""Coffee chats as MCP tools.

The useful question about a pairing programme is never "is it running" but
"is it working": whether the introductions turn into conversations, and who
has quietly stopped turning up.
"""

from __future__ import annotations

from typing import Any

from src.modules.connect.rounds import match_status


def _programs(args: dict, team_id: str) -> Any:
    import src.modules.connect.db as cdb  # noqa: PLC0415
    return cdb.get_programs(team_id)


def _rounds(args: dict, team_id: str) -> Any:
    import src.modules.connect.db as cdb  # noqa: PLC0415
    program_id = args.get("program_id")
    if not program_id:
        return {"error": "program_id is required. Call list_coffee_chat_programs first."}
    limit = max(1, min(int(args.get("limit") or 10), 52))
    return cdb.recent_rounds(team_id, int(program_id), limit)


def _attendance(args: dict, team_id: str) -> Any:
    import src.modules.connect.db as cdb  # noqa: PLC0415
    program_id = args.get("program_id")
    if not program_id:
        return {"error": "program_id is required. Call list_coffee_chat_programs first."}
    rounds = max(1, min(int(args.get("rounds") or 6), 52))
    return {
        "rounds_considered": rounds,
        "people": cdb.participation(team_id, int(program_id), rounds),
    }


def _round_pairs(args: dict, team_id: str) -> Any:
    import src.modules.connect.db as cdb  # noqa: PLC0415
    round_id = args.get("round_id")
    if not round_id:
        return {"error": "round_id is required. Call get_coffee_chat_rounds first."}
    rows = cdb.round_matches(team_id, int(round_id))
    return [
        {
            "members": list(r["member_ids"] or []),
            "status": match_status(r["met"], r.get("delivered_at")),
        }
        for r in rows
    ]


def tools() -> list[dict[str, Any]]:
    program = {"type": "integer", "description": "Programme id from list_coffee_chat_programs"}
    return [
        {
            "name": "list_coffee_chat_programs",
            "description": "The coffee chat programmes in this workspace: channel, cadence, pool size and how many rounds have run.",
            "inputSchema": {"type": "object", "properties": {}},
            "handler": _programs,
        },
        {
            "name": "get_coffee_chat_rounds",
            "description": (
                "Recent rounds with attendance broken out into met, did not meet, "
                "no reply, and not delivered. Those last three mean different things: "
                "only 'not delivered' is a delivery failure rather than people not showing up."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"program_id": program, "limit": {"type": "integer", "description": "How many rounds (default: 10)"}},
                "required": ["program_id"],
            },
            "handler": _rounds,
        },
        {
            "name": "get_coffee_chat_attendance",
            "description": (
                "Per person across recent rounds: how often they were paired, met, "
                "did not meet, or never answered. Ordered by fewest met, so the people "
                "drifting away come first."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"program_id": program, "rounds": {"type": "integer", "description": "How many recent rounds to consider (default: 6)"}},
                "required": ["program_id"],
            },
            "handler": _attendance,
        },
        {
            "name": "get_coffee_chat_pairs",
            "description": "Who was paired with whom in one round, and what became of each pairing.",
            "inputSchema": {
                "type": "object",
                "properties": {"round_id": {"type": "integer", "description": "Round id from get_coffee_chat_rounds"}},
                "required": ["round_id"],
            },
            "handler": _round_pairs,
        },
    ]
