"""One catch-all DM listener, offered to each active module in registry order."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.dm_router import DMContext, route_dm
from src.core.modules import ModuleSpec


def spec(name, claim):
    return ModuleSpec(
        name=name,
        required_scopes=(),
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=claim,
        purge=None,
        nav=(),
        default_enabled=True,
    )


def ctx(text="hello"):
    return DMContext(team_id="T1", user_id="U1", channel_id="D1", text=text, event={}, client=MagicMock())


def test_first_claimer_wins_and_later_modules_are_not_offered():
    second = MagicMock(return_value=True)
    modules = [spec("standup", lambda c: True), spec("connect", second)]
    assert route_dm(modules, ctx(), fallback=None) == "standup"
    second.assert_not_called()


def test_falls_through_to_the_next_module_when_the_first_declines():
    modules = [spec("standup", lambda c: False), spec("connect", lambda c: True)]
    assert route_dm(modules, ctx(), fallback=None) == "connect"


def test_fallback_runs_when_nobody_claims():
    fallback = MagicMock()
    modules = [spec("standup", lambda c: False)]
    assert route_dm(modules, ctx(), fallback=fallback) is None
    fallback.assert_called_once()


def test_modules_without_claim_dm_are_skipped():
    modules = [spec("mcp", None), spec("standup", lambda c: True)]
    assert route_dm(modules, ctx(), fallback=None) == "standup"


def test_a_raising_module_does_not_block_the_others():
    def boom(c):
        raise RuntimeError("module is broken")

    modules = [spec("broken", boom), spec("standup", lambda c: True)]
    assert route_dm(modules, ctx(), fallback=None) == "standup"
