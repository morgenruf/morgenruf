"""Product analytics: which workspaces actually use what, and for how long.

Off unless POSTHOG_API_KEY is set, which means a self-hosted install sends
nothing by default. That is the whole design constraint: the app is MIT
licensed and runs on other people's servers, so telemetry that phones home
without being switched on would be a breach of the deal, not a metric.

Events are workspace-level. The distinct ID is the Slack team ID and nothing
else travels: no Slack user IDs, no channel names, no standup text. The
questions this answers are "did anyone set it up after installing" and "which
modules get used", both of which count workspaces, not people.

POSTHOG_HOST defaults to the US ingestion endpoint, which is where the rest of
the hosting already is. For EEA users that is a transfer, covered by the same
Standard Contractual Clauses the privacy policy already names, and it is why
nothing personal goes into an event in the first place.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading

logger = logging.getLogger(__name__)

DEFAULT_HOST = "https://us.i.posthog.com"

_client = None
_lock = threading.Lock()


def _key() -> str:
    return os.environ.get("POSTHOG_API_KEY", "").strip()


def _host() -> str:
    return os.environ.get("POSTHOG_HOST", "").strip() or DEFAULT_HOST


def enabled() -> bool:
    """Whether an operator has switched analytics on."""
    return bool(_key())


def reset() -> None:
    """Drop the cached client. For tests and for a key that changed underfoot."""
    global _client
    with _lock:
        _client = None


def _get_client():
    """The one client, built on first use. None when unset or unbuildable."""
    global _client
    if _client is not None:
        return _client
    key = _key()
    if not key:
        return None
    with _lock:
        if _client is None:
            import posthog  # noqa: PLC0415

            _client = posthog.Posthog(
                key,
                host=_host(),
                # Nothing here reads feature flags, and local evaluation would
                # poll the API on a timer for definitions we never look at.
                enable_local_evaluation=False,
                # Server-side events. The IP belongs to the pod, not the user.
                disable_geoip=True,
            )
            atexit.register(shutdown)
        return _client


def capture(event: str, team_id: str, **properties) -> bool:
    """Record one workspace-level event. Never raises.

    An exception out of here would land in an install callback or a scheduled
    standup post, so every failure is a log line and a False.
    """
    if not team_id:
        return False
    try:
        client = _get_client()
        if client is None:
            return False
        client.capture(
            event,
            distinct_id=team_id,
            properties=properties or {},
            groups={"workspace": team_id},
        )
        return True
    except Exception as exc:
        logger.warning("Could not capture %s: %s", event, exc)
        return False


def shutdown() -> None:
    """Flush anything queued. Never raises."""
    global _client
    client = _client
    if client is None:
        return
    try:
        client.shutdown()
    except Exception as exc:
        logger.warning("Could not flush analytics: %s", exc)
    finally:
        _client = None
