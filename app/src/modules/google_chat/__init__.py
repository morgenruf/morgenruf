"""Google Chat module: alternative platform surface."""

from __future__ import annotations

import os
from pathlib import Path

from src.core.modules import ModuleSpec


def register_routes(flask_app) -> None:
    """Attach the Google Chat blueprint, if this deployment has credentials.

    main.py gated this on GOOGLE_CREDENTIALS, so the check lives here now.
    It cannot live in default_enabled: that is the per-workspace gate, applied
    when a request or job resolves activation, whereas route registration
    happens once at process start.

    The try/except mirrors main.py: a Google Chat import failure must not stop
    the process from starting.
    """
    import logging

    logger = logging.getLogger(__name__)
    if not os.environ.get("GOOGLE_CREDENTIALS"):
        return
    try:
        from src.modules.google_chat.handler import google_chat_bp

        flask_app.register_blueprint(google_chat_bp)
        logger.info("Google Chat integration enabled")
    except Exception as exc:
        logger.warning("Could not register Google Chat blueprint: %s", exc)


MODULE = ModuleSpec(
    name="google_chat",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=None,
    register_routes=register_routes,
    plan_jobs=None,
    claim_dm=None,
    purge=None,
    nav=(),
    # Mirrors the GOOGLE_CREDENTIALS check main.py used.
    default_enabled=bool(os.environ.get("GOOGLE_CREDENTIALS")),
)
