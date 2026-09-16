"""Shared pytest setup.

Puts app/src on sys.path once, so individual test modules do not have to, and
undoes sys.modules stubbing after each test so a MagicMock installed by one
test cannot be imported by the next.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

_APP = os.path.dirname(__file__)
_SRC = os.path.join(_APP, "src")
for _path in (_SRC, _APP):
    if _path not in sys.path:
        sys.path.insert(0, _path)


@pytest.fixture(autouse=True)
def _restore_stubbed_modules():
    """Restore any sys.modules entry a test replaced with a MagicMock."""
    before = dict(sys.modules)
    yield
    for name, module in list(sys.modules.items()):
        if not isinstance(module, MagicMock):
            continue
        original = before.get(name)
        if original is not None and not isinstance(original, MagicMock):
            sys.modules[name] = original
        elif name not in before:
            del sys.modules[name]
