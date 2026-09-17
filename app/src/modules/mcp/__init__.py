"""MCP module: HTTP surface for the Model Context Protocol server."""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec


def register_routes(flask_app) -> None:
    """Attach the MCP blueprint.

    Imported here rather than at module import time, so that importing the
    registry does not pull the blueprint and its dependencies into memory.
    """
    import logging

    from src.modules.mcp.http import mcp_bp

    flask_app.register_blueprint(mcp_bp)
    logging.getLogger(__name__).info("MCP HTTP endpoint enabled at /mcp")


MODULE = ModuleSpec(
    name="mcp",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=None,
    register_routes=register_routes,
    plan_jobs=None,
    claim_dm=None,
    purge=None,
    nav=(),
    # main.py registered mcp_bp unconditionally, with no environment gate.
    # Introducing one here would silently disable MCP for every workspace, so
    # the default must match today's behavior. The contract still makes it
    # switchable per workspace through workspace_modules.
    default_enabled=True,
)
