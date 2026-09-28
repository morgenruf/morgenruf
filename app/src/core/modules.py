"""Module contract.

Core discovers features through an explicit registry of ModuleSpec values and
never imports a feature module by name. Adding a module is one directory under
src/modules plus one line in src.modules.REGISTRY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional


@dataclass(frozen=True)
class NavItem:
    label: str
    path: str


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    required_scopes: tuple[str, ...]
    migrations_dir: Optional[Path]
    register_slack: Optional[Callable]
    register_routes: Optional[Callable]
    plan_jobs: Optional[Callable]
    claim_dm: Optional[Callable]
    purge: Optional[Callable]
    nav: tuple[NavItem, ...]
    default_enabled: bool
    # A DM that is an explicit command, such as `kudos @sam thanks`. Offered to
    # every active module before any claim_dm, so the command still works while
    # another module is mid-conversation with the person. Returns True when it
    # handled the message. Defaulted so a module with no DM commands needs no
    # change.
    claim_dm_command: Optional[Callable] = None
    # Blocks this module contributes to the Slack App Home tab. Defaulted so
    # a module that has nothing to add needs no change.
    home_blocks: Optional[Callable] = None
    # Tools this module exposes over MCP. Same reasoning as home_blocks: the
    # MCP endpoint should not have to import every module to know what it can
    # answer, and a module shipped dark must not advertise tools.
    mcp_tools: Optional[Callable] = None
    # Whether one person can be put in charge of this module without being a
    # workspace admin. False for a module with nothing to administer: Insights
    # only reads, and MCP's keys are workspace-wide. Offering those as grants
    # would be two switches that change nothing.
    delegable: bool = False
    # Lines `/morgenruf help` shows for this module while it is active, so the
    # help lists what this workspace can actually do. Slack mrkdwn, one
    # command or tip per line.
    help_lines: tuple[str, ...] = ()
    # Called with (event, client) when someone joins a channel the bot is in.
    # Bolt runs only the first listener that matches an event, so a second
    # module registering its own member_joined_channel listener would never
    # be called. Core owns the one listener and offers the event to every
    # module the deployment permits; each hook decides whether the channel is
    # one it cares about.
    on_channel_join: Optional[Callable] = None


def deploy_allowlist() -> Optional[set[str]]:
    """Module names this deployment permits, or None when unrestricted.

    MORGENRUF_MODULES lets a build ship a module that is present but dark.
    """
    raw = os.environ.get("MORGENRUF_MODULES", "").strip()
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_active(
    spec: ModuleSpec,
    granted_scopes: Iterable[str],
    workspace_setting: Optional[bool],
    allowlist: Optional[set[str]],
) -> bool:
    """Resolve activation. All four gates must pass, checked in order."""
    if allowlist is not None and spec.name not in allowlist:
        return False
    if not set(spec.required_scopes).issubset(set(granted_scopes)):
        return False
    if workspace_setting is not None:
        return workspace_setting
    return spec.default_enabled


def is_active_for(team_id: str, name: str) -> bool:
    """Whether the module called `name` is active for one workspace.

    For a module's own Slack hooks, which core calls for every module the
    deployment permits and which must stay quiet where the module is off.
    Fails closed: a lookup error means "not active".
    """
    try:
        import src.core.db as db  # noqa: PLC0415
        from src.modules import REGISTRY  # noqa: PLC0415

        spec = next((s for s in REGISTRY if s.name == name), None)
        if spec is None:
            return False
        return is_active(spec, db.granted_scopes(team_id), db.module_settings(team_id).get(name), deploy_allowlist())
    except Exception:
        return False


def active_modules(
    registry: Iterable[ModuleSpec],
    granted_scopes: Iterable[str],
    settings: dict[str, bool],
    allowlist: Optional[set[str]],
) -> list[ModuleSpec]:
    """Registry members active for one workspace, in registry order."""
    granted = set(granted_scopes)
    return [s for s in registry if is_active(s, granted, settings.get(s.name), allowlist)]
