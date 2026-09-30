"""Two people finishing a standup together must end up in one daily thread.

Both saw no stored thread, both posted a header, and ON CONFLICT DO NOTHING
kept only the first. The loser cached its own orphan ts in memory, so its
answers and every later one on that worker went under a header nobody else
used, and the channel showed two headers.
"""

from unittest.mock import MagicMock

import pytest
import src.modules.standup.handlers as handlers


@pytest.fixture(autouse=True)
def _empty_cache():
    handlers._daily_thread_cache.clear()
    yield
    handlers._daily_thread_cache.clear()


def _client(ts="111.1"):
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": ts}
    return client


def _parent(client, db):
    return handlers._daily_thread_parent(client, db, "T1", "C1", "2026-09-29", 7, header_text="header")


class TestDailyThreadParent:
    def test_first_one_posts_and_keeps_its_header(self):
        client, db = _client("111.1"), MagicMock()
        db.get_daily_thread_ts.return_value = None
        db.upsert_daily_thread.return_value = "111.1"
        assert _parent(client, db) == "111.1"
        client.chat_delete.assert_not_called()
        assert handlers._daily_thread_cache["T1:C1:2026-09-29:7"] == "111.1"

    def test_the_loser_adopts_the_stored_thread_and_deletes_its_header(self):
        client, db = _client("222.2"), MagicMock()
        db.get_daily_thread_ts.return_value = None
        db.upsert_daily_thread.return_value = "111.1"  # someone else won
        assert _parent(client, db) == "111.1"
        client.chat_delete.assert_called_once_with(channel="C1", ts="222.2")
        assert handlers._daily_thread_cache["T1:C1:2026-09-29:7"] == "111.1"

    def test_a_failed_write_is_used_once_but_not_cached(self):
        client, db = _client("333.3"), MagicMock()
        db.get_daily_thread_ts.return_value = None
        db.upsert_daily_thread.return_value = None
        assert _parent(client, db) == "333.3"
        assert "T1:C1:2026-09-29:7" not in handlers._daily_thread_cache
        client.chat_delete.assert_not_called()

    def test_an_existing_thread_is_reused_without_posting(self):
        client, db = _client(), MagicMock()
        db.get_daily_thread_ts.return_value = "999.9"
        assert _parent(client, db) == "999.9"
        client.chat_postMessage.assert_not_called()

    def test_a_failed_delete_still_adopts_the_winner(self):
        client, db = _client("222.2"), MagicMock()
        client.chat_delete.side_effect = Exception("message_not_found")
        db.get_daily_thread_ts.return_value = None
        db.upsert_daily_thread.return_value = "111.1"
        assert _parent(client, db) == "111.1"


def test_upsert_returns_the_stored_ts():
    """The SQL must hand back the existing row's ts on conflict, not nothing."""
    from contextlib import contextmanager
    from unittest.mock import patch

    import src.core.db as db

    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = ("111.1",)
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def fake_conn():
        yield conn

    with patch.object(db, "db_conn", fake_conn):
        assert db.upsert_daily_thread("T1", "C1", "2026-09-29", "222.2", 7) == "111.1"
    sql = cur.execute.call_args.args[0]
    assert "RETURNING parent_ts" in sql
    assert "DO NOTHING" not in sql
