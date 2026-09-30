"""The running release, as baked into the image at build time.

The release workflow passes the tag's version as the APP_VERSION build arg.
A local checkout or a build without it reports "dev".
"""

from __future__ import annotations

import os

APP_VERSION = os.environ.get("APP_VERSION") or "dev"
