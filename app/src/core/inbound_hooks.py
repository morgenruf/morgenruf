"""Webhooks Resend sends us about mail we sent.

Only two events are worth waking somebody for. A bounce means a welcome email
never arrived: the installer believes we never wrote, we believe we did, and
nothing in the app would ever say otherwise. A complaint means somebody pressed
the spam button, which costs sending reputation on a domain shared by every
other message this app sends.

Opens are deliberately not handled. Apple Mail prefetches the tracking pixel,
so the number is wrong in a direction that flatters, and no decision here would
change because of it.

Verification is Svix's scheme, which Resend uses: HMAC-SHA256 over
"<id>.<timestamp>.<body>" keyed by the secret, compared in constant time, with
a timestamp window so a captured delivery cannot be replayed tomorrow.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# Svix's own tolerance. A delivery older than this is a replay, not a retry.
TOLERANCE = 300

WATCHED = ("email.bounced", "email.complained")


def _secret() -> bytes | None:
    raw = os.environ.get("RESEND_WEBHOOK_SECRET", "").strip()
    if not raw:
        return None
    # Svix secrets arrive as "whsec_<base64>"; the bytes are what signs.
    if raw.startswith("whsec_"):
        raw = raw[len("whsec_") :]
    try:
        return base64.b64decode(raw)
    except Exception:
        logger.warning("RESEND_WEBHOOK_SECRET is not valid base64")
        return None


def verify(body: bytes, msg_id: str, timestamp: str, signature_header: str) -> bool:
    """Return True when this delivery really came from Resend and is recent."""
    secret = _secret()
    if not secret or not msg_id or not timestamp or not signature_header:
        return False

    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - sent_at) > TOLERANCE:
        logger.warning("Rejected a webhook delivery outside the timestamp window")
        return False

    signed = f"{msg_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(secret, signed, hashlib.sha256).digest()).decode()

    # The header carries a space-separated list, each "v1,<signature>", because
    # a secret being rotated means two valid signatures at once.
    for part in signature_header.split(" "):
        version, _, candidate = part.partition(",")
        if version == "v1" and hmac.compare_digest(candidate, expected):
            return True
    return False


def handle(payload: dict) -> bool:
    """Alert on the two events that mean something. Returns whether one was sent."""
    event = payload.get("type", "")
    if event not in WATCHED:
        return False

    data = payload.get("data") or {}
    to = data.get("to") or []
    address = (to[0] if isinstance(to, list) and to else to) or "an address"
    subject = data.get("subject", "")

    from src.core.alerts import notify  # noqa: PLC0415

    if event == "email.bounced":
        bounce = data.get("bounce") or {}
        reason = bounce.get("message") or bounce.get("subType") or "no reason given"
        line = f":warning: Email to *{address}* bounced"
        if subject:
            line += f'\n"{subject}"'
        line += f"\n{reason}"
    else:
        line = f":triangular_flag_on_post: *{address}* marked Morgenruf as spam"
        if subject:
            line += f'\n"{subject}"'
        line += "\nThe address is now suppressed."

    sent = notify(line)
    logger.info("Handled %s for one address", event)
    return sent


def suppress_after(payload: dict) -> None:
    """A bounce or a complaint means stop sending there. Resend stops too, but
    our own suppression list is what every send path actually checks."""
    if payload.get("type") not in WATCHED:
        return
    data = payload.get("data") or {}
    to = data.get("to") or []
    address = to[0] if isinstance(to, list) and to else to
    if not address:
        return
    reason = "bounced" if payload.get("type") == "email.bounced" else "complained"
    try:
        import src.core.db as db  # noqa: PLC0415

        db.suppress_email(address, reason=reason)
    except Exception as exc:
        logger.warning("Could not suppress an address after %s: %s", reason, exc)


def parse(body: bytes) -> dict | None:
    try:
        parsed = json.loads(body)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None
