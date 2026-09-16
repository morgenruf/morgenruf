"""Kudos module: peer recognition.

This is Donut's Recognition pillar, already shipped inside standup and now
packaged as a module of its own.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec
from src.modules.kudos.dashboard import register_routes
from src.modules.kudos.handlers import register_handlers
from src.modules.kudos.home import home_blocks

MODULE = ModuleSpec(
    name="kudos",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=register_routes,
    plan_jobs=None,
    claim_dm=None,
    purge=None,
    nav=(),
    default_enabled=True,
    home_blocks=home_blocks,
)
