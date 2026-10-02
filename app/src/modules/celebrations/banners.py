"""The banner image on a birthday or anniversary post.

Sixteen images ship inside the app (banner_images/, drawn from
brand/celebrations/banners.html), so a self-hosted install has them too. They
are served from the app's own public URL, which Slack fetches once and caches.
No image carries a name or a number of years: the mention lives in the message
text, so any banner fits anyone.

A banner is decoration. When there is no public URL, or Slack cannot fetch
the image, the post goes out as text.
"""

from __future__ import annotations

import os
import random
from functools import cache
from pathlib import Path

from src.modules.celebrations.rules import ANNIVERSARY, BIRTHDAY

BANNER_DIR = Path(__file__).parent / "banner_images"
ROUTE_PREFIX = "/celebrations/banners"
ALT_TEXT = {BIRTHDAY: "A birthday banner", ANNIVERSARY: "A work anniversary banner"}
# Slack caches the image, and a file never changes under its name.
CACHE_SECONDS = 30 * 24 * 3600
_SUFFIXES = (".png", ".jpg")


@cache
def available(kind: str) -> tuple[str, ...]:
    """The file names of this kind's banners, in a stable order."""
    return tuple(
        sorted(p.name for p in BANNER_DIR.iterdir() if p.name.startswith(f"{kind}-") and p.suffix in _SUFFIXES)
    )


def is_banner(name: str) -> bool:
    """Only a file that ships as a banner. Anything else, a path included, is not."""
    return any(name in available(kind) for kind in (BIRTHDAY, ANNIVERSARY))


def pick(kind: str, last: str | None, choose=random.choice) -> str | None:
    """A banner for this kind, never the one used last time."""
    options = [name for name in available(kind) if name != last] or list(available(kind))
    return choose(options) if options else None


def url(name: str) -> str | None:
    """Where Slack fetches the banner, or None when the app has no public URL."""
    base = (os.environ.get("APP_URL") or "").rstrip("/")
    return f"{base}{ROUTE_PREFIX}/{name}" if base else None


def image_block(kind: str, name: str) -> dict | None:
    image_url = url(name)
    if not image_url:
        return None
    return {"type": "image", "image_url": image_url, "alt_text": ALT_TEXT[kind]}


def register_route(flask_app) -> None:
    """Serve the banners. Public: Slack fetches them without a session."""
    from flask import abort, send_from_directory  # noqa: PLC0415

    def serve(name: str):
        if not is_banner(name):
            abort(404)
        return send_from_directory(BANNER_DIR, name, max_age=CACHE_SECONDS)

    flask_app.add_url_rule(f"{ROUTE_PREFIX}/<path:name>", "celebration_banner", serve, methods=["GET"])
