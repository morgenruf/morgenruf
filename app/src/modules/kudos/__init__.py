"""Kudos module: peer recognition.

This is Donut's Recognition pillar, already shipped inside standup and now
packaged as a module of its own.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.kudos.dashboard import register_routes
from src.modules.kudos.handlers import register_handlers
from src.modules.kudos.home import home_blocks
from src.modules.kudos.jobs import plan_jobs
from src.modules.kudos.mcp import tools as mcp_tools

MODULE = ModuleSpec(
    name="kudos",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=register_routes,
    plan_jobs=plan_jobs,
    claim_dm=None,
    purge=None,
    nav=(NavItem(label="Kudos", path="#kudos"),),
    default_enabled=True,
    delegable=True,
    home_blocks=home_blocks,
    mcp_tools=mcp_tools,
)
