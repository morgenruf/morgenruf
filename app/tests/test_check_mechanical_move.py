"""Tests for the mechanical-move checker used to gate the package split."""

from __future__ import annotations

from tools.check_mechanical_move import changed_functions, modules_equivalent

OLD = """
import os
from src.core.db import get_conn

def add(a, b):
    return a + b

def scale(x):
    return x * 2
"""

MOVED_IMPORTS_ONLY = """
import os
from src.core.db import get_conn

def add(a, b):
    return a + b

def scale(x):
    return x * 2
"""

LOGIC_CHANGED = """
import os
from src.core.db import get_conn

def add(a, b):
    return a + b + 1

def scale(x):
    return x * 2
"""


def test_import_only_rewrite_is_equivalent():
    assert modules_equivalent(OLD, MOVED_IMPORTS_ONLY) is True


def test_logic_change_is_not_equivalent():
    assert modules_equivalent(OLD, LOGIC_CHANGED) is False


def test_changed_functions_reports_only_the_edited_one():
    assert changed_functions(OLD, LOGIC_CHANGED, ["add", "scale"]) == ["add"]


def test_changed_functions_is_empty_for_an_import_only_rewrite():
    assert changed_functions(OLD, MOVED_IMPORTS_ONLY, ["add", "scale"]) == []


def test_missing_function_counts_as_changed():
    assert changed_functions(OLD, "def add(a, b):\n    return a + b\n", ["scale"]) == ["scale"]


def test_missing_revision_raises_a_clear_error():
    """A typo'd path during the package split must fail legibly, not traceback."""
    import pytest
    from tools.check_mechanical_move import MissingRevision, _read_git

    with pytest.raises(MissingRevision, match="not found"):
        _read_git("HEAD", "app/src/this_file_does_not_exist.py")


def test_cli_returns_3_for_a_missing_old_path():
    from tools.check_mechanical_move import main

    assert main(["prog", "HEAD", "app/src/this_file_does_not_exist.py", "conftest.py"]) == 3
