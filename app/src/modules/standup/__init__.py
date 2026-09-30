"""Standup module.

Registered through the module contract rather than wired directly into
main.py, so enabling, disabling or removing it is a registry change.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.standup.handlers import claim_dm, claim_dm_command, on_channel_join, register_handlers

MODULE = ModuleSpec(
    name="standup",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=None,
    plan_jobs=None,
    claim_dm=claim_dm,
    claim_dm_command=claim_dm_command,
    on_channel_join=on_channel_join,
    purge=None,
    nav=(NavItem(label="Standups", path="/"),),
    default_enabled=True,
    delegable=True,
    help_lines=(
        "`/standup`: start your standup now",
        "`/skip`: skip today's standup",
        "In a DM with me, send `standup`, `skip`, `I'm away`, `I'm back`, `help` "
        "or `timezone America/New_York` as a message on its own",
        "While answering, send `pass` to leave a question blank. Press *Edit my answers* to change what you sent",
    ),
)
