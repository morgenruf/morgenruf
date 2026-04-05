"""Tests for session_store.py — Redis-backed session management with in-memory fallback."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


@pytest.fixture(autouse=True)
def reset_session_store():
    """Reset module-level state before each test."""
    import session_store

    session_store._redis = None
    session_store._memory.clear()
    yield
    session_store._redis = None
    session_store._memory.clear()


class TestInMemoryFallback:
    """When REDIS_URL is not set, all operations use in-memory dict."""

    def test_set_and_get(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import get_session, set_session

        set_session("U1", {"step": 1, "answers": []})
        result = get_session("U1")
        assert result == {"step": 1, "answers": []}

    def test_get_missing_returns_none(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import get_session

        assert get_session("U_NONEXISTENT") is None

    def test_delete_session(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import delete_session, get_session, set_session

        set_session("U1", {"step": 2})
        delete_session("U1")
        assert get_session("U1") is None

    def test_delete_nonexistent_no_error(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import delete_session

        delete_session("GHOST")  # should not raise

    def test_has_session_true(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import has_session, set_session

        set_session("U1", {"step": 0})
        assert has_session("U1") is True

    def test_has_session_false(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import has_session

        assert has_session("U_MISSING") is False

    def test_overwrite_session(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import get_session, set_session

        set_session("U1", {"step": 0})
        set_session("U1", {"step": 3, "answers": ["a", "b", "c"]})
        result = get_session("U1")
        assert result["step"] == 3
        assert result["answers"] == ["a", "b", "c"]

    def test_multiple_users_isolated(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from session_store import get_session, set_session

        set_session("U1", {"step": 1})
        set_session("U2", {"step": 2})
        assert get_session("U1")["step"] == 1
        assert get_session("U2")["step"] == 2


class TestRedisBackend:
    """When Redis is available, operations use Redis."""

    def _make_redis_mock(self, stored: dict | None = None):
        r = MagicMock()
        r.ping.return_value = True
        store = {}

        def mock_setex(key, ttl, value):
            store[key] = value

        def mock_get(key):
            return store.get(key)

        def mock_delete(key):
            store.pop(key, None)

        r.setex.side_effect = mock_setex
        r.get.side_effect = mock_get
        r.delete.side_effect = mock_delete
        return r, store

    def test_set_and_get_via_redis(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_redis, store = self._make_redis_mock()
        redis_mod = MagicMock()
        redis_mod.from_url.return_value = mock_redis

        with patch.dict(sys.modules, {"redis": redis_mod}):
            import session_store

            session_store._redis = None
            session_store.set_session("U1", {"step": 1})
            result = session_store.get_session("U1")

        assert result == {"step": 1}

    def test_redis_get_missing_returns_none(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_redis, _ = self._make_redis_mock()
        redis_mod = MagicMock()
        redis_mod.from_url.return_value = mock_redis

        with patch.dict(sys.modules, {"redis": redis_mod}):
            import session_store

            session_store._redis = None
            result = session_store.get_session("U_MISSING")

        assert result is None

    def test_redis_failure_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        bad_redis = MagicMock()
        bad_redis.ping.side_effect = Exception("Connection refused")
        redis_mod = MagicMock()
        redis_mod.from_url.return_value = bad_redis

        with patch.dict(sys.modules, {"redis": redis_mod}):
            import session_store

            session_store._redis = None
            session_store.set_session("U1", {"step": 5})
            result = session_store.get_session("U1")

        assert result == {"step": 5}
