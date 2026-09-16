"""Compatibility entrypoint for `python src/migrate.py`.

The Helm chart hardcodes this path in the migrate initContainer
(helm/morgenruf/templates/deployment.yaml). A self-hosted user may pin an older
chart while pulling a newer image, so this path must keep working even though
the implementation now lives in src/core/migrations_runner.py.

Do not delete this file without a chart major version bump and a release note.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.migrations_runner import run_migrations  # noqa: E402

__all__ = ["run_migrations"]

if __name__ == "__main__":
    run_migrations()
