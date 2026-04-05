"""Morgenruf MCP Server — expose standup data to AI assistants.

Allows Claude, Cursor, Copilot, and other MCP-capable tools to query
standup history, participation, blockers, and more.

Usage:
    python src/mcp_server.py

Configuration (env vars):
    DATABASE_URL    PostgreSQL connection URL (required)
    MCP_TEAM_ID     Default team_id to query (optional — can pass per-call)
    MCP_API_KEY     Simple shared secret to authenticate MCP clients (optional)

Example claude_desktop_config.json:
    {
      "mcpServers": {
        "morgenruf": {
          "command": "python",
          "args": ["/path/to/morgenruf/app/src/mcp_server.py"],
          "env": {
            "DATABASE_URL": "postgresql://morgenruf:pass@localhost:5432/morgenruf",
            "MCP_TEAM_ID": "TEE0GF0QZ"
          }
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

# Bootstrap database connection before importing db module
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolResult,
        ListToolsResult,
        TextContent,
        Tool,
    )
except ImportError:
    print(
        "mcp package not installed. Run: pip install mcp",
        file=sys.stderr,
    )
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))
import db  # noqa: E402

_DEFAULT_TEAM_ID = os.environ.get("MCP_TEAM_ID", "")

server = Server("morgenruf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _team(args: dict) -> str:
    """Resolve team_id from args or default."""
    tid = args.get("team_id") or _DEFAULT_TEAM_ID
    if not tid:
        raise ValueError("team_id is required. Set MCP_TEAM_ID env var or pass team_id argument.")
    return tid


def _fmt(obj: Any) -> str:
    """JSON-serialise with date/datetime support."""

    def default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, indent=2, default=default)


def _text(content: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=content)])


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="get_standups",
        description=(
            "Get standup responses for a team, optionally filtered by date range. "
            "Returns each member's yesterday/today/blockers/mood answers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Slack team ID (e.g. TEE0GF0QZ)"},
                "from_date": {"type": "string", "description": "Start date YYYY-MM-DD (default: 7 days ago)"},
                "to_date": {"type": "string", "description": "End date YYYY-MM-DD (default: today)"},
                "user_id": {"type": "string", "description": "Filter to a specific Slack user ID"},
            },
        },
    ),
    Tool(
        name="get_today_standups",
        description="Get all standup responses submitted today for a team.",
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Slack team ID"},
            },
        },
    ),
    Tool(
        name="get_blockers",
        description=(
            "Get all standup entries where a team member reported a blocker, "
            "within the last N days. Useful for: 'who is blocked right now?'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "days": {"type": "integer", "description": "How many days back to look (default: 7)"},
            },
        },
    ),
    Tool(
        name="get_participation",
        description=(
            "Get per-member participation stats: how many standups each person "
            "submitted in the last N days, their last standup date, and blocker count."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "days": {"type": "integer", "description": "Look-back window in days (default: 7)"},
            },
        },
    ),
    Tool(
        name="get_members",
        description="List active team members for a workspace.",
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
            },
        },
    ),
    Tool(
        name="search_standups",
        description=(
            "Full-text search across standup answers (yesterday/today/blockers). "
            "Useful for: 'who worked on the auth service this week?'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "query": {"type": "string", "description": "Search text"},
                "days": {"type": "integer", "description": "How many days back to search (default: 14)"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_workspace_summary",
        description=(
            "High-level workspace summary: team name, standup schedule, "
            "active member count, and this week's completion rate. "
            "Good as a first call to understand the workspace."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
            },
        },
    ),
    Tool(
        name="get_mood_summary",
        description=(
            "Aggregate mood data for the team over the last N days. "
            "Returns counts of 😊/😐/😔 responses and any free-text moods."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "days": {"type": "integer", "description": "Look-back window (default: 7)"},
            },
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    try:
        return await _dispatch(name, arguments)
    except ValueError as exc:
        return _text(f"❌ Error: {exc}")
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return _text(f"❌ Unexpected error in {name}: {exc}")


async def _dispatch(name: str, args: dict) -> CallToolResult:
    if name == "get_standups":
        return await _get_standups(args)
    if name == "get_today_standups":
        return await _get_today_standups(args)
    if name == "get_blockers":
        return await _get_blockers(args)
    if name == "get_participation":
        return await _get_participation(args)
    if name == "get_members":
        return await _get_members(args)
    if name == "search_standups":
        return await _search_standups(args)
    if name == "get_workspace_summary":
        return await _get_workspace_summary(args)
    if name == "get_mood_summary":
        return await _get_mood_summary(args)
    raise ValueError(f"Unknown tool: {name}")


async def _get_standups(args: dict) -> CallToolResult:
    team_id = _team(args)
    from_date = args.get("from_date") or (date.today() - timedelta(days=7)).isoformat()
    to_date = args.get("to_date") or date.today().isoformat()
    user_id = args.get("user_id")

    rows = db.export_standups(team_id, from_date, to_date)
    if user_id:
        rows = [r for r in rows if r.get("user_id") == user_id]

    if not rows:
        return _text(f"No standups found for {team_id} between {from_date} and {to_date}.")

    lines = [f"📋 Standups for team {team_id} ({from_date} → {to_date}) — {len(rows)} entries\n"]
    for r in rows:
        lines.append(
            f"── {r.get('standup_date')} · {r.get('user_id')}\n"
            f"  Yesterday: {r.get('yesterday', '')}\n"
            f"  Today:     {r.get('today', '')}\n"
            f"  Blockers:  {r.get('blockers', '')}\n" + (f"  Mood:      {r.get('mood', '')}\n" if r.get("mood") else "")
        )
    return _text("\n".join(lines))


async def _get_today_standups(args: dict) -> CallToolResult:
    team_id = _team(args)
    rows = db.get_today_standups(team_id)
    if not rows:
        return _text(f"No standups submitted today for team {team_id}.")
    lines = [f"📋 Today's standups — {len(rows)} submitted\n"]
    for r in rows:
        lines.append(
            f"── {r.get('user_id')}\n"
            f"  Yesterday: {r.get('yesterday', '')}\n"
            f"  Today:     {r.get('today', '')}\n"
            f"  Blockers:  {r.get('blockers', '')}\n" + (f"  Mood:      {r.get('mood', '')}\n" if r.get("mood") else "")
        )
    return _text("\n".join(lines))


async def _get_blockers(args: dict) -> CallToolResult:
    team_id = _team(args)
    days = int(args.get("days") or 7)
    from_date = (date.today() - timedelta(days=days - 1)).isoformat()

    rows = db.export_standups(team_id, from_date)
    blocked = [r for r in rows if r.get("has_blockers")]

    if not blocked:
        return _text(f"✅ No blockers reported in the last {days} days for team {team_id}.")

    lines = [f"🚧 Blockers in the last {days} days — {len(blocked)} entries\n"]
    for r in blocked:
        lines.append(f"── {r.get('standup_date')} · {r.get('user_id')}\n  {r.get('blockers', '')}\n")
    return _text("\n".join(lines))


async def _get_participation(args: dict) -> CallToolResult:
    team_id = _team(args)
    days = int(args.get("days") or 7)
    stats = db.get_participation_stats(team_id, days)

    if not stats:
        return _text(f"No participation data found for team {team_id}.")

    lines = [f"📊 Participation — last {days} days\n{'Member':<24} {'Standups':>8} {'Blockers':>9} Last Standup"]
    lines.append("─" * 60)
    for s in stats:
        name = (s.get("real_name") or s.get("user_id", ""))[:22]
        responses = int(s.get("responses") or 0)
        blockers = int(s.get("days_with_blockers") or 0)
        last = str(s.get("last_standup") or "—")[:10]
        bar = "🟢" * min(responses, days) + "⬜" * max(0, days - min(responses, days))
        lines.append(f"{name:<24} {bar} {responses}/{days}  {'🚧' if blockers else '—'} {blockers}  {last}")
    return _text("\n".join(lines))


async def _get_members(args: dict) -> CallToolResult:
    team_id = _team(args)
    members = db.get_active_members(team_id)
    if not members:
        return _text(f"No active members found for team {team_id}.")
    lines = [f"👥 Active members — {len(members)}\n"]
    for m in members:
        lines.append(f"  {m.get('real_name') or m.get('user_id')}  ({m.get('user_id')})  tz={m.get('tz', 'UTC')}")
    return _text("\n".join(lines))


async def _search_standups(args: dict) -> CallToolResult:
    team_id = _team(args)
    query = args.get("query", "").strip().lower()
    days = int(args.get("days") or 14)
    if not query:
        raise ValueError("query is required")

    from_date = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = db.export_standups(team_id, from_date)

    matches = [
        r
        for r in rows
        if query in (r.get("yesterday") or "").lower()
        or query in (r.get("today") or "").lower()
        or query in (r.get("blockers") or "").lower()
    ]

    if not matches:
        return _text(f"No standup entries mentioning '{query}' in the last {days} days.")

    lines = [f"🔍 Search: '{query}' — {len(matches)} matches in last {days} days\n"]
    for r in matches:
        lines.append(
            f"── {r.get('standup_date')} · {r.get('user_id')}\n"
            f"  Yesterday: {r.get('yesterday', '')}\n"
            f"  Today:     {r.get('today', '')}\n"
            f"  Blockers:  {r.get('blockers', '')}\n"
        )
    return _text("\n".join(lines))


async def _get_workspace_summary(args: dict) -> CallToolResult:
    team_id = _team(args)
    inst = db.get_installation(team_id)
    config = db.get_workspace_config(team_id) or {}
    stats = db.get_dashboard_stats(team_id)
    members = db.get_active_members(team_id)

    team_name = (inst or {}).get("team_name", team_id)
    schedule = f"{config.get('schedule_time', '?')} {config.get('schedule_tz', 'UTC')} on {config.get('schedule_days', 'weekdays')}"
    channel = config.get("channel_id", "not configured")

    summary = (
        f"☀️  Morgenruf — {team_name} ({team_id})\n\n"
        f"  Schedule:       {schedule}\n"
        f"  Channel:        {channel}\n"
        f"  Active members: {len(members)}\n"
        f"  This week:\n"
        f"    Responses:       {stats.get('responses_this_week', 0)}\n"
        f"    Completion rate: {stats.get('completion_rate', 0)}%\n"
    )
    return _text(summary)


async def _get_mood_summary(args: dict) -> CallToolResult:
    team_id = _team(args)
    days = int(args.get("days") or 7)
    from_date = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = db.export_standups(team_id, from_date)

    moods = [r.get("mood", "").strip() for r in rows if r.get("mood")]
    if not moods:
        return _text(f"No mood data for team {team_id} in the last {days} days.")

    counts: dict[str, int] = {}
    for m in moods:
        # Normalise: map common variants
        key = m
        for happy in ("😊", "great", "good", "1"):
            if happy in m.lower():
                key = "😊 great"
                break
        for meh in ("😐", "okay", "ok", "meh", "2"):
            if meh in m.lower():
                key = "😐 okay"
                break
        for sad in ("😔", "rough", "bad", "3"):
            if sad in m.lower():
                key = "😔 rough"
                break
        counts[key] = counts.get(key, 0) + 1

    lines = [f"🎭 Mood summary — last {days} days ({len(moods)} responses)\n"]
    for mood, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = int(count / len(moods) * 100)
        bar = "█" * (pct // 5)
        lines.append(f"  {mood:<16} {bar} {pct}% ({count})")
    return _text("\n".join(lines))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    logger.info("Starting Morgenruf MCP server (team_id=%s)", _DEFAULT_TEAM_ID or "dynamic")
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
