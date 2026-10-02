"""Watercooler: a conversation question posted to a channel on a schedule.

People reply in the thread. Built-in questions in four categories, plus the
workspace's own; any built-in can be hidden for this workspace. Several
channels, each with its own days and time, skipping company holidays.

Off by default and delegable. Needs no extra scope: it posts only where the
bot is a member, and the 🙋 on each post uses reactions:write only where the
installation granted it. The bot cannot read replies (no channels:history),
so it counts posts, not answers.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.watercooler.dashboard import register_routes
from src.modules.watercooler.handlers import handle_command, home_blocks, register_handlers, start_default
from src.modules.watercooler.jobs import plan_jobs


def purge(team_id: str) -> None:
    import src.modules.watercooler.db as wdb  # noqa: PLC0415

    wdb.purge(team_id)


MODULE = ModuleSpec(
    name="watercooler",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=register_routes,
    plan_jobs=plan_jobs,
    claim_dm=None,
    purge=purge,
    nav=(NavItem(label="Watercooler", path="#watercooler"),),
    default_enabled=False,
    delegable=True,
    home_blocks=home_blocks,
    slash_subcommands={"watercooler": handle_command},
    help_lines=("`/morgenruf watercooler`: post a conversation question in a channel a few times a week",),
    quick_start=("Also post a watercooler question here Mon, Wed, Fri", start_default),
)
