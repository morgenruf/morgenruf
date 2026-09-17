"""Morgenruf MCP server over stdio, for Claude Desktop and similar clients.

The HTTP endpoint in http.py is the one the deployment serves. This is the
same set of tools spoken over stdio for a client that runs a local process
instead, and it deliberately builds them from http.py rather than keeping a
second copy: the two lists had already drifted, and a tool added to one was
simply missing from the other.

Usage:
    python src/modules/mcp/server.py

Configuration (env vars):
    DATABASE_URL    PostgreSQL connection URL (required)
    MCP_TEAM_ID     Workspace to query (required — stdio has no request to
                    authenticate, so the workspace is named up front)

Example claude_desktop_config.json:
    {
      "mcpServers": {
        "morgenruf": {
          "command": "python",
          "args": ["/path/to/morgenruf/app/src/modules/mcp/server.py"],
          "env": {
            "DATABASE_URL": "postgresql://morgenruf:pass@localhost:5432/morgenruf",
            "MCP_TEAM_ID": "T01EXAMPLE"
          }
        }
      }
    }
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Running this file directly puts its own directory on sys.path, not the
# application root, so `src.` imports would fail without this.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server import MCPServer  # noqa: E402

from src.modules.mcp.http import TOOLS, _call_tool  # noqa: E402

logger = logging.getLogger(__name__)

server = MCPServer(name="morgenruf")


def _team_id() -> str:
    team = os.environ.get("MCP_TEAM_ID", "").strip()
    if not team:
        raise ValueError("MCP_TEAM_ID is not set, so there is no workspace to query.")
    return team


def _register(tool: dict) -> None:
    """Expose one of the HTTP endpoint's tools over stdio.

    The handler closes over the tool name rather than reading it from the
    call, because MCPServer dispatches by the registered name.
    """
    name = tool["name"]

    async def handler(**arguments: object) -> str:
        return _call_tool(name, dict(arguments), _team_id())

    handler.__name__ = name
    handler.__doc__ = tool.get("description") or name
    server.add_tool(handler, name=name, description=tool.get("description") or name)


def register_all() -> int:
    """Register every tool the HTTP endpoint answers. Returns how many."""
    for tool in TOOLS:
        _register(tool)
    return len(TOOLS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    count = register_all()
    logger.info("morgenruf MCP server: %d tools over stdio", count)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
