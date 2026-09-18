"""Standup module.

Registered through the module contract rather than wired directly into
main.py, so enabling, disabling or removing it is a registry change.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.standup.handlers import claim_dm, register_handlers

MODULE = ModuleSpec(
    name="standup",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=None,
    plan_jobs=None,
    claim_dm=claim_dm,
    purge=None,
    nav=(NavItem(label="Standups", path="/"),),
    default_enabled=True,
    delegable=True,
)
