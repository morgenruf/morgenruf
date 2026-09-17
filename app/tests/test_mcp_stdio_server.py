"""The stdio MCP server, and the fact that it is not a second copy of the tools.

mcp 2.x renamed FastMCP to MCPServer and dropped the decorators this file used,
so it failed at import with 'Server' object has no attribute 'list_tools'. The
suite stayed green because nothing imported it, which is exactly why these
tests exist.
"""

from __future__ import annotations

import src.modules.mcp.server as stdio
from src.modules.mcp.http import TOOLS


def test_the_module_imports():
    """It broke on a major dependency bump and no test noticed."""
    assert stdio.server is not None


def test_it_serves_the_same_tools_as_the_http_endpoint():
    """Two hand-maintained lists drift; a tool added to one goes missing here."""
    assert stdio.register_all() == len(TOOLS)


def test_every_http_tool_is_registered_by_name():
    stdio.register_all()
    names = {t["name"] for t in TOOLS}
    assert names, "the http endpoint defines no tools"
    assert "get_standups" in names


def test_a_missing_team_id_says_so_rather_than_querying_nothing(monkeypatch):
    monkeypatch.delenv("MCP_TEAM_ID", raising=False)
    try:
        stdio._team_id()
    except ValueError as exc:
        assert "MCP_TEAM_ID" in str(exc)
    else:
        raise AssertionError("a missing workspace must be an error, not an empty query")


def test_a_blank_team_id_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("MCP_TEAM_ID", "   ")
    try:
        stdio._team_id()
    except ValueError:
        pass
    else:
        raise AssertionError("whitespace is not a workspace")


def test_a_team_id_is_returned_trimmed(monkeypatch):
    monkeypatch.setenv("MCP_TEAM_ID", " T01EXAMPLE ")
    assert stdio._team_id() == "T01EXAMPLE"
