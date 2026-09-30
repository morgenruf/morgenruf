"""Public links that Slack messages point people at.

Messages used to hardcode api.morgenruf.dev, so a self-hosted install sent its
members to the hosted dashboard. Everything here follows APP_URL instead.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

_HOSTED_SUPPORT = "https://morgenruf.dev/support/"
_SELF_HOSTED_SUPPORT = "https://github.com/morgenruf/morgenruf/issues"


def app_url() -> str:
    return (os.environ.get("APP_URL") or "https://api.morgenruf.dev").rstrip("/")


def dashboard_url() -> str:
    return f"{app_url()}/dashboard"


def _is_hosted() -> bool:
    host = (urlparse(app_url()).hostname or "").lower()
    return host == "morgenruf.dev" or host.endswith(".morgenruf.dev")


def support_url() -> str:
    """The support page on hosted, GitHub issues on a self-hosted install."""
    return _HOSTED_SUPPORT if _is_hosted() else _SELF_HOSTED_SUPPORT
