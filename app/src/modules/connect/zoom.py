"""Zoom account linking, so a coffee chat can carry a real meeting.

Donut offers the same thing; the difference here is when the meeting is made.
Donut hands you a room to join now. This waits until both people have agreed a
time and then schedules the meeting for that time, so what lands in Slack is a
meeting on a day both accepted rather than a link to press immediately.

Two Zoom behaviours drive the design:

  * An access token lasts one hour, so it is refreshed on use rather than on a
    timer.
  * Refreshing rotates the refresh token. The response carries a new one and
    the old one is dead the moment it is used. Failing to persist the new one
    breaks the link permanently, so the store is written before the caller
    gets the token back.

No Zoom credentials in the deployment means the feature is simply absent: the
button is not shown and nothing raises.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://zoom.us/oauth/authorize"
TOKEN_URL = "https://zoom.us/oauth/token"
API_BASE = "https://api.zoom.us/v2"

# Creating a scheduled meeting on the authorising user's own account.
SCOPES = "meeting:write:meeting user:read:user"

_TIMEOUT = 10
# Refreshed a little early rather than on the exact second, so a slow request
# cannot be sent with a token that expires mid-flight.
_EXPIRY_MARGIN = timedelta(minutes=2)


def configured() -> bool:
    """Whether this deployment has Zoom credentials at all."""
    return bool(os.environ.get("ZOOM_CLIENT_ID") and os.environ.get("ZOOM_CLIENT_SECRET"))


def _creds() -> tuple[str, str]:
    return os.environ.get("ZOOM_CLIENT_ID", ""), os.environ.get("ZOOM_CLIENT_SECRET", "")


def redirect_uri() -> str:
    base = (os.environ.get("APP_URL") or "").rstrip("/")
    return f"{base}/connect/zoom/callback"


def authorize_url(state: str) -> str:
    from urllib.parse import urlencode  # noqa: PLC0415

    client_id, _ = _creds()
    return (
        AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri(),
                "state": state,
            }
        )
    )


def exchange_code(code: str) -> dict | None:
    """Swap the authorisation code for a token pair."""
    return _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri()})


def _token_request(data: dict) -> dict | None:
    client_id, client_secret = _creds()
    try:
        resp = requests.post(
            TOKEN_URL,
            data=data,
            auth=(client_id, client_secret),
            timeout=_TIMEOUT,
        )
    except Exception:
        logger.exception("zoom: token request failed to send")
        return None
    if resp.status_code != 200:
        # The body names the reason ("invalid_grant" for a dead refresh token),
        # which is what the caller needs to decide between retry and re-link.
        logger.warning("zoom: token request rejected (%s): %s", resp.status_code, resp.text[:200])
        return None
    try:
        return resp.json()
    except Exception:
        logger.exception("zoom: token response was not json")
        return None


def store_from_token_response(team_id: str, user_id: str, payload: dict) -> None:
    """Persist a token pair, including the rotated refresh token."""
    import src.modules.connect.db as cdb  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    cdb.save_zoom_link(
        team_id=team_id,
        user_id=user_id,
        access_token=payload.get("access_token") or "",
        refresh_token=payload.get("refresh_token") or "",
        access_expires_at=now + timedelta(seconds=int(payload.get("expires_in") or 3600)),
        # Zoom's refresh tokens die after 90 days unused. Recorded so the UI can
        # ask for a reconnect instead of failing at the moment it is needed.
        refresh_expires_at=now + timedelta(days=90),
    )


def access_token_for(team_id: str, user_id: str) -> str | None:
    """A usable access token, refreshing first if it is close to expiry.

    Returns None when this person has no link, has revoked it, or the refresh
    token has died. The caller treats that as "no Zoom for this match", never
    as an error worth surfacing to the pair.
    """
    import src.modules.connect.db as cdb  # noqa: PLC0415

    if not configured():
        return None
    link = cdb.zoom_link(team_id, user_id)
    if not link:
        return None

    expires = link.get("access_expires_at")
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires - _EXPIRY_MARGIN > datetime.now(timezone.utc):
        return link.get("access_token") or None

    payload = _token_request({"grant_type": "refresh_token", "refresh_token": link.get("refresh_token") or ""})
    if not payload or not payload.get("access_token"):
        # A dead refresh token is not retryable: the person has to link again.
        cdb.revoke_zoom_link(team_id, user_id)
        logger.info("zoom: link for %s/%s needs reconnecting", team_id, user_id)
        return None

    # Written before returning, because the refresh token in this response has
    # already replaced the stored one on Zoom's side.
    store_from_token_response(team_id, user_id, payload)
    return payload.get("access_token")


def whoami(access_token: str) -> dict:
    try:
        resp = requests.get(
            f"{API_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_TIMEOUT,
        )
        return resp.json() if resp.status_code == 200 else {}
    except Exception:
        logger.exception("zoom: could not read the linked account")
        return {}


def create_meeting(access_token: str, start: datetime, minutes: int, topic: str = "Coffee chat") -> dict | None:
    """Schedule a meeting at an agreed time and return Zoom's response.

    `start` is UTC. Zoom takes the start time without an offset alongside an
    explicit timezone, so it is sent as UTC and labelled as such rather than
    relying on the account's own timezone, which is whatever the host set.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    body = {
        "topic": topic,
        "type": 2,  # a scheduled meeting, not an instant one
        "start_time": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration": max(1, int(minutes)),
        "timezone": "UTC",
        "settings": {
            "join_before_host": True,  # neither of them is really the host
            "waiting_room": False,
        },
    }
    try:
        resp = requests.post(
            f"{API_BASE}/users/me/meetings",
            json=body,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_TIMEOUT,
        )
    except Exception:
        logger.exception("zoom: meeting request failed to send")
        return None
    if resp.status_code not in (200, 201):
        logger.warning("zoom: meeting not created (%s): %s", resp.status_code, resp.text[:200])
        return None
    try:
        return resp.json()
    except Exception:
        return None
