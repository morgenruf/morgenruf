"""Kudos is its own module, extracted from core.db and standup."""

from __future__ import annotations

import inspect
import subprocess
from unittest.mock import MagicMock

from src.core.modules import ModuleSpec
from src.modules import REGISTRY
from src.modules.kudos import MODULE
from src.modules.kudos import db as kudos_db
from tools.check_mechanical_move import changed_functions

FUNCS = ["save_kudos", "get_kudos", "get_kudos_leaderboard"]


def test_kudos_is_a_module_spec_in_the_registry():
    assert isinstance(MODULE, ModuleSpec)
    assert MODULE.name == "kudos"
    assert MODULE in REGISTRY


def test_kudos_requires_no_new_scopes():
    assert MODULE.required_scopes == ()


def test_the_three_functions_moved_verbatim():
    """The extraction must not have altered a single statement."""
    old = subprocess.run(
        ["git", "show", "HEAD:app/src/core/db.py"], capture_output=True, text=True
    ).stdout
    new = inspect.getsource(kudos_db)
    assert changed_functions(old, new, FUNCS) == []


def test_core_db_no_longer_defines_them():
    from src.core import db as core_db

    for name in FUNCS:
        assert not hasattr(core_db, name), f"core.db still defines {name}"


def test_kudos_has_no_catch_all():
    """Kudos only has anchored patterns, so it never needs the DM router."""
    assert MODULE.claim_dm is None


def test_kudos_registers_its_own_slack_listeners():
    assert MODULE.register_slack is not None
    bolt_app = MagicMock()
    MODULE.register_slack(bolt_app)
    assert bolt_app.command.called, "kudos did not register its slash command"
    assert bolt_app.message.called, "kudos did not register its message listener"


def test_kudos_owns_its_http_routes():
    """Core must not import a module, so the kudos API lives in the module."""
    assert MODULE.register_routes is not None
    flask_app = MagicMock()
    MODULE.register_routes(flask_app)
    flask_app.register_blueprint.assert_called_once()


def test_core_dashboard_does_not_reference_kudos():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "src" / "core" / "dashboard.py").read_text()
    assert "kudos" not in src.lower()
