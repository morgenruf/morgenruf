"""Connect: random coffee chats.

Pairs people from a channel on a cadence and introduces them in a group DM.
This is the Donut Introductions equivalent.

Off by default, and gated on scopes the existing installs do not hold, so it
cannot appear for a workspace until an admin re-authorises.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.connect.dashboard import register_routes


def purge(team_id: str) -> None:
    """Delete this module's data for one workspace.

    The import is deferred: src.modules imports every module eagerly, so
    importing db here would load src.core.db as a side effect of touching the
    registry, and tests that stub the database before importing the dashboard
    would silently exercise the real one.
    """
    import src.modules.connect.db as cdb

    cdb.purge(team_id)

MODULE = ModuleSpec(
    name="connect",
    # Opening a group DM and reading it to know whether to nudge. Existing
    # tokens do not carry these, so Connect stays dark until re-authorised.
    required_scopes=("mpim:write", "mpim:history", "users.profile:read"),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=None,
    register_routes=register_routes,
    plan_jobs=None,
    claim_dm=None,
    purge=purge,
    nav=(NavItem(label="Coffee chats", path="#connect"),),
    default_enabled=False,
)
