"""Encrypt OAuth tokens before they are written to the database.

Slack bot tokens and Zoom tokens used to sit in Postgres as plain text, so a
leaked dump or backup was enough to act as every installed workspace. With
TOKEN_ENCRYPTION_KEY set they are stored as Fernet ciphertext (AES in CBC mode
with an HMAC), and a dump is useless without the key.

Without the key nothing changes: values are written and read as plain text,
so an existing self-hosted install keeps working until its operator opts in.

Reads accept both forms. A value without the prefix is a token written before
the key was set, and is returned as it is. That is what lets the key be turned
on first and the old rows be encrypted afterwards, with no downtime between.

Losing the key loses every stored token: each workspace would have to
reinstall. Keep it wherever the database password is kept.
"""

from __future__ import annotations

import functools
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
KEY_ENV = "TOKEN_ENCRYPTION_KEY"
_KEY_HINT = (
    'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
)


@functools.lru_cache(maxsize=4)
def _fernet_for(key: str) -> Fernet:
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"{KEY_ENV} is not a valid Fernet key. {_KEY_HINT}") from exc


def _fernet() -> Fernet | None:
    key = (os.environ.get("TOKEN_ENCRYPTION_KEY") or "").strip()
    return _fernet_for(key) if key else None


def enabled() -> bool:
    """True when a usable key is configured. Raises if the key is malformed."""
    return _fernet() is not None


def encrypt_token(value: str | None) -> str | None:
    """Ciphertext for a token, or the value untouched when there is no key.

    Empty and None pass through: a purged installation keeps bot_token = ''
    and queries rely on that. An already encrypted value is not wrapped twice.
    """
    if not value or value.startswith(PREFIX):
        return value
    fernet = _fernet()
    if fernet is None:
        return value
    return PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt_token(value: str | None) -> str | None:
    """The token as Slack or Zoom issued it. Plain text values pass through."""
    if not value or not value.startswith(PREFIX):
        return value
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError(f"A stored token is encrypted but {KEY_ENV} is not set, so it cannot be read.")
    try:
        return fernet.decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError(
            f"A stored token could not be decrypted. {KEY_ENV} is not the key it was written with."
        ) from exc


def decrypt_fields(row: dict, *fields: str) -> dict:
    """Decrypt the named keys of a row in place, skipping any it does not have."""
    for field in fields:
        if row.get(field):
            row[field] = decrypt_token(row[field])
    return row


# (table, primary key columns, token columns)
_TOKEN_COLUMNS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("installations", ("team_id",), ("bot_token", "bot_refresh_token")),
    ("connect_zoom_links", ("team_id", "user_id"), ("access_token", "refresh_token")),
)


def encrypt_stored_tokens() -> int:
    """Encrypt every token still stored as plain text. Returns rows changed.

    Run once after TOKEN_ENCRYPTION_KEY is set on every running pod. Safe to
    run again: rows already encrypted are skipped. Each table is one
    transaction with its rows locked, so a token refresh landing at the same
    moment waits instead of being overwritten with the old token.
    """
    if not enabled():
        raise RuntimeError(f"{KEY_ENV} is not set, so there is nothing to encrypt with. {_KEY_HINT}")

    from src.core.db import db_conn  # noqa: PLC0415

    changed = 0
    for table, keys, columns in _TOKEN_COLUMNS:
        pending = " OR ".join(f"({c} IS NOT NULL AND {c} <> '' AND {c} NOT LIKE %s)" for c in columns)
        select = f"SELECT {', '.join(keys + columns)} FROM {table} WHERE {pending} FOR UPDATE"  # noqa: S608
        update = (
            f"UPDATE {table} SET {', '.join(f'{c} = %s' for c in columns)} "  # noqa: S608
            f"WHERE {' AND '.join(f'{k} = %s' for k in keys)}"
        )
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s)", (table,))
                if not (cur.fetchone() or [None])[0]:
                    continue
                cur.execute(select, tuple(PREFIX + "%" for _ in columns))
                for row in cur.fetchall():
                    key_values, tokens = row[: len(keys)], row[len(keys) :]
                    cur.execute(update, tuple(encrypt_token(t) for t in tokens) + tuple(key_values))
                    changed += 1
    return changed
