"""Guard against pointing the server at addresses it should not reach.

Any code path that makes the server issue an HTTP request to a URL a user
supplied belongs behind `is_safe_webhook_url`. Registered webhooks have gone
through it since they were added; the workflow rule action did not, which is
what issue #81 was about.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def is_safe_webhook_url(url: str) -> bool:
    """Return True when `url` is an http(s) address outside the local network.

    Rejects non-http schemes, the usual loopback names, and any literal IP that
    is private, loopback, link-local or reserved. The link-local case is the one
    that matters most in a cluster: it covers the cloud metadata endpoint.

    A bare hostname passes here without resolution, because what it resolves
    to can change after the webhook is saved. `resolves_to_public` checks
    that at send time.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if host in BLOCKED_HOSTS:
            return False
        try:
            if not _is_public(ipaddress.ip_address(host)):
                return False
        except ValueError:
            pass  # hostname rather than a literal IP, resolved at request time
        return True
    except Exception:
        return False


def _is_public(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # is_global also excludes shared address space (100.64.0.0/10), which some
    # clusters use for pods and services, and is_private alone does not.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def resolves_to_public(url: str) -> bool:
    """True when every address the URL's host resolves to is public.

    Called right before sending, so an internal service name (redis.ns.svc)
    or a public name pointing at a private address is refused. A resolver
    that answers differently between this check and the connection (DNS
    rebinding) is not covered; the delivery also refuses redirects, which is
    the easier way to bounce a request inward.
    """
    try:
        host = urlparse(url).hostname or ""
        if not host:
            return False
        addrs = {ipaddress.ip_address(a) for a in _resolve(host)}
        return bool(addrs) and all(_is_public(a) for a in addrs)
    except Exception:
        return False


def _system_resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [info[4][0].split("%", 1)[0] for info in infos]


# Indirection so tests can answer without DNS (see conftest._no_dns_in_tests).
_resolve = _system_resolve
