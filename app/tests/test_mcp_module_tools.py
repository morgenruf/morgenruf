"""Modules contributing their own MCP tools.

The gate that decides whether a workspace sees a dashboard page is the one
that decides whether an assistant sees a tool. A module switched off, or
shipped dark by a deployment, must not advertise anything.
"""

from __future__ import annotations

import pytest
from src.core.mcp_tools import handler_for, module_tools, public_tools
from src.core.modules import ModuleSpec

from tests.support import patch_modules


def spec(name, tools, *, scopes=(), default=True):
    return ModuleSpec(
        name=name,
        required_scopes=scopes,
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=(),
        default_enabled=default,
        mcp_tools=(lambda: tools) if tools is not None else None,
    )


def tool(name, result="ok"):
    return {
        "name": name,
        "description": "d",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": lambda args, team_id: result,
    }


class FakeDb:
    def __init__(self, scopes=(), settings=None):
        self._scopes = scopes
        self._settings = settings or {}

    def granted_scopes(self, team_id):
        return self._scopes

    def module_settings(self, team_id):
        return self._settings


@pytest.fixture
def registry(monkeypatch):
    """Install a fake registry and db, and clear any deploy allowlist."""
    monkeypatch.delenv("MORGENRUF_MODULES", raising=False)

    def install(specs, db=None):
        import types

        mods = types.ModuleType("src.modules")
        mods.REGISTRY = specs
        return patch_modules(
            {
                "src.modules": mods,
                "src.core.db": db or FakeDb(),
            }
        )

    return install


def test_an_active_module_contributes_its_tools(registry):
    with registry([spec("kudos", [tool("get_kudos_leaderboard")])]):
        assert "get_kudos_leaderboard" in module_tools("T1")


def test_a_module_switched_off_advertises_nothing(registry):
    """The workspace toggle is what decides, not the module's own default."""
    db = FakeDb(settings={"kudos": False})
    with registry([spec("kudos", [tool("get_kudos_leaderboard")])], db):
        assert module_tools("T1") == {}


def test_a_module_missing_its_scopes_advertises_nothing(registry):
    s = spec("connect", [tool("list_coffee_chat_programs")], scopes=("mpim:write",))
    with registry([s], FakeDb(scopes=())):
        assert module_tools("T1") == {}


def test_a_module_with_its_scopes_does_advertise(registry):
    s = spec("connect", [tool("list_coffee_chat_programs")], scopes=("mpim:write",))
    with registry([s], FakeDb(scopes=("mpim:write",))):
        assert "list_coffee_chat_programs" in module_tools("T1")


def test_a_module_shipped_dark_advertises_nothing(registry, monkeypatch):
    monkeypatch.setenv("MORGENRUF_MODULES", "standup")
    with registry([spec("kudos", [tool("get_kudos_leaderboard")])]):
        assert module_tools("T1") == {}


def test_a_module_with_no_tools_is_skipped(registry):
    with registry([spec("insights", None)]):
        assert module_tools("T1") == {}


def test_one_broken_module_does_not_hide_the_others(registry):
    """A kudos query that raises must not cost an assistant its coffee chat tools."""
    broken = spec("kudos", None)
    broken = ModuleSpec(**{**broken.__dict__, "mcp_tools": _raise})
    good = spec("connect", [tool("list_coffee_chat_programs")])
    with registry([broken, good]):
        assert list(module_tools("T1")) == ["list_coffee_chat_programs"]


def _raise():
    raise RuntimeError("boom")


def test_a_duplicate_tool_name_keeps_the_first(registry):
    a = spec("kudos", [tool("get_stats", "from-kudos")])
    b = spec("insights", [tool("get_stats", "from-insights")])
    with registry([a, b]):
        assert handler_for("T1", "get_stats")({}, "T1") == "from-kudos"


def test_handlers_are_not_advertised(registry):
    """The handler is a Python callable and has no place in a JSON tool list."""
    with registry([spec("kudos", [tool("get_kudos_leaderboard")])]):
        listed = public_tools("T1")
        assert listed and all("handler" not in t for t in listed)
        assert listed[0]["name"] == "get_kudos_leaderboard"


def test_an_unknown_tool_has_no_handler(registry):
    with registry([spec("kudos", [tool("get_kudos_leaderboard")])]):
        assert handler_for("T1", "nope") is None


class TestShippedModules:
    """The real modules, so a rename or a bad schema is caught here."""

    def test_every_shipped_tool_is_well_formed(self):
        from src.modules.connect.mcp import tools as connect_tools
        from src.modules.insights.mcp import tools as insights_tools
        from src.modules.kudos.mcp import tools as kudos_tools

        for listed in (kudos_tools(), connect_tools(), insights_tools()):
            assert listed
            for t in listed:
                assert t["name"] and t["description"]
                assert t["inputSchema"]["type"] == "object"
                assert callable(t["handler"])

    def test_tool_names_are_unique_across_modules(self):
        from src.modules.connect.mcp import tools as connect_tools
        from src.modules.insights.mcp import tools as insights_tools
        from src.modules.kudos.mcp import tools as kudos_tools

        names = [t["name"] for t in kudos_tools() + connect_tools() + insights_tools()]
        assert len(names) == len(set(names)), f"duplicate tool name: {names}"

    def test_no_module_tool_collides_with_a_standup_tool(self):
        from src.modules.connect.mcp import tools as connect_tools
        from src.modules.insights.mcp import tools as insights_tools
        from src.modules.kudos.mcp import tools as kudos_tools
        from src.modules.mcp.http import TOOLS

        core = {t["name"] for t in TOOLS}
        for t in kudos_tools() + connect_tools() + insights_tools():
            assert t["name"] not in core

    def test_a_tool_needing_an_id_says_so_rather_than_failing(self):
        """An assistant calling without program_id should be told what to call first."""
        from src.modules.connect.mcp import tools as connect_tools

        rounds = next(t for t in connect_tools() if t["name"] == "get_coffee_chat_rounds")
        out = rounds["handler"]({}, "T1")
        assert "program_id" in out["error"]
        assert "list_coffee_chat_programs" in out["error"]
