"""Watercooler storage: channels, a workspace's own questions, hidden built-ins, posts.

The built-in questions are in bank.py, not here. The workspace calendar
(working days, holidays) is core's and only read.
"""

from __future__ import annotations

from datetime import date

import psycopg2.extras

from src.core.db import db_conn

DEFAULT_DAYS = "mon,wed,fri"
DEFAULT_POST_TIME = "10:00"
DEFAULT_SOURCE = "both"
DEFAULT_CATEGORIES = "light,work,remote,this_or_that"
MAX_CHANNELS = 20
MAX_QUESTIONS = 500
# Rotation only needs the current cycle; a year of posts is plenty.
POST_RETENTION_DAYS = 365
# How far back rotation looks. Longer than any pool, so a cycle is never cut.
HISTORY_LIMIT = 1000

_CHANNEL_FIELDS = ("days", "post_time", "timezone", "source", "categories", "active", "paused_reason")


def _rows(sql: str, args: tuple) -> list[dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]


def _one(sql: str, args: tuple) -> dict | None:
    rows = _rows(sql, args)
    return rows[0] if rows else None


def _exec(sql: str, args: tuple) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.rowcount


# ── Channels ────────────────────────────────────────────────────────────────


def list_channels(team_id: str) -> list[dict]:
    return _rows("SELECT * FROM watercooler_channels WHERE team_id = %s ORDER BY created_at, channel_id", (team_id,))


def get_channel(team_id: str, channel_id: str) -> dict | None:
    return _one("SELECT * FROM watercooler_channels WHERE team_id = %s AND channel_id = %s", (team_id, channel_id))


def count_channels(team_id: str) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM watercooler_channels WHERE team_id = %s", (team_id,))
            return int(cur.fetchone()[0])


def save_channel(team_id: str, channel_id: str, fields: dict, created_by: str) -> dict:
    """Create or update one channel's schedule. The caller validates."""
    columns = [c for c in _CHANNEL_FIELDS if c in fields]
    names = ", ".join(["team_id", "channel_id", *columns, "created_by"])
    placeholders = ", ".join(["%s"] * (len(columns) + 3))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns) or "channel_id = EXCLUDED.channel_id"
    sql = f"""
        INSERT INTO watercooler_channels ({names}) VALUES ({placeholders})
        ON CONFLICT (team_id, channel_id) DO UPDATE SET {updates}
        RETURNING *
    """
    row = _one(sql, (team_id, channel_id, *[fields[c] for c in columns], created_by))
    return row or {}


def set_channel_active(team_id: str, channel_id: str, active: bool, reason: str | None = None) -> bool:
    return (
        _exec(
            "UPDATE watercooler_channels SET active = %s, paused_reason = %s WHERE team_id = %s AND channel_id = %s",
            (active, None if active else reason, team_id, channel_id),
        )
        > 0
    )


def delete_channel(team_id: str, channel_id: str) -> bool:
    return _exec("DELETE FROM watercooler_channels WHERE team_id = %s AND channel_id = %s", (team_id, channel_id)) > 0


# ── The workspace's own questions ───────────────────────────────────────────


def list_questions(team_id: str, include_archived: bool = True) -> list[dict]:
    where = "" if include_archived else " AND NOT archived"
    return _rows(
        f"SELECT id, text, archived, created_by, created_at FROM watercooler_questions "
        f"WHERE team_id = %s{where} ORDER BY created_at, id",
        (team_id,),
    )


def count_questions(team_id: str) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM watercooler_questions WHERE team_id = %s", (team_id,))
            return int(cur.fetchone()[0])


def add_question(team_id: str, text: str, created_by: str) -> dict:
    return (
        _one(
            "INSERT INTO watercooler_questions (team_id, text, created_by) VALUES (%s, %s, %s) "
            "RETURNING id, text, archived, created_by, created_at",
            (team_id, text, created_by),
        )
        or {}
    )


def update_question(team_id: str, question_id: int, text: str | None = None, archived: bool | None = None):
    sets, args = [], []
    if text is not None:
        sets.append("text = %s")
        args.append(text)
    if archived is not None:
        sets.append("archived = %s")
        args.append(archived)
    if not sets:
        return _one(
            "SELECT id, text, archived, created_by, created_at FROM watercooler_questions WHERE team_id = %s AND id = %s",
            (team_id, question_id),
        )
    return _one(
        f"UPDATE watercooler_questions SET {', '.join(sets)} WHERE team_id = %s AND id = %s "
        "RETURNING id, text, archived, created_by, created_at",
        (*args, team_id, question_id),
    )


def get_question_text(team_id: str, question_id: int) -> str | None:
    row = _one("SELECT text FROM watercooler_questions WHERE team_id = %s AND id = %s", (team_id, question_id))
    return row["text"] if row else None


# ── Hidden built-ins ────────────────────────────────────────────────────────


def hidden_keys(team_id: str) -> set[str]:
    return {
        r["question_key"] for r in _rows("SELECT question_key FROM watercooler_hidden WHERE team_id = %s", (team_id,))
    }


def set_hidden(team_id: str, question_key: str, hidden: bool) -> None:
    if hidden:
        _exec(
            "INSERT INTO watercooler_hidden (team_id, question_key) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (team_id, question_key),
        )
    else:
        _exec("DELETE FROM watercooler_hidden WHERE team_id = %s AND question_key = %s", (team_id, question_key))


# ── Posts ───────────────────────────────────────────────────────────────────


def history(team_id: str, channel_id: str, limit: int = HISTORY_LIMIT) -> list[str]:
    """Question refs this channel posted, newest first."""
    rows = _rows(
        "SELECT question_ref FROM watercooler_posts WHERE team_id = %s AND channel_id = %s "
        "ORDER BY posted_on DESC, created_at DESC LIMIT %s",
        (team_id, channel_id, limit),
    )
    return [r["question_ref"] for r in rows]


def claim_post(team_id: str, channel_id: str, posted_on: date, question_ref: str) -> bool:
    """Reserve today's post for this channel. True only for the caller that inserted the row."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO watercooler_posts (team_id, channel_id, posted_on, question_ref) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (team_id, channel_id, posted_on) DO NOTHING RETURNING 1",
                (team_id, channel_id, posted_on, question_ref),
            )
            return cur.fetchone() is not None


def record_post(team_id: str, channel_id: str, posted_on: date, ts: str) -> None:
    _exec(
        "UPDATE watercooler_posts SET ts = %s WHERE team_id = %s AND channel_id = %s AND posted_on = %s",
        (ts, team_id, channel_id, posted_on),
    )


def release_post(team_id: str, channel_id: str, posted_on: date) -> None:
    """Give a claim back when Slack refused the post. A post Slack accepted is never released."""
    _exec(
        "DELETE FROM watercooler_posts WHERE team_id = %s AND channel_id = %s AND posted_on = %s AND ts IS NULL",
        (team_id, channel_id, posted_on),
    )


def posts_since(team_id: str, since: date) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM watercooler_posts WHERE team_id = %s AND posted_on >= %s AND ts IS NOT NULL",
                (team_id, since),
            )
            return int(cur.fetchone()[0])


def purge_old_posts(team_id: str, days: int = POST_RETENTION_DAYS) -> int:
    return _exec(
        "DELETE FROM watercooler_posts WHERE team_id = %s AND posted_on < CURRENT_DATE - %s::int",
        (team_id, days),
    )


def purge(team_id: str) -> None:
    """Every row this module holds for one workspace."""
    for table in ("watercooler_posts", "watercooler_hidden", "watercooler_questions", "watercooler_channels"):
        _exec(f"DELETE FROM {table} WHERE team_id = %s", (team_id,))
