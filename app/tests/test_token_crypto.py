"""Tokens are encrypted on the way into the database and read back intact.

The property that matters for a rollout: a read accepts a plain text token
(written before the key was set) as well as an encrypted one, and an install
with no key behaves exactly as it did before.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from src.core import token_crypto
from src.core.token_crypto import PREFIX, decrypt_fields, decrypt_token, encrypt_token


@pytest.fixture
def key(monkeypatch):
    value = Fernet.generate_key().decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", value)
    return value


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)


def test_round_trip_hides_the_token(key):
    stored = encrypt_token("xoxb-secret")
    assert stored.startswith(PREFIX)
    assert "xoxb-secret" not in stored
    assert decrypt_token(stored) == "xoxb-secret"


def test_without_a_key_tokens_are_stored_as_before(no_key):
    assert encrypt_token("xoxb-secret") == "xoxb-secret"
    assert decrypt_token("xoxb-secret") == "xoxb-secret"
    assert token_crypto.enabled() is False


def test_plain_text_written_before_the_key_is_still_readable(key):
    assert decrypt_token("xoxb-legacy") == "xoxb-legacy"


@pytest.mark.parametrize("empty", ["", None])
def test_empty_values_pass_through(key, empty):
    # A purged installation keeps bot_token = '' and must stay that way.
    assert encrypt_token(empty) == empty
    assert decrypt_token(empty) == empty


def test_encrypting_twice_does_not_wrap_twice(key):
    once = encrypt_token("xoxb-secret")
    assert encrypt_token(once) == once


def test_encrypted_token_without_a_key_fails_loudly(key, monkeypatch):
    stored = encrypt_token("xoxb-secret")
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEY is not set"):
        decrypt_token(stored)


def test_wrong_key_fails_loudly_instead_of_returning_ciphertext(key, monkeypatch):
    stored = encrypt_token("xoxb-secret")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match="could not be decrypted"):
        decrypt_token(stored)


def test_malformed_key_is_reported(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "not-a-key")
    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        encrypt_token("xoxb-secret")


def test_decrypt_fields_skips_missing_and_empty_keys(key):
    row = {"bot_token": encrypt_token("xoxb-secret"), "bot_refresh_token": None, "team_id": "T1"}
    assert decrypt_fields(row, "bot_token", "bot_refresh_token", "absent") == {
        "bot_token": "xoxb-secret",
        "bot_refresh_token": None,
        "team_id": "T1",
    }


# ── Database layer ──────────────────────────────────────────────────────────


def _conn(fetchone=None, fetchall=None):
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    ctx = MagicMock()
    ctx.__enter__ = lambda s: conn
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


def test_save_installation_writes_ciphertext(key):
    import src.core.db as db

    ctx, cur = _conn(fetchone=(True,))
    with patch.object(db, "db_conn", return_value=ctx):
        db.save_installation("T1", "Acme", "xoxb-secret", "B1", "A1", bot_refresh_token="xoxe-refresh")
    params = cur.execute.call_args[0][1]
    assert "xoxb-secret" not in params and "xoxe-refresh" not in params
    assert sorted(decrypt_token(p) for p in params if isinstance(p, str) and p.startswith(PREFIX)) == [
        "xoxb-secret",
        "xoxe-refresh",
    ]


@pytest.mark.parametrize(
    "call",
    [
        lambda db: db.get_all_installations(),
        lambda db: db.teams_with_waiting_standups(),
        lambda db: db.get_all_active_schedules(),
        lambda db: db.workspaces_without_standup(24),
        lambda db: db.workspaces_for_activation_nudge("nudge:day2", 24),
        lambda db: [db.get_installation("T1")],
    ],
)
def test_every_query_that_returns_a_bot_token_decrypts_it(key, call):
    import src.core.db as db

    row = {"team_id": "T1", "bot_token": encrypt_token("xoxb-secret")}
    ctx, _ = _conn(fetchone=dict(row), fetchall=[dict(row)])
    with patch.object(db, "db_conn", return_value=ctx):
        assert [r["bot_token"] for r in call(db)] == ["xoxb-secret"]


def test_zoom_link_round_trip(key):
    import src.modules.connect.db as cdb

    ctx, cur = _conn()
    with patch.object(cdb, "db_conn", return_value=ctx):
        cdb.save_zoom_link("T1", "U1", "zoom-access", "zoom-refresh", None)
    _, _, access, refresh, *_ = cur.execute.call_args[0][1]
    assert access.startswith(PREFIX) and refresh.startswith(PREFIX)

    ctx, _ = _conn(fetchone={"access_token": access, "refresh_token": refresh})
    with patch.object(cdb, "db_conn", return_value=ctx):
        link = cdb.zoom_link("T1", "U1")
    assert (link["access_token"], link["refresh_token"]) == ("zoom-access", "zoom-refresh")


# ── Backfill ────────────────────────────────────────────────────────────────


def test_backfill_encrypts_plain_rows_and_keeps_empty_ones(key):
    import src.core.db as db

    ctx, cur = _conn(fetchone=("installations",), fetchall=[("T1", "xoxb-plain", None)])
    with patch.object(db, "db_conn", return_value=ctx):
        changed = token_crypto.encrypt_stored_tokens()

    updates = [c[0] for c in cur.execute.call_args_list if c[0][0].startswith("UPDATE")]
    assert changed == len(updates) == 2  # the same fake row is served for both tables
    sql, (bot_token, refresh, team_id) = updates[0]
    assert sql == "UPDATE installations SET bot_token = %s, bot_refresh_token = %s WHERE team_id = %s"
    assert decrypt_token(bot_token) == "xoxb-plain" and bot_token.startswith(PREFIX)
    assert refresh is None and team_id == "T1"


def test_backfill_refuses_to_run_without_a_key(no_key):
    with pytest.raises(RuntimeError, match="nothing to encrypt with"):
        token_crypto.encrypt_stored_tokens()
