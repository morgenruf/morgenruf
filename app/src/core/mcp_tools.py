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
