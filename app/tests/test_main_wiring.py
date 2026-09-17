"""main.py registers modules through the registry, not by name."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

from src.core.modules import ModuleSpec
from src.main import register_modules


def spec(name, routes=None, slack=None):
    return ModuleSpec(
        name=name,
        required_scopes=(),
        migrations_dir=None,
        register_slack=slack,
        register_routes=routes,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=(),
        default_enabled=True,
    )


def test_registers_routes_and_slack_listeners_for_each_module():
    routes, slack = MagicMock(), MagicMock()
    flask_app, bolt_app = MagicMock(), MagicMock()
    names = register_modules(flask_app, bolt_app, [spec("demo", routes, slack)])
    assert names == ["demo"]
    routes.assert_called_once_with(flask_app)
    slack.assert_called_once_with(bolt_app)


def test_modules_with_no_hooks_are_still_reported():
    names = register_modules(MagicMock(), MagicMock(), [spec("empty")])
    assert names == ["empty"]


def test_a_module_that_fails_to_register_does_not_stop_the_others():
    def boom(_):
        raise RuntimeError("bad module")

    names = register_modules(MagicMock(), MagicMock(), [spec("broken", boom), spec("ok")])
    assert names == ["ok"]


def test_no_module_is_imported_by_name_in_main():
    source = (pathlib.Path(__file__).resolve().parents[1] / "src" / "main.py").read_text()
    for forbidden in ["modules.standup", "modules.kudos", "modules.mcp", "modules.google_chat"]:
        assert forbidden not in source, f"main.py still imports {forbidden} directly"


# Phase 0 moved the files but did not finish moving the responsibilities.
# core/dashboard.py still serves standup's schedule and workflow endpoints,
# core/scheduler.py still runs standup's jobs, and both reach into the module
# through lazy imports. Those belong in the standup module, behind
# register_routes and plan_jobs.
#
# This is a ratchet, not an allowance: the count may fall, never rise. It goes
# to zero when standup owns its own endpoints and jobs.
KNOWN_CORE_TO_MODULE_IMPORTS = 14


def _core_module_imports():
    core = pathlib.Path(__file__).resolve().parents[1] / "src" / "core"
    found = []
    for py in sorted(core.rglob("*.py")):
        for i, line in enumerate(py.read_text().splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue  # prose in a docstring is not a dependency
            if "src.modules" not in stripped:
                continue
            # Reading the registry is allowed anywhere in core: it names no
            # module. Importing src.modules.<name> is what the contract bans.
            if "import REGISTRY" in stripped:
                continue
            found.append(f"{py.name}:{i}: {line.strip()}")
    return found


def test_core_to_module_imports_do_not_grow():
    """The contract's central invariant, ratcheted down rather than asserted.

    Importing REGISTRY is allowed: it names no module. Importing
    src.modules.<name> is the dependency the contract bans.
    """
    found = _core_module_imports()
    assert len(found) <= KNOWN_CORE_TO_MODULE_IMPORTS, (
        "core gained a new dependency on a feature module:\n" + "\n".join(found)
    )


def test_the_ratchet_is_tightened_when_it_improves():
    """Fails if the debt was paid down without lowering the constant."""
    found = _core_module_imports()
    assert len(found) == KNOWN_CORE_TO_MODULE_IMPORTS, (
        f"core to module imports is now {len(found)}; lower KNOWN_CORE_TO_MODULE_IMPORTS to match"
    )


def test_main_itself_is_clean():
    """Whatever core still does, the entrypoint must not name a module."""
    source = (pathlib.Path(__file__).resolve().parents[1] / "src" / "main.py").read_text()
    assert "src.modules." not in source
