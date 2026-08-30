"""Database module — PostgreSQL connection pool and query helpers."""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Generator
from zoneinfo import ZoneInfo

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
    bot_refresh_token: str | None = None,
    bot_token_expires_at: str | None = None,
) -> bool:
    """Insert or update an OAuth installation record. Returns True if this is a new installation."""
    sql = """
        INSERT INTO installations (team_id, team_name, bot_token, bot_user_id, app_id,
            installed_by_user_id, bot_refresh_token, bot_token_expires_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (team_id) DO UPDATE SET
            team_name = EXCLUDED.team_name,
            bot_token = EXCLUDED.bot_token,
            bot_user_id = EXCLUDED.bot_user_id,
            app_id = EXCLUDED.app_id,
            installed_by_user_id = EXCLUDED.installed_by_user_id,
            bot_refresh_token = EXCLUDED.bot_refresh_token,
            bot_token_expires_at = EXCLUDED.bot_token_expires_at,
            updated_at = NOW()
        RETURNING (xmax = 0) AS is_new
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    team_id,
                    team_name,
                    bot_token,
                    bot_user_id,
                    app_id,
                    installed_by_user_id,
                    bot_refresh_token,
                    bot_token_expires_at,
                ),
            )
            row = cur.fetchone()
            is_new = bool(row[0]) if row else False
    logger.info("Saved installation for team %s (%s) (new=%s)", team_id, team_name, is_new)
    return is_new


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
    allowed = {
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "active",
        "reminder_minutes",
        "edit_window_hours",
        "jira_base_url",
        "github_repo",
        "linear_team",
        "ai_summary_enabled",
        "ai_provider",
        "feed_token",
        "feed_public",
        "manager_email",
        "manager_digest_enabled",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    for col in fields:
        if not re.match(r"^[a-z_]+$", col):
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


def get_workspace_by_feed_token(token: str) -> dict | None:
    """Return workspace_config row matching feed_token, or None."""
    sql = "SELECT * FROM workspace_config WHERE feed_token = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (token,))
            row = cur.fetchone()
    return dict(row) if row else None


def get_standups(
    team_id: str,
    days: int = 1,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Return standup submissions.

    If *from_date* / *to_date* (YYYY-MM-DD strings) are provided they take
    priority over *days*.  Otherwise the last *days* days are returned.
    """
    if from_date or to_date:
        conditions = ["s.team_id = %s"]
        params: list = [team_id]
        if from_date:
            conditions.append("s.standup_date >= %s")
            params.append(from_date)
        if to_date:
            conditions.append("s.standup_date <= %s")
            params.append(to_date)
        where = " AND ".join(conditions)
        sql = f"""
            SELECT s.*, m.real_name AS user_name
            FROM standups s
            LEFT JOIN members m ON m.team_id = s.team_id AND m.user_id = s.user_id
            WHERE {where}
            ORDER BY s.standup_date DESC, s.submitted_at
        """
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    sql = """
        SELECT s.*, m.real_name AS user_name
        FROM standups s
        LEFT JOIN members m ON m.team_id = s.team_id AND m.user_id = s.user_id
        WHERE s.team_id = %s
          AND s.standup_date >= CURRENT_DATE - ((%s - 1) * INTERVAL '1 day')
        ORDER BY s.standup_date DESC, s.submitted_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, days))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def get_all_members(team_id: str) -> list[dict]:
    """Every member row for a team, active or not."""
    sql = "SELECT * FROM members WHERE team_id = %s ORDER BY real_name NULLS LAST, user_id"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def set_members_active(team_id: str, user_ids: list[str], active: bool) -> int:
    """Flip the active flag for a set of members. Returns the number changed.

    Rows are never deleted. A person who left keeps their standup history, and
    reactivating them if they return is a single flag.
    """
    if not user_ids:
        return 0
    sql = "UPDATE members SET active = %s WHERE team_id = %s AND user_id = ANY(%s) AND active <> %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (active, team_id, list(user_ids), active))
            return cur.rowcount or 0


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
) -> int | None:
    """Persist a completed standup. Returns the new standup ID."""
    has_blockers = blockers.strip().lower() not in ("none", "no", "nope", "-", "n/a", "")
    sql = """
        INSERT INTO standups (team_id, user_id, yesterday, today, blockers, has_blockers, mood)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, yesterday, today, blockers, has_blockers, mood))
            row = cur.fetchone()
    standup_id = row[0] if row else None
    logger.info("Saved standup %s for %s / %s", standup_id, team_id, user_id)
    return standup_id


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
    """Return this week's completion rate plus the counts the rate is built from.

    The rate comes from `get_participation_overview`, so the denominator is the
    set of (member, schedule, occurrence date) triples the workspace actually
    asked for rather than a headcount times a hardcoded five day week. The
    enrolment counts travel with it so the UI can say "of N enrolled members"
    instead of showing a bare percentage.
    """
    overview = get_participation_overview(team_id, days=7)
    return {
        "completion_rate": overview["completion_rate"],
        "active_members": overview["responding_members"],
        "total_responses": overview["responses"],
        "responses_this_week": overview["responses"],
        "total_members": overview["total_members"],
        "enrolled_members": overview["enrolled_members"],
        "unenrolled_members": overview["unenrolled_members"],
        "on_vacation_members": overview["on_vacation_members"],
        "expected_responses": overview["expected"],
        "completed_responses": overview["completed"],
        "missed_responses": overview["missed"],
        "days": overview["days"],
        "schedules": overview["schedules"],
    }


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

# Canonical outbound webhook event names.
#
# Naming convention: dotted "<noun>.<past tense verb>", the convention the
# webhooks table has shipped with since migration 003. The workflow_rules
# table uses underscore trigger names ("standup_complete") for a different
# concept (automation rule triggers), so the two vocabularies are mapped
# rather than merged. Underscore spellings are accepted on input and
# normalised to the dotted form; migration 023 rewrites any rows that were
# stored with the underscore spelling.
WEBHOOK_EVENTS = (
    "standup.completed",
    "blocker.detected",
    "participation.low",
)

DEFAULT_WEBHOOK_EVENTS = ["standup.completed"]

# Legacy / workflow_rules spellings accepted on input.
WEBHOOK_EVENT_ALIASES = {
    "standup_complete": "standup.completed",
    "standup_completed": "standup.completed",
    "blocker_detected": "blocker.detected",
    "low_participation": "participation.low",
}

# Keep the most recent N delivery log rows per webhook.
WEBHOOK_DELIVERY_RETENTION = 50


def normalize_webhook_event(event: str) -> str:
    """Map a legacy or underscore event spelling onto its canonical name."""
    name = (event or "").strip()
    return WEBHOOK_EVENT_ALIASES.get(name, name)


def normalize_webhook_events(events: list[str] | None) -> list[str]:
    """Normalise and de-duplicate a list of event names, keeping order.

    Unknown names are dropped. An empty or missing list falls back to the
    default event set so a webhook is never registered with no events.
    """
    if not events:
        return list(DEFAULT_WEBHOOK_EVENTS)
    out: list[str] = []
    for raw in events:
        name = normalize_webhook_event(str(raw))
        if name in WEBHOOK_EVENTS and name not in out:
            out.append(name)
    return out or list(DEFAULT_WEBHOOK_EVENTS)


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
    events = normalize_webhook_events(events)
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


def get_webhook(team_id: str, webhook_id: int) -> dict | None:
    """Return a single webhook row scoped to team_id, or None."""
    sql = "SELECT * FROM webhooks WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (webhook_id, team_id))
            row = cur.fetchone()
    return dict(row) if row else None


def update_webhook(
    team_id: str,
    webhook_id: int,
    url: str | None = None,
    events: list[str] | None = None,
) -> dict | None:
    """Update a webhook's URL and/or event subscription. Returns the new row, or None.

    The secret is never touched here. Use ``rotate_webhook_secret`` for that.
    """
    sets: list[str] = []
    params: list[Any] = []
    if url is not None:
        sets.append("webhook_url = %s")
        params.append(url)
    if events is not None:
        sets.append("events = %s")
        params.append(normalize_webhook_events(events))
    if not sets:
        return get_webhook(team_id, webhook_id)

    params.extend([webhook_id, team_id])
    sql = f"UPDATE webhooks SET {', '.join(sets)} WHERE id = %s AND team_id = %s RETURNING *"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
    return dict(row) if row else None


def rotate_webhook_secret(team_id: str, webhook_id: int, secret: str) -> dict | None:
    """Store a new signing secret for a webhook. Returns the updated row, or None.

    The caller generates the secret so it can hand it back to the operator
    exactly once. The value is never logged here.
    """
    sql = "UPDATE webhooks SET secret = %s WHERE id = %s AND team_id = %s RETURNING *"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (secret, webhook_id, team_id))
            row = cur.fetchone()
    if row:
        logger.info("Rotated signing secret for webhook %s (team %s)", webhook_id, team_id)
    return dict(row) if row else None


def delete_webhook(team_id: str, webhook_id: int) -> bool:
    """Delete a webhook by id (scoped to team_id for safety). Returns True if deleted."""
    sql = "DELETE FROM webhooks WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (webhook_id, team_id))
            deleted = cur.rowcount > 0
    return deleted


def record_webhook_delivery(
    team_id: str,
    webhook_id: int,
    event_type: str,
    status_code: int | None = None,
    ok: bool = False,
    signed: bool = False,
    error: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Append one delivery attempt to the log and prune old rows for that webhook.

    ``status_code`` is NULL when the request never produced a response (DNS
    failure, connection refused, timeout); ``error`` then holds a short reason.
    Only the most recent ``WEBHOOK_DELIVERY_RETENTION`` rows per webhook are
    kept so the table cannot grow without bound.
    """
    insert_sql = """
        INSERT INTO webhook_deliveries
            (webhook_id, team_id, event_type, status_code, ok, signed, error, duration_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    prune_sql = """
        DELETE FROM webhook_deliveries
        WHERE webhook_id = %s
          AND id NOT IN (
              SELECT id FROM webhook_deliveries
              WHERE webhook_id = %s
              ORDER BY id DESC
              LIMIT %s
          )
    """
    short_error = (error or "")[:500] or None
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                insert_sql,
                (
                    webhook_id,
                    team_id,
                    event_type,
                    status_code,
                    bool(ok),
                    bool(signed),
                    short_error,
                    duration_ms,
                ),
            )
            cur.execute(prune_sql, (webhook_id, webhook_id, WEBHOOK_DELIVERY_RETENTION))


def get_webhook_deliveries(team_id: str, webhook_id: int | None = None, limit: int = 20) -> list[dict]:
    """Return recent delivery attempts for a team, newest first.

    Pass ``webhook_id`` to narrow the log to a single webhook.
    """
    limit = max(1, min(int(limit), 200))
    params: list[Any] = [team_id]
    where = "team_id = %s"
    if webhook_id is not None:
        where += " AND webhook_id = %s"
        params.append(int(webhook_id))
    params.append(limit)
    sql = f"""
        SELECT id, webhook_id, event_type, status_code, ok, signed, error, duration_ms, created_at
        FROM webhook_deliveries
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


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


def set_vacation(team_id: str, user_id: str, on_vacation: bool) -> None:
    """Mark a member as on vacation (or back from vacation)."""
    sql = """
        INSERT INTO members (team_id, user_id, on_vacation)
        VALUES (%s, %s, %s)
        ON CONFLICT (team_id, user_id) DO UPDATE SET on_vacation = EXCLUDED.on_vacation
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, on_vacation))


def is_on_vacation(team_id: str, user_id: str) -> bool:
    """Return True if this member is currently marked as on vacation."""
    sql = "SELECT on_vacation FROM members WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return bool(row[0]) if row else False


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def get_standup_streak(team_id: str, user_id: str) -> int:
    """Return the current consecutive standup streak (number of working days in a row).

    Counts backwards from today (or the most recent standup date) through
    consecutive weekdays where the user submitted a standup.
    """
    sql = """
        WITH dates AS (
            SELECT DISTINCT standup_date
            FROM standups
            WHERE team_id = %s AND user_id = %s
            ORDER BY standup_date DESC
        ),
        numbered AS (
            SELECT standup_date,
                   standup_date - (ROW_NUMBER() OVER (ORDER BY standup_date DESC))::int AS grp
            FROM dates
        )
        SELECT COUNT(*) AS streak
        FROM numbered
        WHERE grp = (SELECT grp FROM numbered LIMIT 1)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return int(row[0]) if row and row[0] else 0


def get_user_last_standup_answers(team_id: str, user_id: str) -> dict | None:
    """Return the most recent standup answers for prefilling the form."""
    sql = """
        SELECT yesterday, today, blockers
        FROM standups
        WHERE team_id = %s AND user_id = %s
        ORDER BY submitted_at DESC
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return dict(row) if row else None


# Participation model (issue #74). See compute_participation for the model.

DEFAULT_SCHEDULE_DAYS = "mon,tue,wed,thu,fri"

_WEEKDAY_TOKENS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "weds": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
}

_WORKING_WEEK = {0, 1, 2, 3, 4}


def _utc_now() -> datetime:
    """Current UTC time. A seam so the participation model can be tested at a fixed clock."""
    return datetime.now(timezone.utc)


def _resolve_zone(name: object):
    """Return a tzinfo for an IANA timezone name, falling back to UTC."""
    if isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except Exception:  # noqa: BLE001 - unknown name or missing tz database
            logger.debug("Unknown schedule timezone %r, treating it as UTC", name)
    return timezone.utc


def parse_schedule_days(spec: object) -> set[int]:
    """Return the weekday numbers a `schedule_days` value fires on (Monday is 0).

    Accepts the shapes APScheduler's `day_of_week` accepts and this app writes:
    "mon,wed,fri", "mon-fri", "fri-mon", "*" and bare numbers.
    """
    if not isinstance(spec, str) or not spec.strip():
        spec = DEFAULT_SCHEDULE_DAYS
    days: set[int] = set()
    for token in spec.lower().replace(" ", "").split(","):
        if not token:
            continue
        if token == "*":
            return set(range(7))
        if "-" in token[1:]:
            start_txt, _, end_txt = token.partition("-")
            start = _WEEKDAY_TOKENS.get(start_txt)
            end = _WEEKDAY_TOKENS.get(end_txt)
            if start is None or end is None:
                continue
            day = start
            days.add(day)
            while day != end:
                day = (day + 1) % 7
                days.add(day)
            continue
        day = _WEEKDAY_TOKENS.get(token)
        if day is not None:
            days.add(day)
    return days or set(_WORKING_WEEK)


def _schedule_minutes(schedule: dict) -> int:
    """Return a schedule's fire time as minutes past local midnight, for ordering."""
    match = re.match(r"^\s*(\d{1,2}):(\d{2})", str(schedule.get("schedule_time") or "09:00"))
    if not match:
        return 0
    return int(match.group(1)) * 60 + int(match.group(2))


def _as_date(value: object) -> date | None:
    """Coerce a psycopg2 date, a datetime or an ISO string to a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _percentage(part: int, whole: int) -> int:
    """Return part of whole as a whole percentage, rounded half up, 0 when nothing was expected."""
    if whole <= 0:
        return 0
    return int(part * 100 / whole + 0.5)


def _occurrence_dates(schedule: dict, days: int, now: datetime) -> list[date]:
    """Return the dates a schedule fired on in the last N days, in its own timezone."""
    local_today = now.astimezone(_resolve_zone(schedule.get("schedule_tz"))).date()
    weekdays = parse_schedule_days(schedule.get("schedule_days"))
    window = [local_today - timedelta(days=offset) for offset in range(days)]
    return sorted(day for day in window if day.weekday() in weekdays)


def compute_participation(
    schedules: list[dict] | None,
    members: list[dict] | None,
    submissions: list[dict] | None,
    days: int = 7,
    now: datetime | None = None,
) -> dict:
    """Compute workspace, per-schedule and per-member participation from raw rows.

    The unit of "expected" is a (member, schedule, occurrence date) triple, not
    a member. Counting members was wrong in three independent ways on a
    workspace that runs several schedules:

      * people who are in no schedule can never respond, yet sat in the
        denominator;
      * someone in a morning and an evening standup adds one to a headcount but
        several submissions to the numerator;
      * a hardcoded five day week caps a three-day-a-week standup at 60 percent.

    Expanding each schedule's own `schedule_days` across the window in its own
    `schedule_tz`, crossed with its own `participants`, fixes all three and
    makes the per-schedule rates fall out of the same pass.

    One limitation is worth naming: the `standups` table has no schedule id, so
    a submission cannot be attributed to a schedule by identity. Submissions are
    matched to occurrences per (member, day) by count, and where a member has
    several occurrences on one day the matches are handed out in schedule_time
    order. That keeps the per-schedule numbers summing exactly to the workspace
    numerator, at the cost of guessing which of a member's two standups they
    skipped when they filed only one.

    Kept free of any database access so the arithmetic can be tested against
    hand-computed numbers. `schedules` are `standup_schedules` rows, `members`
    are `members` rows and `submissions` are `standups` rows covering at least
    the window (a day of slack either side is fine, it is filtered here).
    """
    days = max(1, int(days or 1))
    now = now or _utc_now()

    known: dict[str, dict] = {}
    for row in members or []:
        user_id = row.get("user_id")
        if not user_id:
            continue
        known[user_id] = {
            "real_name": row.get("real_name") or user_id,
            "active": bool(row.get("active", True)),
            "on_vacation": bool(row.get("on_vacation") or False),
        }

    # Submissions are keyed by (member, day) because a standup row carries no
    # schedule id. `responses` stays a raw count over the window so callers that
    # already read it (the mailer, the MCP tools) keep their meaning.
    per_day: dict[tuple[str, date], int] = {}
    responses: dict[str, int] = {}
    blockers: dict[str, int] = {}
    last_standup: dict[str, Any] = {}
    window_start = now.astimezone(timezone.utc).date() - timedelta(days=days - 1)
    for row in submissions or []:
        user_id = row.get("user_id")
        day = _as_date(row.get("standup_date"))
        if not user_id or day is None:
            continue
        per_day[(user_id, day)] = per_day.get((user_id, day), 0) + 1
        if day >= window_start:
            responses[user_id] = responses.get(user_id, 0) + 1
            if row.get("has_blockers"):
                blockers[user_id] = blockers.get(user_id, 0) + 1
        submitted_at = row.get("submitted_at")
        if submitted_at is not None:
            previous = last_standup.get(user_id)
            try:
                if previous is None or submitted_at > previous:
                    last_standup[user_id] = submitted_at
            except TypeError:
                last_standup.setdefault(user_id, submitted_at)

    active_schedules = sorted(
        (s for s in (schedules or []) if s.get("active", True)),
        key=lambda s: (_schedule_minutes(s), int(s.get("id") or 0)),
    )

    schedule_rows: dict[int, dict] = {}
    enrolled: set[str] = set()
    # (member, day) -> the schedule ids that asked them for a standup that day,
    # in schedule_time order.
    occurrences: dict[tuple[str, date], list[int]] = {}
    for schedule in active_schedules:
        schedule_id = int(schedule.get("id") or 0)
        dates = _occurrence_dates(schedule, days, now)
        counted: list[str] = []
        seen: set[str] = set()
        for user_id in schedule.get("participants") or []:
            if not user_id or user_id in seen:
                continue
            seen.add(user_id)
            enrolled.add(user_id)
            member = known.get(user_id)
            if member is None:
                # In a schedule but missing from the members table: the bot
                # still DMs them, so they belong in the denominator.
                known[user_id] = {"real_name": user_id, "active": True, "on_vacation": False}
            elif not member["active"] or member["on_vacation"]:
                # Inactive, or on approved leave, so nobody asked them today.
                continue
            counted.append(user_id)
        schedule_rows[schedule_id] = {
            "schedule_id": schedule_id,
            "name": schedule.get("name") or f"Schedule {schedule_id}",
            "occurrence_days": len(dates),
            "participants": len(counted),
            "expected": len(dates) * len(counted),
            "completed": 0,
        }
        for user_id in counted:
            for day in dates:
                occurrences.setdefault((user_id, day), []).append(schedule_id)

    expected_total = 0
    completed_total = 0
    per_member: dict[str, dict] = {}
    for (user_id, day), schedule_ids in occurrences.items():
        expected_here = len(schedule_ids)
        completed_here = min(per_day.get((user_id, day), 0), expected_here)
        expected_total += expected_here
        completed_total += completed_here
        stats = per_member.setdefault(user_id, {"expected": 0, "completed": 0, "schedules": set()})
        stats["expected"] += expected_here
        stats["completed"] += completed_here
        stats["schedules"].update(schedule_ids)
        for schedule_id in schedule_ids[:completed_here]:
            schedule_rows[schedule_id]["completed"] += 1

    member_rows = []
    for user_id, member in known.items():
        if not member["active"]:
            continue
        stats = per_member.get(user_id) or {"expected": 0, "completed": 0, "schedules": set()}
        member_rows.append(
            {
                "user_id": user_id,
                "real_name": member["real_name"],
                "enrolled": user_id in enrolled,
                "on_vacation": member["on_vacation"],
                "expected": stats["expected"],
                "completed": stats["completed"],
                "missed": stats["expected"] - stats["completed"],
                "responses": responses.get(user_id, 0),
                "completion_rate": _percentage(stats["completed"], stats["expected"]),
                "last_standup": last_standup.get(user_id),
                "days_with_blockers": blockers.get(user_id, 0),
                "schedules": [schedule_rows[sid]["name"] for sid in sorted(stats["schedules"])],
            }
        )
    member_rows.sort(
        key=lambda r: (
            not r["enrolled"],
            -r["completion_rate"],
            -r["responses"],
            (r["real_name"] or "").lower(),
        )
    )

    for row in schedule_rows.values():
        row["missed"] = row["expected"] - row["completed"]
        row["completion_rate"] = _percentage(row["completed"], row["expected"])

    return {
        "days": days,
        "expected": expected_total,
        "completed": completed_total,
        "missed": expected_total - completed_total,
        "completion_rate": _percentage(completed_total, expected_total),
        "responses": sum(responses.values()),
        "responding_members": len([user for user, count in responses.items() if count > 0]),
        "total_members": len(member_rows),
        "enrolled_members": len([row for row in member_rows if row["enrolled"]]),
        "unenrolled_members": len([row for row in member_rows if not row["enrolled"]]),
        "on_vacation_members": len([row for row in member_rows if row["on_vacation"]]),
        "schedules": [schedule_rows[sid] for sid in sorted(schedule_rows)],
        "members": member_rows,
    }


def _fetch_participation_inputs(team_id: str, days: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Load everything the participation model needs, in three fixed queries.

    Three round trips whatever the workspace looks like, rather than one query
    per schedule per day per participant. The calendar expansion itself is done
    in Python instead of with `generate_series`: the row counts involved are
    small (tens of schedules, hundreds of members, a week of submissions), each
    schedule expands in its own IANA timezone which the Postgres session does
    not know about, and keeping the arithmetic out of SQL is what lets it be
    tested against hand-computed numbers without a live database.
    """
    sql_schedules = """
        SELECT id, name, schedule_time, schedule_tz, schedule_days, participants, active
        FROM standup_schedules
        WHERE team_id = %s AND active = TRUE
        ORDER BY schedule_time, id
    """
    sql_members = """
        SELECT user_id, real_name, active, COALESCE(on_vacation, FALSE) AS on_vacation
        FROM members
        WHERE team_id = %s AND active = TRUE
    """
    # One extra day back absorbs the offset between the server's CURRENT_DATE
    # and a schedule whose local date is behind it.
    sql_submissions = """
        SELECT user_id, standup_date, has_blockers, submitted_at
        FROM standups
        WHERE team_id = %s AND standup_date >= CURRENT_DATE - %s * INTERVAL '1 day'
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql_schedules, (team_id,))
            schedules = [dict(r) for r in cur.fetchall()]
            cur.execute(sql_members, (team_id,))
            members = [dict(r) for r in cur.fetchall()]
            cur.execute(sql_submissions, (team_id, int(days)))
            submissions = [dict(r) for r in cur.fetchall()]
    return schedules, members, submissions


def get_participation_overview(team_id: str, days: int = 7) -> dict:
    """Return workspace, per-schedule and per-member participation for the last N days."""
    days = max(1, int(days or 1))
    schedules, members, submissions = _fetch_participation_inputs(team_id, days)
    return compute_participation(schedules, members, submissions, days=days)


def get_participation_stats(team_id: str, days: int = 7) -> list[dict]:
    """Return per-member participation stats for the last N days.

    Members in no active schedule are returned with `enrolled` False and an
    expected count of 0 rather than being dropped, so a caller can show them as
    "not enrolled" instead of "0/7".
    """
    return get_participation_overview(team_id, days=days)["members"]


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
    """Return all standup schedules for a workspace (includes paused)."""
    sql = "SELECT * FROM standup_schedules WHERE team_id = %s ORDER BY created_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def create_standup_schedule(team_id: str, **kwargs) -> dict:
    """Insert a new standup schedule row and return it."""
    allowed = {
        "name",
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "participants",
        "reminder_minutes",
        "active",
        "post_to_thread",
        "notify_on_report",
        "weekend_reminder",
        "report_channel",
        "report_time",
        "sync_with_channel",
        "group_by",
        "prepopulate_answers",
        "allow_edit_after_report",
        "post_summary",
    }
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


def upsert_daily_thread(team_id: str, channel_id: str, thread_date: str, parent_ts: str, schedule_id: int = 0) -> None:
    """Persist the parent message ts for today's standup thread.

    Scoped by schedule_id so workspaces running multiple standups on the same
    channel (morning + evening) get a distinct thread parent per schedule.
    """
    sql = """
        INSERT INTO daily_standup_threads (team_id, channel_id, thread_date, schedule_id, parent_ts)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (team_id, channel_id, thread_date, schedule_id) DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, (team_id, channel_id, thread_date, int(schedule_id or 0), parent_ts))
            except Exception:
                pass


def get_daily_thread_ts(team_id: str, channel_id: str, thread_date: str, schedule_id: int = 0) -> str | None:
    """Look up the parent ts for today's standup thread, if one was created."""
    sql = """
        SELECT parent_ts FROM daily_standup_threads
        WHERE team_id = %s AND channel_id = %s AND thread_date = %s AND schedule_id = %s
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, (team_id, channel_id, thread_date, int(schedule_id or 0)))
            except Exception:
                return None
            row = cur.fetchone()
    return row[0] if row else None


def get_schedule_for_user(team_id: str, user_id: str) -> dict | None:
    """Return the active schedule the user is most likely currently doing.

    When a user is in one schedule this is unambiguous. When they are in several
    (e.g. morning + evening standups, or multiple teams), pick the schedule whose
    `schedule_time` most recently passed in its own timezone — that is almost
    always the standup the user is filling out right now. Falls back to the
    oldest schedule if none has a time within the past 2 hours.

    Used when a standup is started outside the scheduled DM (e.g. user typed
    "standup" in DM, clicked App Home's Start button, or ran /standup) so the
    session posts to the correct channel instead of some other schedule's channel.
    """
    sql = """
        SELECT * FROM standup_schedules
        WHERE team_id = %s
          AND active = TRUE
          AND %s = ANY(participants)
        ORDER BY created_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                cur.execute(sql, (team_id, user_id))
            except Exception:
                return None
            rows = cur.fetchall() or []
    if not rows:
        return None
    schedules = [dict(r) for r in rows]
    if len(schedules) == 1:
        return schedules[0]

    # Multiple schedules — prefer the one whose scheduled time has most recently
    # passed within the last 2 hours in the schedule's own timezone.
    from datetime import datetime  # noqa: PLC0415

    import pytz  # noqa: PLC0415

    best = None
    best_age_min: float | None = None
    for sched in schedules:
        tz_name = sched.get("schedule_tz") or "UTC"
        time_str = sched.get("schedule_time") or ""
        try:
            tz = pytz.timezone(tz_name)
            now_local = datetime.now(tz)
            hh, mm = time_str.split(":")
            sched_today = now_local.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except Exception:
            continue
        age_min = (now_local - sched_today).total_seconds() / 60.0
        # Prefer schedules whose time has passed within the last 2 hours.
        if 0 <= age_min <= 120 and (best_age_min is None or age_min < best_age_min):
            best = sched
            best_age_min = age_min
    return best or schedules[0]


def get_standup_schedule_for_channel(team_id: str, channel_id: str) -> dict | None:
    """Return the active standup schedule for a given channel (scoped to team_id).

    When a channel has multiple active schedules (e.g. morning + evening standups),
    prefer the one whose `schedule_time` most recently passed within the last 2 hours
    in its own timezone. Falls back to the oldest schedule otherwise.
    """
    sql = """
        SELECT * FROM standup_schedules
        WHERE team_id = %s AND channel_id = %s AND active = TRUE
        ORDER BY created_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, channel_id))
            rows = cur.fetchall() or []
    if not rows:
        return None
    schedules = [dict(r) for r in rows]
    if len(schedules) == 1:
        return schedules[0]

    from datetime import datetime  # noqa: PLC0415

    import pytz  # noqa: PLC0415

    best = None
    best_age_min: float | None = None
    for sched in schedules:
        tz_name = sched.get("schedule_tz") or "UTC"
        time_str = sched.get("schedule_time") or ""
        try:
            tz = pytz.timezone(tz_name)
            now_local = datetime.now(tz)
            hh, mm = time_str.split(":")
            sched_today = now_local.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except Exception:
            continue
        age_min = (now_local - sched_today).total_seconds() / 60.0
        if 0 <= age_min <= 120 and (best_age_min is None or age_min < best_age_min):
            best = sched
            best_age_min = age_min
    return best or schedules[0]


def update_standup_schedule(team_id: str, schedule_id: int, **kwargs) -> dict | None:
    """Update a standup schedule by id (scoped to team_id)."""
    allowed = {
        "name",
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "participants",
        "reminder_minutes",
        "active",
        "post_to_thread",
        "notify_on_report",
        "weekend_reminder",
        "report_channel",
        "report_time",
        "sync_with_channel",
        "group_by",
        "prepopulate_answers",
        "allow_edit_after_report",
        "post_summary",
    }
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
    """Hard-delete a standup schedule (scoped to team_id)."""
    sql = "DELETE FROM standup_schedules WHERE id = %s AND team_id = %s"
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


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------


def get_member_role(team_id: str, user_id: str) -> str:
    """Return 'admin' or 'member' for a user. Defaults to 'member' if not found."""
    sql = "SELECT role FROM members WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return (row[0] if row else None) or "member"


def set_member_role(team_id: str, user_id: str, role: str) -> None:
    """Set a member's role to 'admin' or 'member'."""
    if role not in ("admin", "member"):
        raise ValueError(f"Invalid role: {role}")
    sql = "UPDATE members SET role = %s WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (role, team_id, user_id))


def ensure_admin(team_id: str, user_id: str) -> None:
    """Upsert user as admin — used on OAuth install."""
    sql = """
        INSERT INTO members (team_id, user_id, role)
        VALUES (%s, %s, 'admin')
        ON CONFLICT (team_id, user_id) DO UPDATE SET role = 'admin'
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))


# ---------------------------------------------------------------------------
# Standup editing helpers
# ---------------------------------------------------------------------------


def get_latest_standup(user_id: str, team_id: str) -> dict | None:
    """Return the most recent standup for a user/team, or None."""
    sql = """
        SELECT * FROM standups
        WHERE team_id = %s AND user_id = %s
        ORDER BY submitted_at DESC
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return dict(row) if row else None


def update_standup(user_id: str, team_id: str, **kwargs: Any) -> None:
    """Update the most recent standup for a user/team with the provided fields.

    Accepted keyword arguments: yesterday, today, blockers, mood.
    Automatically recomputes ``has_blockers`` when ``blockers`` is updated.
    """
    allowed = {"yesterday", "today", "blockers", "mood"}
    updates: dict[str, Any] = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    if "blockers" in updates:
        blocker_val: str = updates["blockers"] or ""
        updates["has_blockers"] = blocker_val.strip().lower() not in ("none", "no", "nope", "-", "n/a", "")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values: list[Any] = list(updates.values())
    sql = f"""
        UPDATE standups SET {set_clause}
        WHERE id = (
            SELECT id FROM standups
            WHERE team_id = %s AND user_id = %s
            ORDER BY submitted_at DESC
            LIMIT 1
        )
    """
    values.extend([team_id, user_id])
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
    logger.info("Updated standup for %s / %s", team_id, user_id)


# ---------------------------------------------------------------------------
# MCP API keys
# ---------------------------------------------------------------------------

import hashlib as _hashlib
import secrets as _secrets


def generate_mcp_key(team_id: str, name: str = "Default") -> str:
    """Generate a new MCP API key, store its hash, return the full key."""
    key = "mrn_" + _secrets.token_urlsafe(32)
    key_hash = _hashlib.sha256(key.encode()).hexdigest()
    key_prefix = key[:12]
    sql = """
        INSERT INTO mcp_api_keys (team_id, key_hash, key_prefix, name)
        VALUES (%s, %s, %s, %s)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, key_hash, key_prefix, name))
    logger.info("Generated MCP key %s... for team %s", key_prefix, team_id)
    return key


def get_mcp_keys(team_id: str) -> list[dict]:
    """Return all MCP keys for a team (prefix only, not the raw key)."""
    sql = """
        SELECT id, key_prefix, name, created_at, last_used_at, active
        FROM mcp_api_keys
        WHERE team_id = %s
        ORDER BY created_at DESC
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            return [dict(r) for r in cur.fetchall()]


def revoke_mcp_key(key_id: int, team_id: str) -> None:
    """Soft-delete an MCP API key (marks inactive)."""
    sql = "UPDATE mcp_api_keys SET active = FALSE WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (key_id, team_id))


def verify_mcp_key(key: str) -> str | None:
    """Verify an API key, update last_used_at, return team_id or None."""
    key_hash = _hashlib.sha256(key.encode()).hexdigest()
    sql = """
        UPDATE mcp_api_keys SET last_used_at = NOW()
        WHERE key_hash = %s AND active = TRUE
        RETURNING team_id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (key_hash,))
            row = cur.fetchone()
    return row[0] if row else None


def delete_installation(team_id: str) -> bool:
    """Delete a workspace installation and all cascading data (members, standups, config, etc.).

    All child tables reference installations(team_id) with ON DELETE CASCADE,
    so a single DELETE removes all workspace data.
    Returns True if a row was deleted, False if team_id was not found.
    """
    sql = "DELETE FROM installations WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            return cur.rowcount > 0
