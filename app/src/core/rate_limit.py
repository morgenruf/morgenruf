"""A small in-process rate limiter for the endpoints anyone can call.

The public feed, the email links, the OAuth callback and MCP authentication
take no session, so nothing else slows down someone guessing tokens or
hammering the database through them. Counts are per client address and per
process: with several pods the effective limit is that many times higher,
which is still a ceiling where there was none, without a shared store.
"""

from __future__ import annotations

import time
from collections import deque
from functools import wraps
from threading import Lock

# Past this many tracked addresses the stale ones are dropped, so a flood from
# many addresses cannot grow memory without bound.
_MAX_KEYS = 10_000


class RateLimiter:
    """At most `limit` hits per `window` seconds for each key."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = {}
        self._lock = Lock()

    def _recent(self, key: str, now: float) -> deque:
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= _MAX_KEYS:
                self._prune(now)
            hits = self._hits[key] = deque()
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        return hits

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            del self._hits[key]
        if len(self._hits) >= _MAX_KEYS:
            self._hits.clear()

    def limited(self, key: str) -> bool:
        """True when this key is over the limit, without counting a hit."""
        now = time.monotonic()
        with self._lock:
            return len(self._recent(key, now)) >= self.limit

    def hit(self, key: str) -> bool:
        """Count one hit. True when it was within the limit."""
        now = time.monotonic()
        with self._lock:
            hits = self._recent(key, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key() -> str:
    """The caller's address. ProxyFix has already applied X-Forwarded-For."""
    from flask import request  # noqa: PLC0415

    return request.remote_addr or "unknown"


def too_many():
    from flask import jsonify  # noqa: PLC0415

    response = jsonify(error="Too many requests. Try again in a minute.")
    response.status_code = 429
    response.headers["Retry-After"] = "60"
    return response


def rate_limited(limiter: RateLimiter):
    """Refuse a view with 429 once the caller is over the limiter's budget."""

    def decorate(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not limiter.hit(client_key()):
                return too_many()
            return view(*args, **kwargs)

        return wrapper

    return decorate


# The budgets. Generous for a person, tight for a script.
FEED = RateLimiter(limit=60, window=60)
EMAIL_LINKS = RateLimiter(limit=20, window=60)
OAUTH_CALLBACK = RateLimiter(limit=20, window=60)
MCP_AUTH_FAILURES = RateLimiter(limit=20, window=60)
# Keyed by person, not address: each report opens a GitHub issue.
FEEDBACK = RateLimiter(limit=5, window=3600)

ALL = (FEED, EMAIL_LINKS, OAUTH_CALLBACK, MCP_AUTH_FAILURES, FEEDBACK)
