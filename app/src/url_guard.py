"""Guard against pointing the server at addresses it should not reach.

Any code path that makes the server issue an HTTP request to a URL a user
supplied belongs behind `is_safe_webhook_url`. Registered webhooks have gone
through it since they were added; the workflow rule action did not, which is
what issue #81 was about.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

BLOCKED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def is_safe_webhook_url(url: str) -> bool:
    """Return True when `url` is an http(s) address outside the local network.

    Rejects non-http schemes, the usual loopback names, and any literal IP that
    is private, loopback, link-local or reserved. The link-local case is the one
    that matters most in a cluster: it covers the cloud metadata endpoint.

    Known limitation, unchanged from the original implementation in dashboard.py:
    a bare hostname is allowed without resolution, so an internal name that
    resolves to a private address still passes, and nothing here defends against
    DNS rebinding between the check and the request. Closing that needs
    resolution at request time plus a pinned connection.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if host in BLOCKED_HOSTS:
            return False
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
        except ValueError:
            pass  # hostname rather than a literal IP, resolved at request time
        return True
    except Exception:
        return False
