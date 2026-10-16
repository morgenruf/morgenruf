"""Watercooler as MCP tools.

The bot cannot read thread replies (no channels:history), so what it knows
is what it posted: which question, where, and when. No reply or participant
counts, because there is nothing to count them from.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.mcp_tools import window


def _topics(args: dict, team_id: str) -> Any:
    import src.modules.watercooler.db as wdb  # noqa: PLC0415
    from src.modules.watercooler import bank, rotation  # noqa: PLC0415

    days, limit = window(args)
    rows = wdb.recent_posts(team_id, datetime.now(timezone.utc).date() - timedelta(days=days), limit)
    custom = {rotation.custom_ref(q["id"]): q["text"] for q in wdb.list_questions(team_id)}
    out = []
    for r in rows:
        ref = r["question_ref"]
        builtin = bank.BY_KEY.get(ref[2:]) if ref.startswith("b:") else None
        out.append(
            {
                "channel_id": r["channel_id"],
                "posted_on": r["posted_on"],
                "message_ts": r["ts"],
                "question": builtin.text if builtin else custom.get(ref),
                "category": builtin.category if builtin else "custom",
            }
        )
    return out


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_watercooler_topics",
            "description": (
                "Watercooler questions posted in the last N days, newest first: the question, "
                "its category, the channel and the day. Morgenruf cannot read thread replies, "
                "so there are no reply or participant counts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days (default: 30)"},
                    "limit": {"type": "integer", "description": "How many to return (default: 50, max: 200)"},
                },
            },
            "handler": _topics,
        },
    ]
