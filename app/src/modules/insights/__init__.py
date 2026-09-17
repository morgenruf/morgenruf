"""Insights: what the standup and recognition data says together.

Each competitor holds one slice. Geekbot has the standups, HeyTaco has the
recognition, Donut has the pairing. Morgenruf has all three in one database,
and these are the questions that only become answerable once they are joined.
"""

from __future__ import annotations

from src.core.modules import ModuleSpec, NavItem
from src.modules.insights.dashboard import register_routes
from src.modules.insights.mcp import tools as mcp_tools

MODULE = ModuleSpec(
    name="insights",
    required_scopes=(),
    migrations_dir=None,  # reads existing tables; owns none of its own
    register_slack=None,
    register_routes=register_routes,
    plan_jobs=None,
    claim_dm=None,
    purge=None,  # stores nothing, so there is nothing to purge
    nav=(NavItem(label="Insights", path="#insights"),),
    default_enabled=True,
    mcp_tools=mcp_tools,
)
