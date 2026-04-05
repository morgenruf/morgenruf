"""MCP HTTP endpoint — exposes standup data to AI assistants over HTTP."""
from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request

import db

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
    """Extract and verify Bearer token, return team_id or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    key = auth[7:].strip()
    return db.verify_mcp_key(key)


def _fmt(obj) -> str:
    from datetime import date, datetime

    def _default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, indent=2, default=_default)


def _call_tool(name: str, args: dict, team_id: str) -> str:
    """Execute a named MCP tool and return a text result."""
    from collections import Counter
    from datetime import date, timedelta

    today = date.today()

    if name == "get_standups":
        from_date = args.get("from_date", str(today - timedelta(days=7)))
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
        days = args.get("days", 7)
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
        days = args.get("days", 30)
        stats = db.get_participation_stats(team_id, days=days)
        return _fmt(stats)

    if name == "get_members":
        members = db.get_active_members(team_id)
        return _fmt(members) if members else "No members found."

    if name == "search_standups":
        query = args.get("query", "")
        days = args.get("days", 30)
        rows = db.get_standups(team_id, days=days)
        q = query.lower()
        matches = [r for r in rows if q in json.dumps(r, default=str).lower()]
        return _fmt(matches) if matches else f"No standup responses matching '{query}'."

    if name == "get_workspace_summary":
        members = db.get_active_members(team_id) or []
        stats_rows = db.get_participation_stats(team_id, days=7) or []
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
        days = args.get("days", 30)
        rows = db.get_standups(team_id, days=days)
        moods = [r.get("mood") for r in rows if r.get("mood")]
        if not moods:
            return "No mood data available."
        counts = Counter(moods)
        return _fmt({"total_responses": len(moods), "mood_counts": dict(counts)})

    return f"Unknown tool: {name}"


@mcp_bp.route("/mcp", methods=["GET"])
def mcp_info():
    """Public info endpoint — shows how to connect."""
    return jsonify({
        "name": "Morgenruf MCP Server",
        "version": "1.0.0",
        "transport": "http",
        "endpoint": request.host_url.rstrip("/") + "/mcp",
        "auth": "Bearer token — generate from your Morgenruf dashboard",
        "docs": "https://docs.morgenruf.dev/mcp.html",
        "tools": [t["name"] for t in TOOLS],
    })


@mcp_bp.route("/mcp", methods=["POST"])
def mcp_endpoint():
    """MCP JSON-RPC 2.0 endpoint."""
    team_id = _auth()
    if not team_id:
        return jsonify({
            "jsonrpc": "2.0",
            "error": {
                "code": -32001,
                "message": "Unauthorized — provide a valid Bearer API key from your Morgenruf dashboard",
            },
            "id": None,
        }), 401

    body = request.get_json(silent=True) or {}
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id")

    def ok(result):
        return jsonify({"jsonrpc": "2.0", "result": result, "id": req_id})

    def err(code, msg):
        return jsonify({"jsonrpc": "2.0", "error": {"code": code, "message": msg}, "id": req_id})

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": MCP_SERVER_INFO,
        })

    if method == "tools/list":
        return ok({"tools": TOOLS})

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
