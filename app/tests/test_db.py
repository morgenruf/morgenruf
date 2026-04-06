"""Tests for db.py — database utility functions with mocked psycopg2."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Stub psycopg2 before importing the real db module.
# Other test modules may have put a MagicMock under "db" in sys.modules, so
# we explicitly remove it here to force a fresh import of the real module.
_psycopg2_mock = MagicMock()
_psycopg2_extras_mock = MagicMock()
_pool_mod_mock = MagicMock()
_pool_mod_mock.ThreadedConnectionPool.return_value = None  # skip pool init at import time
sys.modules["psycopg2"] = _psycopg2_mock
sys.modules["psycopg2.extras"] = _psycopg2_extras_mock
sys.modules["psycopg2.pool"] = _pool_mod_mock
sys.modules.pop("db", None)  # discard any mock from other test files

import importlib  # noqa: E402

import db as _db_real  # noqa: E402  — this is the real db module

importlib.reload(_db_real)  # re-run module body now that psycopg2 stubs are in place
db = _db_real


# ---------------------------------------------------------------------------
# Helpers to build a realistic psycopg2 cursor / connection mock
# ---------------------------------------------------------------------------


def _make_cursor(rows=None, fetchone_result=None):
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = fetchone_result
    return cur


def _make_conn(cursor=None):
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    if cursor is not None:
        conn.cursor.return_value = cursor
    return conn


def _mock_pool(fetchone_result=None, fetchall_result=None):
    """Return a (pool_mock, conn_mock, cursor_mock) triple for patching db._pool."""
    cur = _make_cursor(rows=fetchall_result or [], fetchone_result=fetchone_result)
    conn = _make_conn(cur)
    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool, conn, cur


# ---------------------------------------------------------------------------
# db_conn context manager
# ---------------------------------------------------------------------------


class TestDbConnContextManager:
    def test_commits_on_success(self):
        """db_conn commits the connection when no exception is raised."""
        pool, conn, _ = _mock_pool()
        with patch.object(db, "_pool", pool):
            with db.db_conn():
                pass

        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        pool.putconn.assert_called_once_with(conn)

    def test_rolls_back_on_exception(self):
        """db_conn rolls back and re-raises when an exception occurs."""
        pool, conn, _ = _mock_pool()
        with patch.object(db, "_pool", pool):
            with pytest.raises(ValueError):
                with db.db_conn():
                    raise ValueError("boom")

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_raises_when_pool_not_initialised(self):
        with patch.object(db, "_pool", None):
            with pytest.raises(RuntimeError, match="pool not initialised"):
                with db.db_conn():
                    pass


# ---------------------------------------------------------------------------
# get_conn / release_conn
# ---------------------------------------------------------------------------


class TestGetReleaseConn:
    def test_get_conn_calls_pool_getconn(self):
        pool, conn, _ = _mock_pool()
        with patch.object(db, "_pool", pool):
            result = db.get_conn()
        pool.getconn.assert_called_once()
        assert result is conn

    def test_release_conn_calls_pool_putconn(self):
        pool, conn, _ = _mock_pool()
        with patch.object(db, "_pool", pool):
            db.release_conn(conn)
        pool.putconn.assert_called_once_with(conn)

    def test_release_conn_no_op_when_pool_none(self):
        with patch.object(db, "_pool", None):
            db.release_conn(MagicMock())  # should not raise


# ---------------------------------------------------------------------------
# get_installation
# ---------------------------------------------------------------------------


class TestGetInstallation:
    def test_returns_dict_when_row_found(self):
        row = {"team_id": "T1", "bot_token": "xoxb-x"}
        pool, conn, cur = _mock_pool(fetchone_result=row)
        with patch.object(db, "_pool", pool):
            result = db.get_installation("T1")
        assert isinstance(result, dict)

    def test_returns_none_when_no_row(self):
        pool, conn, cur = _mock_pool(fetchone_result=None)
        with patch.object(db, "_pool", pool):
            result = db.get_installation("TMISSING")
        assert result is None


# ---------------------------------------------------------------------------
# is_on_vacation / set_vacation
# ---------------------------------------------------------------------------


class TestVacationHelpers:
    def test_is_on_vacation_true(self):
        pool, conn, cur = _mock_pool(fetchone_result=(True,))
        with patch.object(db, "_pool", pool):
            assert db.is_on_vacation("T1", "U1") is True

    def test_is_on_vacation_false_when_no_row(self):
        pool, conn, cur = _mock_pool(fetchone_result=None)
        with patch.object(db, "_pool", pool):
            assert db.is_on_vacation("T1", "U_MISS") is False

    def test_set_vacation_executes_upsert(self):
        pool, conn, cur = _mock_pool()
        with patch.object(db, "_pool", pool):
            db.set_vacation("T1", "U1", True)  # should not raise
        cur.execute.assert_called()


# ---------------------------------------------------------------------------
# skip_today / is_skipped_today
# ---------------------------------------------------------------------------


class TestSkipHelpers:
    def test_is_skipped_today_true(self):
        pool, conn, cur = _mock_pool(fetchone_result=(1,))
        with patch.object(db, "_pool", pool):
            assert db.is_skipped_today("T1", "U1") is True

    def test_is_skipped_today_false_when_none(self):
        pool, conn, cur = _mock_pool(fetchone_result=None)
        with patch.object(db, "_pool", pool):
            assert db.is_skipped_today("T1", "U1") is False

    def test_skip_today_does_not_raise(self):
        pool, conn, cur = _mock_pool()
        with patch.object(db, "_pool", pool):
            db.skip_today("T1", "U1")
        cur.execute.assert_called()


# ---------------------------------------------------------------------------
# get_member_role
# ---------------------------------------------------------------------------


class TestGetMemberRole:
    def test_returns_admin_when_row_says_admin(self):
        pool, conn, cur = _mock_pool(fetchone_result=("admin",))
        with patch.object(db, "_pool", pool):
            assert db.get_member_role("T1", "U1") == "admin"

    def test_returns_member_when_no_row(self):
        pool, conn, cur = _mock_pool(fetchone_result=None)
        with patch.object(db, "_pool", pool):
            assert db.get_member_role("T1", "U_MISS") == "member"


# ---------------------------------------------------------------------------
# get_active_members
# ---------------------------------------------------------------------------


class TestGetActiveMembers:
    def test_returns_list_of_dicts(self):
        rows = [{"user_id": "U1", "real_name": "Alice"}, {"user_id": "U2", "real_name": "Bob"}]
        pool, conn, cur = _mock_pool(fetchall_result=rows)
        with patch.object(db, "_pool", pool):
            result = db.get_active_members("T1")
        assert isinstance(result, list)

    def test_returns_empty_list_when_no_rows(self):
        pool, conn, cur = _mock_pool(fetchall_result=[])
        with patch.object(db, "_pool", pool):
            result = db.get_active_members("T1")
        assert result == []


# ---------------------------------------------------------------------------
# get_standups
# ---------------------------------------------------------------------------


class TestGetStandups:
    def test_returns_list(self):
        rows = [{"user_id": "U1", "yesterday": "a", "today": "b"}]
        pool, conn, cur = _mock_pool(fetchall_result=rows)
        with patch.object(db, "_pool", pool):
            result = db.get_standups("T1", days=7)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# save_installation
# ---------------------------------------------------------------------------


class TestSaveInstallation:
    def test_new_installation_returns_true(self):
        pool, conn, cur = _mock_pool(fetchone_result=(True,))
        with patch.object(db, "_pool", pool):
            result = db.save_installation("T1", "Acme", "xoxb-tok", "BBOT", "A1", "U99")
        assert result is True

    def test_existing_installation_returns_false(self):
        pool, conn, cur = _mock_pool(fetchone_result=(False,))
        with patch.object(db, "_pool", pool):
            result = db.save_installation("T1", "Acme", "xoxb-tok", "BBOT", "A1", "U99")
        assert result is False
