"""Where an install came from: /install?ref=<source>.

The ref is a plain tag, stored once on the first install, so the Monday
report can count activated workspaces per source. Anything that is not a
short lowercase tag is dropped rather than stored.
"""

from __future__ import annotations

import pytest
from src.core.oauth import clean_ref


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("linkedin", "linkedin"),
        ("LinkedIn", "linkedin"),
        ("post-2026_10", "post-2026_10"),
        ("", ""),
        (None, ""),
        ("a" * 33, ""),
        ("<script>", ""),
        ("-leading", ""),
        ("has space", ""),
    ],
)
def test_clean_ref(raw, expected):
    assert clean_ref(raw) == expected


def test_set_install_source_only_fills_an_empty_source(fake_cursor_db):
    from src.core import db

    db.set_install_source("T1", "linkedin")
    sql, params = fake_cursor_db.calls[0]
    assert "install_source IS NULL" in sql
    assert params == ("linkedin", "T1")
