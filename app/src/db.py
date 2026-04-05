"""Database module — PostgreSQL connection pool and query helpers."""

from __future__ import annotations

import json
import logging
import os
import re
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
    allowed = {"channel_id", "schedule_time", "schedule_tz", "schedule_days", "questions", "active", "reminder_minutes", "edit_window_hours", "jira_base_url", "github_repo", "linear_team"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    for col in fields:
        if not re.match(r'^[a-z_]+$', col):
            raise ValueError(f"Invalid column name: {col}")

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
    tz: str | None = None,
) -> None:
    """Insert or update a member record. Only non-None values overwrite existing ones."""
    sql = """
        INSERT INTO members (team_id, user_id, real_name, email, tz)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (team_id, user_id) DO UPDATE SET
            real_name = COALESCE(EXCLUDED.real_name, members.real_name),
            email = COALESCE(EXCLUDED.email, members.email),
            tz = COALESCE(EXCLUDED.tz, members.tz),
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
    mood: str | None = None,
) -> None:
    """Persist a completed standup."""
    has_blockers = blockers.strip().lower() not in ("none", "no", "nope", "-", "n/a", "")
    sql = """
        INSERT INTO standups (team_id, user_id, yesterday, today, blockers, has_blockers, mood)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, yesterday, today, blockers, has_blockers, mood))
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


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

def get_dashboard_stats(team_id: str) -> dict:
    """Return completion rate, active member count, and response counts."""
    sql_responses = """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT user_id) AS active_members
        FROM standups
        WHERE team_id = %s
          AND standup_date >= CURRENT_DATE - INTERVAL '7 days'
    """
    sql_total_members = "SELECT COUNT(*) AS cnt FROM members WHERE team_id = %s AND active = TRUE"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql_responses, (team_id,))
            row = dict(cur.fetchone())
            cur.execute(sql_total_members, (team_id,))
            members_row = dict(cur.fetchone())
    total_members = members_row.get("cnt", 0) or 0
    responses_week = row.get("total", 0) or 0
    active_members = row.get("active_members", 0) or 0
    # Completion rate: responses this week / (members * working days this week)
    completion_rate = 0
    if total_members > 0 and responses_week > 0:
        completion_rate = min(100, int(responses_week / max(total_members, 1) * 100 / 5))
    return {
        "completion_rate": completion_rate,
        "active_members": active_members,
        "total_responses": responses_week,
        "responses_this_week": responses_week,
        "total_members": total_members,
    }



# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

def get_webhooks(team_id: str) -> list[dict]:
    """Return all webhooks registered for a team."""
    sql = "SELECT * FROM webhooks WHERE team_id = %s ORDER BY created_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def add_webhook(
    team_id: str,
    url: str,
    secret: str | None = None,
    events: list[str] | None = None,
) -> dict:
    """Insert a new webhook and return the created row."""
    if events is None:
        events = ["standup.completed"]
    sql = """
        INSERT INTO webhooks (team_id, webhook_url, secret, events)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, url, secret, events))
            row = cur.fetchone()
    logger.info("Added webhook %s for team %s", url, team_id)
    return dict(row)


def delete_webhook(team_id: str, webhook_id: int) -> bool:
    """Delete a webhook by id (scoped to team_id for safety). Returns True if deleted."""
    sql = "DELETE FROM webhooks WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (webhook_id, team_id))
            deleted = cur.rowcount > 0
    return deleted


# ---------------------------------------------------------------------------
# Standup lookup
# ---------------------------------------------------------------------------

def get_standup_by_id(standup_id: int) -> dict | None:
    """Return a single standup row by primary key, or None."""
    sql = "SELECT * FROM standups WHERE id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (standup_id,))
            row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Skip today
# ---------------------------------------------------------------------------

def skip_today(team_id: str, user_id: str) -> None:
    """Mark user as skipping today's standup."""
    sql = """
        INSERT INTO user_skip (team_id, user_id, skip_date)
        VALUES (%s, %s, CURRENT_DATE)
        ON CONFLICT DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))


def is_skipped_today(team_id: str, user_id: str) -> bool:
    """Return True if user has skipped today."""
    sql = "SELECT 1 FROM user_skip WHERE team_id=%s AND user_id=%s AND skip_date=CURRENT_DATE"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_participation_stats(team_id: str, days: int = 7) -> list[dict]:
    """Return per-member participation stats for the last N days."""
    sql = """
        SELECT
            m.user_id,
            m.real_name,
            COUNT(s.id) AS responses,
            MAX(s.submitted_at) AS last_standup,
            COUNT(CASE WHEN s.has_blockers THEN 1 END) AS days_with_blockers
        FROM members m
        LEFT JOIN standups s ON s.team_id = m.team_id
            AND s.user_id = m.user_id
            AND s.standup_date >= CURRENT_DATE - (%s - 1) * INTERVAL '1 day'
        WHERE m.team_id = %s AND m.active = TRUE
        GROUP BY m.user_id, m.real_name
        ORDER BY responses DESC, m.real_name
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (days, team_id))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_standups(team_id: str, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
    """Return standup rows for export, optionally filtered by date range."""
    conditions = ["team_id = %s"]
    params: list = [team_id]
    if from_date:
        conditions.append("standup_date >= %s")
        params.append(from_date)
    if to_date:
        conditions.append("standup_date <= %s")
        params.append(to_date)
    sql = f"SELECT * FROM standups WHERE {' AND '.join(conditions)} ORDER BY standup_date, submitted_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Member email lookup
# ---------------------------------------------------------------------------

def get_member_email(team_id: str, user_id: str) -> str | None:
    """Return email for a member, or None."""
    sql = "SELECT email FROM members WHERE team_id=%s AND user_id=%s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Standup schedules
# ---------------------------------------------------------------------------

def get_standup_schedules(team_id: str) -> list[dict]:
    """Return all active standup schedules for a workspace."""
    sql = "SELECT * FROM standup_schedules WHERE team_id = %s ORDER BY created_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def create_standup_schedule(team_id: str, **kwargs) -> dict:
    """Insert a new standup schedule row and return it."""
    allowed = {"name", "channel_id", "schedule_time", "schedule_tz", "schedule_days", "questions", "participants", "reminder_minutes", "active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if "questions" in fields and isinstance(fields["questions"], list):
        fields["questions"] = json.dumps(fields["questions"])
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["%s"] * len(fields))
    sql = f"""
        INSERT INTO standup_schedules (team_id, {cols}, updated_at)
        VALUES (%s, {placeholders}, NOW())
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, [team_id] + list(fields.values()))
            row = cur.fetchone()
    return dict(row)


def update_standup_schedule(team_id: str, schedule_id: int, **kwargs) -> dict | None:
    """Update a standup schedule by id (scoped to team_id)."""
    allowed = {"name", "channel_id", "schedule_time", "schedule_tz", "schedule_days", "questions", "participants", "reminder_minutes", "active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_standup_schedule(team_id, schedule_id)
    if "questions" in fields and isinstance(fields["questions"], list):
        fields["questions"] = json.dumps(fields["questions"])
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    sql = f"UPDATE standup_schedules SET {set_clause} WHERE id = %s AND team_id = %s RETURNING *"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, list(fields.values()) + [schedule_id, team_id])
            row = cur.fetchone()
    return dict(row) if row else None


def delete_standup_schedule(team_id: str, schedule_id: int) -> bool:
    """Soft-delete by setting active=false (scoped to team_id)."""
    sql = "UPDATE standup_schedules SET active = FALSE WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (schedule_id, team_id))
            return cur.rowcount > 0


def get_standup_schedule(team_id: str, schedule_id: int) -> dict | None:
    """Return a single standup schedule by id (scoped to team_id)."""
    sql = "SELECT * FROM standup_schedules WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, team_id))
            row = cur.fetchone()
    return dict(row) if row else None


def get_all_active_schedules() -> list[dict]:
    """Return all active schedules across all workspaces (for scheduler bootstrap)."""
    sql = """
        SELECT s.*, i.bot_token
        FROM standup_schedules s
        JOIN installations i ON i.team_id = s.team_id
        WHERE s.active = TRUE
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Kudos
# ---------------------------------------------------------------------------

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
