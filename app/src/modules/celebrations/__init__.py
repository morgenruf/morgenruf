"""Celebrations: birthdays and work anniversaries, posted to a channel.

Reads the dates from the core member profile and plans around the core
workspace calendar. Off by default. Delegable, so a workspace admin can put
the HR person in charge of it without handing over the rest of the workspace.

Needs no extra scope to run. The 🎉 on each post uses reactions:write, which
the bot uses only where the installation granted it.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.celebrations.dashboard import register_routes
from src.modules.celebrations.handlers import on_channel_join, register_handlers
from src.modules.celebrations.jobs import plan_jobs


def purge(team_id: str) -> None:
    """Delete this module's data for one workspace. Deferred import, as in connect."""
    import src.modules.celebrations.db as cdb

    cdb.purge(team_id)


MODULE = ModuleSpec(
    name="celebrations",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=register_routes,
    plan_jobs=plan_jobs,
    claim_dm=None,
    purge=purge,
    nav=(NavItem(label="Celebrations", path="#celebrations"),),
    default_enabled=False,
    delegable=True,
    help_lines=(
        "Birthdays and work anniversaries are celebrated in the team channel. "
        "Add yours with `/morgenruf profile`, or opt out there",
    ),
    on_channel_join=on_channel_join,
)
