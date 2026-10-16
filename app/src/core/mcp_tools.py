"""Collecting MCP tools from whatever modules are active for a workspace.

The MCP endpoint answers questions about a single workspace, and which
features that workspace has turned on is already decided by the module
contract. Reusing it here means an assistant is never offered a tool for a
module the workspace has switched off, or that this deployment ships dark.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def module_tools(team_id: str) -> dict[str, dict[str, Any]]:
    """`{tool_name: {"name", "description", "inputSchema", "handler"}}`.

    A module that raises is skipped rather than taking the whole tool list
    down with it: a broken kudos query should not cost an assistant its
    access to standups.
    """
    try:
        from src.core import db  # noqa: PLC0415
        from src.core.modules import active_modules, deploy_allowlist  # noqa: PLC0415
        from src.modules import REGISTRY  # noqa: PLC0415
    except Exception:
        return {}

    try:
        mods = active_modules(
            REGISTRY,
            granted_scopes=db.granted_scopes(team_id),
            settings=db.module_settings(team_id),
            allowlist=deploy_allowlist(),
        )
    except Exception as exc:
        logger.warning("mcp could not resolve modules for %s: %s", team_id, exc)
        return {}

    tools: dict[str, dict[str, Any]] = {}
    for spec in mods:
        if spec.mcp_tools is None:
            continue
        try:
            for tool in spec.mcp_tools() or []:
                name = tool.get("name")
                if not name:
                    continue
                # First module to claim a name keeps it, and the collision is
                # logged rather than silently resolved.
                if name in tools:
                    logger.warning("mcp tool name %r claimed twice; keeping the first", name)
                    continue
                tools[name] = tool
        except Exception:
            logger.exception("module %s failed to list MCP tools", spec.name)
    return tools


def public_tools(team_id: str) -> list[dict[str, Any]]:
    """The same list with handlers stripped, which is what MCP advertises."""
    return [{k: v for k, v in tool.items() if k != "handler"} for tool in module_tools(team_id).values()]


def handler_for(team_id: str, name: str) -> Callable | None:
    tool = module_tools(team_id).get(name)
    return tool.get("handler") if tool else None


def window(args: dict, default_days: int = 30, default_limit: int = 50) -> tuple[int, int]:
    """`days` (1 to 365) and `limit` (1 to 200) from a tool call's arguments."""
    days = max(1, min(int(args.get("days") or default_days), 365))
    limit = max(1, min(int(args.get("limit") or default_limit), 200))
    return days, limit


def member_identities(team_id: str) -> dict[str, dict[str, Any]]:
    """`{user_id: {"user_id", "name", "email"?}}`, the identity get_members carries.

    Email only where the member row has one, so an outside tool can join on it
    when it is there and fall back to the Slack user id when it is not.
    """
    from src.core import db  # noqa: PLC0415

    out: dict[str, dict[str, Any]] = {}
    for m in db.get_all_members(team_id):
        person = {"user_id": m["user_id"], "name": m.get("real_name") or m.get("display_name") or ""}
        if m.get("email"):
            person["email"] = m["email"]
        out[m["user_id"]] = person
    return out


def identity(people: dict[str, dict[str, Any]], user_id: str) -> dict[str, Any]:
    return people.get(user_id) or {"user_id": user_id, "name": ""}
