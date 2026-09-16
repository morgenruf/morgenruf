"""Proves the autouse fixture undoes sys.modules stubbing between tests.

These two tests must run in this order. The first stubs a real module the way
several existing test files do; the second asserts the stub did not survive.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def test_a_stubs_a_real_module():
    import url_guard  # noqa: F401  real module, imported so it is in sys.modules

    sys.modules["url_guard"] = MagicMock()
    assert isinstance(sys.modules["url_guard"], MagicMock)


def test_b_sees_the_real_module_again():
    assert not isinstance(sys.modules.get("url_guard"), MagicMock)
    import url_guard

    assert callable(url_guard.is_safe_webhook_url)
