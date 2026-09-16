"""Test helpers for faking modules under the package layout.

Before the package split, source modules did a lazy `import db`, so a test
could intercept it by replacing the "db" entry in sys.modules.

Under the package layout the same lazy import reads `import src.core.db as
db`, and Python binds that name from `getattr(src.core, "db")` when the parent
package is already imported. Replacing only the sys.modules entry leaves that
attribute pointing at the real module, so the mock is silently bypassed and the
test exercises the real database code.

patch_modules patches both, so the existing faking strategy keeps working.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from unittest import mock


@contextlib.contextmanager
def patch_modules(mapping: dict):
    """Patch sys.modules entries and the matching parent package attributes."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(sys.modules, mapping))
        for dotted, replacement in mapping.items():
            parent_name, _, attr = dotted.rpartition(".")
            if not parent_name:
                continue
            parent = sys.modules.get(parent_name)
            if parent is None:
                try:
                    parent = importlib.import_module(parent_name)
                except Exception:
                    continue
            stack.enter_context(mock.patch.object(parent, attr, replacement, create=True))
        yield
