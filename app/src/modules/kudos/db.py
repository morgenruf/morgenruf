"""Kudos persistence, extracted verbatim from core.db.

The function bodies below are unchanged. A test asserts that with an AST
comparison against the previous revision, so the extraction cannot silently
alter behavior.
"""

from __future__ import annotations

import psycopg2.extras

from src.core.db import db_conn


def save_kudos(team_id: str, from_user: str, to_user: str, message: str, channel_id: str = "") -> dict:
    """Save a kudos entry and return it."""
    sql = """
        INSERT INTO kudos (team_id, from_user, to_user, message, channel_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, from_user, to_user, message, channel_id))
            row = cur.fetchone()
    return dict(row)

def get_kudos(team_id: str, limit: int = 50) -> list[dict]:
    """Return recent kudos for a team."""
    sql = """
        SELECT * FROM kudos
        WHERE team_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, limit))
            rows = cur.fetchall()
    return [dict(r) for r in rows]

def get_kudos_leaderboard(team_id: str, days: int = 30) -> list[dict]:
    """Return top kudos receivers for the last N days."""
    sql = """
        SELECT
            to_user,
            COUNT(*) AS received,
            MAX(created_at) AS last_kudos
        FROM kudos
        WHERE team_id = %s
          AND created_at >= NOW() - (%s * INTERVAL '1 day')
        GROUP BY to_user
        ORDER BY received DESC
        LIMIT 20
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, days))
            rows = cur.fetchall()
    return [dict(r) for r in rows]
