"""Two pods migrating at once wait for each other instead of racing.

Every pod runs the migration runner in an init container. Two starting
together both saw a migration as unapplied, and the one that lost the race
failed on the duplicate and crash-looped.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import src.core.migrations_runner as runner
from src.core import db


def test_the_lock_is_taken_before_anything_else(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: str(tmp_path))
    monkeypatch.setattr(runner, "module_migration_dirs", lambda: [])
    cur = MagicMock()
    cur.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    with patch.object(runner.psycopg2, "connect", return_value=conn):
        runner.run_migrations()
    first_sql, first_args = cur.execute.call_args_list[0].args
    assert first_sql == "SELECT pg_advisory_lock(%s)"
    assert first_args == (runner.MIGRATION_LOCK_KEY,)
    conn.close.assert_called_once()


def test_the_key_is_not_shared_with_the_profile_purge():
    assert runner.MIGRATION_LOCK_KEY != db._PROFILE_PURGE_LOCK
