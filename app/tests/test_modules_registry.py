"""Activation rules for the module registry."""

from __future__ import annotations

from src.core.modules import ModuleSpec, active_modules, is_active


def spec(name="demo", scopes=(), default_enabled=True):
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
        default_enabled=default_enabled,
    )


def test_enabled_by_default_when_nothing_objects():
    assert is_active(spec(), granted_scopes={"chat:write"}, workspace_setting=None, allowlist=None) is True


def test_disabled_by_default_stays_off_without_a_workspace_row():
    assert is_active(spec(default_enabled=False), granted_scopes=set(), workspace_setting=None, allowlist=None) is False


def test_workspace_row_overrides_the_default():
    assert is_active(spec(default_enabled=False), granted_scopes=set(), workspace_setting=True, allowlist=None) is True
    assert is_active(spec(default_enabled=True), granted_scopes=set(), workspace_setting=False, allowlist=None) is False


def test_missing_scope_wins_over_an_enabled_workspace_row():
    s = spec(scopes=("mpim:write",))
    assert is_active(s, granted_scopes={"chat:write"}, workspace_setting=True, allowlist=None) is False
    assert is_active(s, granted_scopes={"mpim:write"}, workspace_setting=True, allowlist=None) is True


def test_allowlist_wins_over_everything():
    s = spec(name="connect")
    assert is_active(s, granted_scopes=set(), workspace_setting=True, allowlist={"standup"}) is False
    assert is_active(s, granted_scopes=set(), workspace_setting=True, allowlist={"standup", "connect"}) is True


def test_absent_allowlist_means_all_registered_modules():
    assert is_active(spec(), granted_scopes=set(), workspace_setting=None, allowlist=None) is True


def test_active_modules_filters_and_preserves_registry_order():
    registry = (spec("standup"), spec("connect", default_enabled=False), spec("kudos"))
    result = active_modules(registry, granted_scopes=set(), settings={}, allowlist=None)
    assert [m.name for m in result] == ["standup", "kudos"]
