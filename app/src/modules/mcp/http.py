"""MCP HTTP endpoint — exposes standup data to AI assistants over HTTP."""

from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request

import src.core.db as db

logger = logging.getLogger(__name__)
mcp_bp = Blueprint("mcp", __name__)

MCP_SERVER_INFO = {
    "name": "morgenruf",
    "version": "1.0.0",
}

TOOLS = [
    {
        "name": "get_standups",
        "description": "Fetch standup responses for the workspace. Returns who submitted, what they worked on, and any blockers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "Start date YYYY-MM-DD (default: 7 days ago)"},
                "to_date": {"type": "string", "description": "End date YYYY-MM-DD (default: today)"},
                "user_id": {"type": "string", "description": "Filter by specific user ID (optional)"},
            },
        },
    },
    {
        "name": "get_today_standups",
        "description": "Get all standup submissions from today.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_blockers",
        "description": "Get all active blockers reported by the team.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "How many days back to look (default: 7)"},
            },
        },
    },
    {
        "name": "get_participation",
        "description": "Get standup participation statistics — who submitted, who missed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to analyze (default: 30)"},
            },
        },
    },
    {
        "name": "get_members",
        "description": "List all workspace members and their status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_member_profiles",
        "description": (
            "What members say about themselves: role, location, what to ask them about, "
            "birthday (day and month only, never a year) and start date. People who have "
            "left the workspace are not included."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Only this member's profile (optional)"},
            },
        },
    },
    {
        "name": "search_standups",
        "description": "Full-text search across standup responses.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Search term"},
                "days": {"type": "integer", "description": "How many days back to search (default: 30)"},
            },
        },
    },
    {
        "name": "get_workspace_summary",
        "description": "Get a high-level summary of the workspace: member count, recent participation, top blockers.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_mood_summary",
        "description": "Get team mood trends over time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to analyze (default: 30)"},
            },
        },
    },
]

_NO_BLOCKER = {"", "none", "n/a", "no", "-", "nothing"}


def _auth() -> str | None:
    """Extract and verify Bearer token, return team_id or None.

    Failures are counted per address (mcp_endpoint refuses a caller over the
    budget before the key is looked up), so guessing keys cannot also hammer
    the database. A client using a good key never counts against it.
    """
    from src.core import rate_limit  # noqa: PLC0415

    who = rate_limit.client_key()
    auth = request.headers.get("Authorization", "")
    key = auth[7:].strip() if auth.startswith("Bearer ") else ""
    team_id = db.verify_mcp_key(key) if key else None
    if not team_id:
        rate_limit.MCP_AUTH_FAILURES.hit(who)
    return team_id


def _fmt(obj) -> str:
    from datetime import date, datetime

    def _default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, indent=2, default=_default)


# The longest window any tool reads, the same cap the dashboard reports use.
# get_standups with from_date=2000-01-01, or search_standups with days=100000,
# loaded a workspace's whole history into memory, the query that ran the pod
# out of memory from the reports page before 1.9.1.
MAX_DAYS = 365


def _days(args: dict, default: int) -> int:
    try:
        days = int(args.get("days") or default)
    except (TypeError, ValueError):
        days = default
    return max(1, min(days, MAX_DAYS))


def _clamp_from_date(value: str, today) -> str:  # noqa: ANN001
    from datetime import date, timedelta

    earliest = today - timedelta(days=MAX_DAYS - 1)
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return str(today - timedelta(days=7))
    return earliest.isoformat() if parsed < earliest else parsed.isoformat()


def _call_tool(name: str, args: dict, team_id: str) -> str:
    """Execute a named MCP tool and return a text result."""
    from collections import Counter
    from datetime import date, timedelta

    today = date.today()

    if name == "get_standups":
        from_date = _clamp_from_date(args.get("from_date") or str(today - timedelta(days=7)), today)
        to_date = args.get("to_date", str(today))
        user_id = args.get("user_id")
        rows = db.get_standups(team_id, from_date=from_date, to_date=to_date)
        if user_id:
            rows = [r for r in rows if r.get("user_id") == user_id]
        return _fmt(rows) if rows else "No standups found for the given period."

    if name == "get_today_standups":
        rows = db.get_standups(team_id, days=1)
        return _fmt(rows) if rows else "No standups submitted today yet."

    if name == "get_blockers":
        days = _days(args, 7)
        rows = db.get_standups(team_id, days=days)
        blockers = [
            {
                "user_id": r.get("user_id"),
                "date": r.get("standup_date"),
                "blockers": r.get("blockers"),
            }
            for r in rows
            if r.get("blockers", "").strip().lower() not in _NO_BLOCKER
        ]
        return _fmt(blockers) if blockers else f"No blockers reported in the last {days} days. 🎉"

    if name == "get_participation":
        days = _days(args, 30)
        stats = db.get_participation_stats(team_id, days=days)
        return _fmt(stats)

    if name == "get_members":
        members = db.get_active_members(team_id)
        return _fmt(members) if members else "No members found."

    if name == "get_member_profiles":
        return _member_profiles(team_id, (args.get("user_id") or "").strip())

    if name == "search_standups":
        query = args.get("query", "")
        days = _days(args, 30)
        rows = db.get_standups(team_id, days=days)
        q = query.lower()
        matches = [r for r in rows if q in json.dumps(r, default=str).lower()]
        return _fmt(matches) if matches else f"No standup responses matching '{query}'."

    if name == "get_workspace_summary":
        members = db.get_active_members(team_id) or []
        rows_today = db.get_standups(team_id, days=1) or []
        all_recent = db.get_standups(team_id, days=7) or []
        blockers = [r for r in all_recent if r.get("blockers", "").strip().lower() not in _NO_BLOCKER]
        total = len(members)
        submitted = len(rows_today)
        pct = round(submitted / total * 100) if total else 0
        summary = {
            "total_members": total,
            "submitted_today": submitted,
            "participation_7d_pct": pct,
            "active_blockers": len(blockers),
        }
        return _fmt(summary)

    if name == "get_mood_summary":
        days = _days(args, 30)
        rows = db.get_standups(team_id, days=days)
        moods = [r.get("mood") for r in rows if r.get("mood")]
        if not moods:
            return "No mood data available."
        counts = Counter(moods)
        return _fmt({"total_responses": len(moods), "mood_counts": dict(counts)})

    # Not a standup tool. Modules register their own, and only the ones this
    # workspace has active are reachable.
    handler = _module_handler(team_id, name)
    if handler is not None:
        return _fmt(handler(args, team_id))

    return f"Unknown tool: {name}"


def _member_profiles(team_id: str, user_id: str = "") -> str:
    """Profile fields for the workspace's current members, read only.

    Which admin or member last wrote a row, and the job bookkeeping
    (nudged_at, left_at), stay out: an assistant needs what people said about
    themselves, not the audit trail.
    """
    rows = db.list_member_profiles(team_id)
    if user_id:
        rows = [r for r in rows if r.get("user_id") == user_id]
    names = {m["user_id"]: m.get("real_name") or "" for m in db.get_all_members(team_id)}
    profiles = [
        {
            "user_id": r["user_id"],
            "name": names.get(r["user_id"], ""),
            "role": r.get("role"),
            "location": r.get("location"),
            "ask_me_about": r.get("ask_me_about"),
            "birthday": (
                f"{r['birth_month']:02d}-{r['birth_day']:02d}" if r.get("birth_month") and r.get("birth_day") else None
            ),
            "start_date": r.get("start_date"),
            "celebrate": bool(r.get("celebrate", True)),
        }
        for r in rows
    ]
    if not profiles:
        return "No profile found for that member." if user_id else "No member profiles filled in yet."
    return _fmt(profiles)


def _module_tool_list(team_id: str) -> list[dict]:
    """Tools contributed by active modules, or nothing if the registry fails.

    A module problem must not take the standup tools offline with it.
    """
    try:
        from src.core.mcp_tools import public_tools  # noqa: PLC0415

        return public_tools(team_id)
    except Exception:
        logger.exception("could not list module MCP tools")
        return []


def _module_handler(team_id: str, name: str):
    try:
        from src.core.mcp_tools import handler_for  # noqa: PLC0415

        return handler_for(team_id, name)
    except Exception:
        logger.exception("could not resolve module MCP tool %r", name)
        return None


@mcp_bp.route("/mcp", methods=["GET"])
def mcp_info():
    """Public info endpoint — shows how to connect."""
    return jsonify(
        {
            "name": "Morgenruf MCP Server",
            "version": "1.0.0",
            "transport": "http",
            "endpoint": request.host_url.rstrip("/") + "/mcp",
            "auth": "Bearer token — generate from your Morgenruf dashboard",
            "docs": "https://docs.morgenruf.dev/mcp.html",
            "tools": [t["name"] for t in TOOLS],
            "note": (
                "Authenticated tools/list returns more: coffee chats, kudos and insights "
                "tools appear for workspaces that have those modules switched on."
            ),
        }
    )


@mcp_bp.route("/mcp", methods=["POST"])
def mcp_endpoint():
    """MCP JSON-RPC 2.0 endpoint."""
    from src.core import rate_limit  # noqa: PLC0415

    if rate_limit.MCP_AUTH_FAILURES.limited(rate_limit.client_key()):
        return rate_limit.too_many()
    team_id = _auth()
    if not team_id:
        return jsonify(
            {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32001,
                    "message": "Unauthorized — provide a valid Bearer API key from your Morgenruf dashboard",
                },
                "id": None,
            }
        ), 401

    body = request.get_json(silent=True) or {}
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id")

    def ok(result):
        return jsonify({"jsonrpc": "2.0", "result": result, "id": req_id})

    def err(code, msg):
        return jsonify({"jsonrpc": "2.0", "error": {"code": code, "message": msg}, "id": req_id})

    if method == "initialize":
        return ok(
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": MCP_SERVER_INFO,
            }
        )

    if method == "tools/list":
        return ok({"tools": TOOLS + _module_tool_list(team_id)})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        try:
            result = _call_tool(tool_name, tool_args, team_id)
            return ok({"content": [{"type": "text", "text": result}]})
        except Exception as exc:
            logger.error("MCP tool %s error: %s", tool_name, exc)
            return err(-32603, f"Tool execution error: {exc}")

    if method == "ping":
        return ok({})

    return err(-32601, f"Method not found: {method}")
