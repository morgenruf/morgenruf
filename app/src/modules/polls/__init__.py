"""Polls: ask the team something in Slack and watch the votes come in.

Started with `/morgenruf poll` (a subcommand, so no new slash command in the
Slack app config) or from the App Home. Named or anonymous, one choice or
several, results live or hidden until the poll closes. Anonymous votes are
keyed by an HMAC whose salt is dropped at close; see db.py.

Needs no extra scope: the bot posts only where it is already a member.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.polls.handlers import handle_poll_command, home_blocks, register_handlers

MODULE = ModuleSpec(
    name="polls",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=None,
    plan_jobs=None,
    claim_dm=None,
    purge=None,
    nav=(NavItem(label="Polls", path="#polls"),),
    default_enabled=True,
    delegable=False,
    home_blocks=home_blocks,
    slash_subcommands={"poll": handle_poll_command},
    help_lines=(
        '`/morgenruf poll`: start a poll, or `/morgenruf poll "Question" "Option 1" "Option 2"` to post one here',
    ),
)
