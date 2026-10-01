"""Pulse: a weekly anonymous check-in by DM.

A workspace admin turns it on; each week everyone in the audience gets a DM
with a 1 to 5 mood question, and every fourth week an eNPS question too.
Answers are stored without a name and shown only as team averages once at
least five people answered (privacy.MIN_GROUP). Buttons only, no free text.

Off by default. Needs no extra scope: it only sends DMs, which the bot can
already do, and `/morgenruf pulse` is a subcommand.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.pulse.handlers import handle_pulse_command, home_blocks, register_handlers
from src.modules.pulse.jobs import plan_jobs

MODULE = ModuleSpec(
    name="pulse",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=None,
    plan_jobs=plan_jobs,
    claim_dm=None,
    purge=None,
    nav=(NavItem(label="Pulse", path="#pulse"),),
    default_enabled=False,
    delegable=False,
    home_blocks=home_blocks,
    slash_subcommands={"pulse": handle_pulse_command},
    help_lines=("`/morgenruf pulse`: how the anonymous weekly check-in works and whether it is on",),
)
