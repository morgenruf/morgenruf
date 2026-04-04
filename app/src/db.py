"""Database module — PostgreSQL connection pool and query helpers."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

_pool = None

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool

    _DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if _DATABASE_URL:
        _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=_DATABASE_URL)
        logger.info("PostgreSQL connection pool initialised")
    else:
        logger.warning("DATABASE_URL not set — database features disabled")
except ImportError:
    logger.warning("psycopg2 not installed — database features disabled")
except Exception as exc:  # noqa: BLE001
    logger.warning("Could not initialise DB pool: %s", exc)


def get_conn():
    """Borrow a connection from the pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised")
    return _pool.getconn()


def release_conn(conn) -> None:
    """Return a connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)


@contextmanager
def db_conn() -> Generator[Any, None, None]:
    """Context manager that borrows and auto-returns a DB connection."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# ---------------------------------------------------------------------------
# Installations
# ---------------------------------------------------------------------------

def save_installation(
    team_id: str,
    team_name: str,
    bot_token: str,
    bot_user_id: str,
    app_id: str,
    installed_by_user_id: str | None = None,
) -> None:
    """Insert or update an OAuth installation record."""
    sql = """
        INSERT INTO installations (team_id, team_name, bot_token, bot_user_id, app_id, installed_by_user_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (team_id) DO UPDATE SET
            team_name = EXCLUDED.team_name,
            bot_token = EXCLUDED.bot_token,
            bot_user_id = EXCLUDED.bot_user_id,
            app_id = EXCLUDED.app_id,
            installed_by_user_id = EXCLUDED.installed_by_user_id,
            updated_at = NOW()
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, team_name, bot_token, bot_user_id, app_id, installed_by_user_id))
    logger.info("Saved installation for team %s (%s)", team_id, team_name)


def get_installation(team_id: str) -> dict | None:
    """Return installation row as a dict, or None."""
    sql = "SELECT * FROM installations WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def get_all_installations() -> list[dict]:
    """Return all installation rows."""
    sql = "SELECT * FROM installations ORDER BY installed_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Workspace config
# ---------------------------------------------------------------------------

def upsert_workspace_config(team_id: str, **kwargs: Any) -> None:
    """Insert or update workspace config. Pass only columns you want to set."""
    allowed = {"channel_id", "schedule_time", "schedule_tz", "schedule_days", "questions", "active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}

    if not fields:
        # Insert with defaults only
        sql = """
            INSERT INTO workspace_config (team_id) VALUES (%s)
            ON CONFLICT DO NOTHING
        """
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (team_id,))
        return

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    set_clause += ", updated_at = NOW()"
    values = list(fields.values())

    # Serialise questions list to JSON if needed
    if "questions" in fields and isinstance(fields["questions"], list):
        idx = list(fields.keys()).index("questions")
        values[idx] = json.dumps(fields["questions"])

    sql = f"""
        INSERT INTO workspace_config (team_id, {", ".join(fields.keys())}, updated_at)
        VALUES (%s, {", ".join(["%s"] * len(fields))}, NOW())
        ON CONFLICT (team_id) DO UPDATE SET {set_clause}
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [team_id] + values + values)


def get_workspace_config(team_id: str) -> dict | None:
    """Return workspace config row, or None."""
    sql = "SELECT * FROM workspace_config WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

def get_active_members(team_id: str) -> list[dict]:
    """Return active members for a workspace."""
    sql = "SELECT * FROM members WHERE team_id = %s AND active = TRUE ORDER BY real_name"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def upsert_member(
    team_id: str,
    user_id: str,
    real_name: str | None = None,
    email: str | None = None,
    tz: str = "UTC",
) -> None:
    """Insert or update a member record."""
    sql = """
        INSERT INTO members (team_id, user_id, real_name, email, tz)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (team_id, user_id) DO UPDATE SET
            real_name = EXCLUDED.real_name,
            email = EXCLUDED.email,
            tz = EXCLUDED.tz,
            active = TRUE
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, real_name, email, tz))


# ---------------------------------------------------------------------------
# Standups
# ---------------------------------------------------------------------------

def save_standup(
    team_id: str,
    user_id: str,
    yesterday: str,
    today: str,
    blockers: str,
) -> None:
    """Persist a completed standup."""
    has_blockers = blockers.strip().lower() not in ("none", "no", "nope", "-", "n/a", "")
    sql = """
        INSERT INTO standups (team_id, user_id, yesterday, today, blockers, has_blockers)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, yesterday, today, blockers, has_blockers))
    logger.info("Saved standup for %s / %s", team_id, user_id)


def get_today_standups(team_id: str) -> list[dict]:
    """Return all standup submissions for today."""
    sql = """
        SELECT * FROM standups
        WHERE team_id = %s AND standup_date = CURRENT_DATE
        ORDER BY submitted_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]
