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
    # Blocks this module contributes to the Slack App Home tab. Defaulted so
    # a module that has nothing to add needs no change.
    home_blocks: Optional[Callable] = None
    # Tools this module exposes over MCP. Same reasoning as home_blocks: the
    # MCP endpoint should not have to import every module to know what it can
    # answer, and a module shipped dark must not advertise tools.
    mcp_tools: Optional[Callable] = None


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


def active_modules(
    registry: Iterable[ModuleSpec],
    granted_scopes: Iterable[str],
    settings: dict[str, bool],
    allowlist: Optional[set[str]],
) -> list[ModuleSpec]:
    """Registry members active for one workspace, in registry order."""
    granted = set(granted_scopes)
    return [s for s in registry if is_active(s, granted, settings.get(s.name), allowlist)]
