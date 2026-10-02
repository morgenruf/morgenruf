"""Composing the Slack App Home tab from whatever modules contribute.

The App Home is rendered by one module but belongs to all of them: a person
opening it wants their standup and their recognition, not whichever the
renderer happens to own. Modules expose home_blocks and core collects them, so
the renderer never has to import another module.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The module that renders App Home registers how to redraw it, so core can
# refresh the tab after one of its own buttons (the activation checklist)
# without importing that module.
_refresher = None


def set_refresher(fn) -> None:  # noqa: ANN001
    global _refresher
    _refresher = fn


def refresh_home(team_id: str, user_id: str, client) -> None:  # noqa: ANN001
    """Redraw one person's App Home, when a renderer has registered."""
    if _refresher is None:
        return
    try:
        _refresher(team_id, user_id, client)
    except Exception:
        logger.exception("could not refresh App Home for %s", user_id)


def top_home_blocks(team_id: str, user_id: str) -> list[dict]:
    """Core blocks that belong above everything else: the activation checklist."""
    try:
        from src.core.activation import checklist_blocks  # noqa: PLC0415

        return checklist_blocks(team_id, user_id) or []
    except Exception:
        logger.exception("the activation checklist failed to render on the App Home")
        return []


def extra_home_blocks(team_id: str, user_id: str, exclude: str = "") -> list[dict]:
    """Blocks from every active module except the one doing the rendering.

    A module that raises is skipped rather than taking the whole tab down with
    it: a broken leaderboard should not cost someone their standup.

    The member profile comes first. It belongs to core, not to a module, so it
    is there whichever features the workspace runs, and the renderer trims
    from the end when the tab runs out of room.
    """
    blocks: list[dict] = []
    try:
        from src.core.profile_slack import home_blocks as profile_blocks  # noqa: PLC0415

        blocks.extend(profile_blocks(team_id, user_id) or [])
    except Exception:
        logger.exception("the profile section failed to render on the App Home")

    # The setup email switch, which only the installer (or whoever opted in)
    # sees. Also core: consent to email is not any one feature's business.
    try:
        from src.core.email_consent import home_blocks as email_blocks  # noqa: PLC0415

        blocks.extend(email_blocks(team_id, user_id) or [])
    except Exception:
        logger.exception("the setup email section failed to render on the App Home")

    try:
        from src.core import db  # noqa: PLC0415
        from src.core.modules import active_modules, deploy_allowlist  # noqa: PLC0415
        from src.modules import REGISTRY  # noqa: PLC0415
    except Exception:
        return blocks

    try:
        mods = active_modules(
            REGISTRY,
            granted_scopes=db.granted_scopes(team_id),
            settings=db.module_settings(team_id),
            allowlist=deploy_allowlist(),
        )
    except Exception as exc:
        logger.warning("app home could not resolve modules for %s: %s", team_id, exc)
        return blocks

    for spec in mods:
        if spec.name == exclude or spec.home_blocks is None:
            continue
        try:
            blocks.extend(spec.home_blocks(team_id, user_id) or [])
        except Exception:
            logger.exception("module %s failed to render App Home blocks", spec.name)
    return blocks
