"""Composing the Slack App Home tab from whatever modules contribute.

The App Home is rendered by one module but belongs to all of them: a person
opening it wants their standup and their recognition, not whichever the
renderer happens to own. Modules expose home_blocks and core collects them, so
the renderer never has to import another module.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def extra_home_blocks(team_id: str, user_id: str, exclude: str = "") -> list[dict]:
    """Blocks from every active module except the one doing the rendering.

    A module that raises is skipped rather than taking the whole tab down with
    it: a broken leaderboard should not cost someone their standup.
    """
    try:
        from src.core import db  # noqa: PLC0415
        from src.core.modules import active_modules, deploy_allowlist  # noqa: PLC0415
        from src.modules import REGISTRY  # noqa: PLC0415
    except Exception:
        return []

    try:
        mods = active_modules(
            REGISTRY,
            granted_scopes=db.granted_scopes(team_id),
            settings=db.module_settings(team_id),
            allowlist=deploy_allowlist(),
        )
    except Exception as exc:
        logger.warning("app home could not resolve modules for %s: %s", team_id, exc)
        return []

    blocks: list[dict] = []
    for spec in mods:
        if spec.name == exclude or spec.home_blocks is None:
            continue
        try:
            blocks.extend(spec.home_blocks(team_id, user_id) or [])
        except Exception:
            logger.exception("module %s failed to render App Home blocks", spec.name)
    return blocks
