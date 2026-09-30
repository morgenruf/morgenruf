"""A forked process never shares Postgres connections with its parent.

gunicorn forks its worker after the master opened the pool, and the master's
scheduler keeps using it. Sharing the sockets let a web request and a job
interleave on one connection ("no results to fetch", "PGRES_TUPLES_OK and no
message from the libpq").
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from src.core import db


@pytest.fixture(autouse=True)
def restore_pool():
    before, inherited = db._pool, list(db._inherited_pools)
    yield
    db._pool = before
    db._inherited_pools[:] = inherited


def test_the_child_drops_the_parents_pool_without_closing_it():
    parent_pool = MagicMock()
    db._pool = parent_pool
    db._forget_pool_after_fork()
    assert db._pool is None
    parent_pool.closeall.assert_not_called()
    assert parent_pool in db._inherited_pools


def test_without_a_pool_nothing_happens():
    db._pool = None
    db._forget_pool_after_fork()
    assert db._pool is None


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs fork")
def test_a_real_fork_starts_the_child_without_a_pool():
    db._pool = MagicMock()
    read, write = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.write(write, b"none" if db._pool is None else b"kept")
        os._exit(0)
    os.waitpid(pid, 0)
    assert os.read(read, 4) == b"none"
    assert db._pool is not None
