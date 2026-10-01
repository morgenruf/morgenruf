"""Database module — PostgreSQL connection pool and query helpers."""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Any, Generator
from zoneinfo import ZoneInfo

from src.core.timezones import canonical_tz, local_today

logger = logging.getLogger(__name__)

_pool = None
_pool_lock = Lock()

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool
except ImportError:
    ThreadedConnectionPool = None


# Pools a forked child inherited from its parent. Kept referenced so they are
# never garbage collected in the child: closing one would send Postgres a
# terminate message on a socket the parent is still using.
_inherited_pools: list = []


def _forget_pool_after_fork() -> None:
    """Give a forked process its own connections.

    gunicorn forks its worker after create_app, which already opened this
    pool to load installations, and the scheduler keeps using it in the
    master. The worker inherited the same sockets, so a web request and a
    scheduled job could interleave on one connection, which surfaces as
    "no results to fetch" or "PGRES_TUPLES_OK and no message from the libpq".
    """
    global _pool
    if _pool is not None:
        _inherited_pools.append(_pool)
        _pool = None


os.register_at_fork(after_in_child=_forget_pool_after_fork)


def initialize_pool():
    """Open PostgreSQL only on first use, never while importing HTTP routes."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            database_url = os.environ.get("DATABASE_URL", "")
            if not database_url or ThreadedConnectionPool is None:
                raise RuntimeError("Database pool not initialised")
            _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=database_url)
    return _pool


def get_conn():
    """Borrow a connection, lazily creating the pool."""
    return initialize_pool().getconn()


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
    granted_scopes: list[str] | None = None,
) -> bool:
    """Insert or update an OAuth installation record. Returns True if this is a new installation.

    The first installer keeps installed_by_user_id on a reinstall. A later
    OAuth run is often a member signing in to the dashboard, and
    get_member_role treats the installer as a permanent admin.

    A workspace whose data was purged keeps a bare row, so coming back
    conflicts with it. That still counts as new: nothing of the old install
    is left, so the installer gets the welcome and the clock starts again.
    `prior` reads the row as it was before this statement.
    """
    sql = """
        WITH prior AS (SELECT purged_at FROM installations WHERE team_id = %s)
        INSERT INTO installations (team_id, team_name, bot_token, bot_user_id, app_id,
            installed_by_user_id, bot_refresh_token, bot_token_expires_at,
            granted_scopes, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (team_id) DO UPDATE SET
            installed_at = CASE WHEN installations.purged_at IS NOT NULL THEN NOW()
                                ELSE installations.installed_at END,
            purged_at = NULL,
            team_name = EXCLUDED.team_name,
            bot_token = EXCLUDED.bot_token,
            bot_user_id = EXCLUDED.bot_user_id,
            app_id = EXCLUDED.app_id,
            installed_by_user_id = COALESCE(installations.installed_by_user_id, EXCLUDED.installed_by_user_id),
            bot_refresh_token = EXCLUDED.bot_refresh_token,
            bot_token_expires_at = EXCLUDED.bot_token_expires_at,
            granted_scopes = COALESCE(EXCLUDED.granted_scopes, installations.granted_scopes),
            updated_at = NOW()
        RETURNING (xmax = 0) OR EXISTS (SELECT 1 FROM prior WHERE purged_at IS NOT NULL) AS is_new
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    team_id,
                    team_id,
                    team_name,
                    bot_token,
                    bot_user_id,
                    app_id,
                    installed_by_user_id,
                    bot_refresh_token,
                    bot_token_expires_at,
                    granted_scopes,
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


def deactivate_installation(team_id: str, reason: str) -> bool:
    """Mark an installation as gone. Returns True if this changed anything.

    Called when Slack tells us the app is no longer installed. The row stays so
    standup history keeps its reference and a reinstall can revive it.
    """
    sql = """
        UPDATE installations
        SET active = FALSE, deactivated_at = NOW(), deactivated_reason = %s
        WHERE team_id = %s AND active
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (reason[:200], team_id))
            changed = (cur.rowcount or 0) > 0
    if changed:
        logger.info("Retired installation %s: %s", team_id, reason)
    return changed


def reactivate_installation(team_id: str) -> bool:
    """Bring a retired installation back. Called when a workspace reinstalls."""
    sql = """
        UPDATE installations
        SET active = TRUE, deactivated_at = NULL, deactivated_reason = NULL
        WHERE team_id = %s AND NOT active
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            changed = (cur.rowcount or 0) > 0
    if changed:
        logger.info("Installation %s is back", team_id)
    return changed


def get_all_installations(include_inactive: bool = False) -> list[dict]:
    """Return installation rows, live ones by default.

    An installation whose Slack app has been uninstalled keeps answering
    account_inactive forever. Excluding those by default stops the scheduler
    registering jobs for workspaces that cannot receive them, and stops the
    member sync burning API calls on tokens Slack has already invalidated.
    """
    sql = "SELECT * FROM installations ORDER BY installed_at"
    if not include_inactive:
        sql = "SELECT * FROM installations WHERE active ORDER BY installed_at"
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
    if "schedule_tz" in fields:
        fields["schedule_tz"] = canonical_tz(fields["schedule_tz"])
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


def get_standups_for_schedule(
    team_id: str, schedule_id: int, days: int = 1, for_date: date | None = None
) -> list[dict]:
    """Today's answers for one standup only.

    The workspace-wide query is wrong for a per-team digest: a workspace with
    ten standups would mail every team's answers to every lead.

    `for_date` is the schedule's local today (see timezones.local_today). The
    database's CURRENT_DATE is UTC, which is a different day for most of the
    world at report time. Without it the UTC date is used.
    """
    day = for_date or local_today("UTC")
    sql = """
        SELECT s.*, m.real_name AS user_name
        FROM standups s
        LEFT JOIN members m ON m.team_id = s.team_id AND m.user_id = s.user_id
        WHERE s.team_id = %s AND s.schedule_id = %s
          AND s.standup_date >= %s::date - (%s - 1)
          AND s.standup_date <= %s::date
        ORDER BY s.submitted_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, schedule_id, day, days, day))
            return [dict(r) for r in cur.fetchall()]


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

    Their profile is different: birthdays and start dates should not outlive
    the person's time in the workspace. Leaving stamps `left_at`, and the
    nightly purge deletes profiles gone for 30 days. Coming back clears the
    stamp, so a Slack deactivate and reactivate loses nothing. Both happen in
    the same transaction as the flag, so the two can never disagree.
    """
    if not user_ids:
        return 0
    ids = list(user_ids)
    sql = "UPDATE members SET active = %s WHERE team_id = %s AND user_id = ANY(%s) AND active <> %s"
    if active:
        profile_sql = (
            "UPDATE member_profiles SET left_at = NULL WHERE team_id = %s AND user_id = ANY(%s) AND left_at IS NOT NULL"
        )
    else:
        profile_sql = (
            "UPDATE member_profiles SET left_at = NOW() WHERE team_id = %s AND user_id = ANY(%s) AND left_at IS NULL"
        )
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (active, team_id, ids, active))
            changed = cur.rowcount or 0
            cur.execute(profile_sql, (team_id, ids))
            return changed


def remove_participants_everywhere(team_id: str, user_ids: list[str]) -> int:
    """Drop these users from every schedule's participant list.

    Deactivating a member is not enough on its own. The participation model
    treats anyone named in a schedule's `participants` as expected, inventing a
    row for them when they are not in the members table, so a person who left
    would keep inflating the denominator and keep being listed on the standup.

    Returns the number of schedules changed.
    """
    if not user_ids:
        return 0
    sql = """
        UPDATE standup_schedules
        SET participants = ARRAY(SELECT unnest(participants) EXCEPT SELECT unnest(%s::text[]))
        WHERE team_id = %s AND participants && %s::text[]
    """
    ids = list(user_ids)
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ids, team_id, ids))
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
    avatar_url: str | None = None,
    display_name: str | None = None,
) -> None:
    """Insert or update a member record. Only non-None values overwrite existing ones."""
    sql = """
        INSERT INTO members (team_id, user_id, real_name, email, tz, avatar_url, display_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (team_id, user_id) DO UPDATE SET
            real_name = COALESCE(EXCLUDED.real_name, members.real_name),
            email = COALESCE(EXCLUDED.email, members.email),
            tz = COALESCE(EXCLUDED.tz, members.tz),
            avatar_url = COALESCE(EXCLUDED.avatar_url, members.avatar_url),
            display_name = COALESCE(EXCLUDED.display_name, members.display_name),
            active = TRUE
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, real_name, email, canonical_tz(tz), avatar_url, display_name))


# ---------------------------------------------------------------------------
# Member profiles
# ---------------------------------------------------------------------------

# Columns a write may set. nudged_at and left_at belong to jobs, never to a
# form, so neither is here.
PROFILE_FIELDS = ("birth_month", "birth_day", "start_date", "role", "location", "ask_me_about", "celebrate")

# How long a profile outlives its owner leaving the workspace.
PROFILE_RETENTION_DAYS = 30

# pg_try_advisory_xact_lock key for the purge, so two pods running the nightly
# job at the same minute do the work once. Any constant works; this one spells
# "PROF" in ASCII.
_PROFILE_PURGE_LOCK = 0x50524F46


class ProfileValidationError(ValueError):
    """A profile write was refused. `messages` maps field to reasons."""

    def __init__(self, messages: dict):
        self.messages = messages
        first = next(iter(messages.values()), ["invalid profile"])
        super().__init__(first[0] if isinstance(first, list) and first else str(first))


def validate_member_profile(fields: dict) -> dict:
    """Load `fields` through schemas.MemberProfile, or raise ProfileValidationError.

    Unknown keys are dropped, which is how a birth year sent by any caller is
    discarded before it could reach the database.
    """
    from marshmallow import ValidationError  # noqa: PLC0415

    from src.core.api_schemas import MemberProfile  # noqa: PLC0415

    try:
        return MemberProfile().load(fields or {})
    except ValidationError as exc:
        messages = exc.messages if isinstance(exc.messages, dict) else {"_schema": exc.messages}
        raise ProfileValidationError(messages) from None


def upsert_member_profile(team_id: str, user_id: str, fields: dict, updated_by: str) -> dict:
    """Create or change one profile. The only function that writes one.

    Every entry point (App Home, /morgenruf profile, the dashboard, the admin
    CSV import) comes through here, so they share one validation and all
    record who wrote last. Only the fields present in `fields` change, which
    is how an import sets dates without clearing someone's role.

    Returns the stored row.
    """
    if not team_id or not user_id:
        raise ProfileValidationError({"user_id": ["A profile needs a workspace and a person."]})
    if not updated_by:
        raise ProfileValidationError({"updated_by": ["Record who is making the change."]})
    clean = validate_member_profile(fields)
    columns = [c for c in PROFILE_FIELDS if c in clean]
    names = ", ".join(["team_id", "user_id", *columns, "updated_by", "updated_at"])
    placeholders = ", ".join(["%s"] * (len(columns) + 3) + ["NOW()"])
    updates = ", ".join(
        [f"{c} = EXCLUDED.{c}" for c in columns] + ["updated_by = EXCLUDED.updated_by", "updated_at = NOW()"]
    )
    sql = f"""
        INSERT INTO member_profiles ({names})
        VALUES ({placeholders})
        ON CONFLICT (team_id, user_id) DO UPDATE SET {updates}
        RETURNING *
    """
    params = (team_id, user_id, *[clean[c] for c in columns], updated_by)
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    return dict(row) if row else {}


def get_member_profile(team_id: str, user_id: str) -> dict | None:
    """One person's profile, or None when they have never filled it in."""
    sql = "SELECT * FROM member_profiles WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return dict(row) if row else None


def list_member_profiles(team_id: str, include_departed: bool = False) -> list[dict]:
    """Every profile in a workspace. People who left are excluded unless asked for."""
    sql = "SELECT * FROM member_profiles WHERE team_id = %s"
    if not include_departed:
        sql += " AND left_at IS NULL"
    sql += " ORDER BY user_id"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def sync_profile_departures(team_id: str, live_user_ids) -> tuple[int, int]:
    """Stamp or clear left_at from who Slack says is in the workspace now.

    set_members_active covers people with a members row. A profile can exist
    without one: an admin imports dates for everyone in Slack, not only the
    people on a standup. Without this, those profiles would never be marked
    as left and never purged. Returns (left, returned).

    The caller must pass a directory it trusts. The member sync already skips
    a workspace whose user list failed or came back empty, and so must this.
    """
    live = sorted({u for u in (live_user_ids or ()) if u})
    if not live:
        return 0, 0
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE member_profiles SET left_at = NOW() "
                "WHERE team_id = %s AND left_at IS NULL AND NOT (user_id = ANY(%s))",
                (team_id, live),
            )
            left = cur.rowcount or 0
            cur.execute(
                "UPDATE member_profiles SET left_at = NULL "
                "WHERE team_id = %s AND left_at IS NOT NULL AND user_id = ANY(%s)",
                (team_id, live),
            )
            returned = cur.rowcount or 0
    return left, returned


def purge_departed_profiles(days: int = PROFILE_RETENTION_DAYS) -> int:
    """Delete profiles of people who left more than `days` ago. Returns how many.

    Safe to run from every pod at once: the advisory lock lets one of them do
    the work and the others return 0, and the statements are idempotent
    anyway, so a second run finds nothing left to do.

    Someone marked active again by a path other than the sync (a DM to the
    bot re-registers them) still carries a stale left_at. That stamp is
    cleared here first, and the delete re-checks the members table, so an
    active person's profile is never removed.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (_PROFILE_PURGE_LOCK,))
            row = cur.fetchone()
            if not row or not row[0]:
                return 0
            cur.execute(
                """
                UPDATE member_profiles p SET left_at = NULL
                FROM members m
                WHERE m.team_id = p.team_id AND m.user_id = p.user_id
                  AND m.active = TRUE AND p.left_at IS NOT NULL
                """
            )
            cur.execute(
                """
                DELETE FROM member_profiles p
                WHERE p.left_at IS NOT NULL
                  AND p.left_at < NOW() - make_interval(days => %s)
                  AND NOT EXISTS (
                      SELECT 1 FROM members m
                      WHERE m.team_id = p.team_id AND m.user_id = p.user_id AND m.active = TRUE
                  )
                """,
                (int(days),),
            )
            return cur.rowcount or 0


def claim_profile_nudges(team_id: str, user_ids, cooldown_days: int | None = None) -> list[str]:
    """Stamp nudged_at for whoever may be asked for their dates now, and return them.

    With no cooldown, only people never asked before are claimed: the one-time
    DM. With a cooldown, anyone not asked in that many days is claimed too:
    the admin's "Ask for dates". Either way people who opted out of being
    celebrated, or who already have a birthday or start date, are never
    claimed.

    The stamp is written before any DM is sent, in one statement, so two pods
    running the same pass cannot both claim the same person. A person with no
    profile row yet gets one holding only nudged_at.
    """
    ids = sorted({u for u in (user_ids or ()) if u})
    if not ids:
        return []
    if cooldown_days is None:
        may_ask = "member_profiles.nudged_at IS NULL"
        params: tuple = (team_id, ids)
    else:
        may_ask = "(member_profiles.nudged_at IS NULL OR member_profiles.nudged_at < NOW() - make_interval(days => %s))"
        params = (team_id, ids, int(cooldown_days))
    sql = f"""
        INSERT INTO member_profiles (team_id, user_id, nudged_at)
        SELECT %s, u, NOW() FROM unnest(%s::text[]) AS u
        ON CONFLICT (team_id, user_id) DO UPDATE SET nudged_at = NOW()
        WHERE {may_ask}
          AND member_profiles.celebrate
          AND member_profiles.birth_month IS NULL
          AND member_profiles.start_date IS NULL
        RETURNING user_id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [r[0] for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Workspace calendar: working days and holidays
# ---------------------------------------------------------------------------


def get_working_days(team_id: str) -> str:
    """The workspace's working week as "mon,tue,...", Monday to Friday by default."""
    from src.core.workspace_calendar import DEFAULT_WORKING_DAYS  # noqa: PLC0415

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT working_days FROM workspace_config WHERE team_id = %s", (team_id,))
            row = cur.fetchone()
    return (row[0] if row and row[0] else None) or DEFAULT_WORKING_DAYS


def set_working_days(team_id: str, working_days: str) -> str:
    """Store the working week. The caller validates; this only writes.

    Inserts a default config row when the workspace has none, which is what
    the OAuth callback does on install, so standup sees the same row either
    way.
    """
    sql = """
        INSERT INTO workspace_config (team_id, working_days, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (team_id) DO UPDATE SET working_days = EXCLUDED.working_days, updated_at = NOW()
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, working_days))
    return working_days


def list_holidays(team_id: str) -> list[dict]:
    """Every stored holiday for a workspace, oldest first."""
    sql = "SELECT date, name FROM workspace_holidays WHERE team_id = %s ORDER BY date"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            return [dict(r) for r in cur.fetchall()]


def upsert_holidays(team_id: str, holidays) -> int:
    """Add holidays, renaming any date already on the list. Returns how many."""
    rows = [(team_id, h["date"], h["name"]) for h in holidays or ()]
    if not rows:
        return 0
    sql = """
        INSERT INTO workspace_holidays (team_id, date, name)
        VALUES (%s, %s, %s)
        ON CONFLICT (team_id, date) DO UPDATE SET name = EXCLUDED.name
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(sql, row)
    return len(rows)


def delete_holiday(team_id: str, day) -> bool:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workspace_holidays WHERE team_id = %s AND date = %s", (team_id, day))
            return (cur.rowcount or 0) > 0


def purge_old_holidays(days: int = 365) -> int:
    """Delete holidays more than `days` in the past, in every workspace.

    Idempotent, so every pod may run it; the second finds nothing to do.
    """
    sql = "DELETE FROM workspace_holidays WHERE date < CURRENT_DATE - %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (int(days),))
            return cur.rowcount or 0


def claim_scheduler_run(job_id: str, run_at: datetime) -> bool:
    """Claim one firing of a cron job. True for exactly one pod per firing."""
    sql = """
        INSERT INTO scheduler_runs (job_id, run_at) VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        RETURNING 1
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id, run_at))
            return cur.fetchone() is not None


def purge_scheduler_runs(days: int = 7) -> int:
    """Delete claims older than `days`. Idempotent, so every pod may run it."""
    sql = "DELETE FROM scheduler_runs WHERE claimed_at < NOW() - make_interval(days => %s)"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (int(days),))
            return cur.rowcount or 0


def claim_login_token(nonce: str) -> bool:
    """Mark a dashboard login token as used. True only the first time."""
    sql = """
        INSERT INTO login_token_uses (nonce) VALUES (%s)
        ON CONFLICT DO NOTHING
        RETURNING 1
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (nonce,))
            return cur.fetchone() is not None


def purge_login_token_uses() -> int:
    """Forget used login tokens once they are past their five minute life."""
    sql = "DELETE FROM login_token_uses WHERE used_at < NOW() - INTERVAL '1 hour'"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.rowcount or 0


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
    questions: list[str] | None = None,
    schedule_id: int | None = None,
    standup_date: date | None = None,
) -> int | None:
    """Persist a completed standup. Returns the new standup ID.

    Pass `questions` whenever the caller knows them. The three answer columns
    are named after the default questions, but a schedule can ask anything, so
    without the question list there is no way to tell whether the third answer
    is a blocker or an availability figure. See blockers.py.

    Pass `standup_date` as the schedule's local today. The column defaults to
    the database's CURRENT_DATE, which is UTC, so a Sydney team answering at
    09:00 was filed under yesterday and its 10:00 report found nothing.
    """
    import src.modules.standup.blockers as _blockers  # noqa: PLC0415

    if questions:
        has_blockers = _blockers.has_blockers(questions, [yesterday, today, blockers])
    else:
        has_blockers = _blockers.reports_a_blocker(blockers)
    sql = """
        INSERT INTO standups
            (team_id, user_id, yesterday, today, blockers, has_blockers, mood, schedule_id, standup_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    day = standup_date or local_today("UTC")
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, yesterday, today, blockers, has_blockers, mood, schedule_id, day))
            row = cur.fetchone()
    standup_id = row[0] if row else None
    logger.info("Saved standup %s for %s / %s", standup_id, team_id, user_id)
    return standup_id


def workspace_local_today(team_id: str) -> date:
    """The day the workspace is on, for views with no single schedule to go by.

    The first active standup's timezone, then the workspace default, then UTC:
    the same order as insights.today.workspace_today. The database's
    CURRENT_DATE is UTC, which is the wrong day for most teams for part of
    every day.
    """
    tz_name = None
    try:
        schedules = [s for s in get_standup_schedules(team_id) if s.get("active", True)]
        tz_name = next((s.get("schedule_tz") for s in schedules if s.get("schedule_tz")), None)
        if not tz_name:
            tz_name = (get_workspace_config(team_id) or {}).get("schedule_tz")
    except Exception as exc:  # noqa: BLE001 - a lookup failure falls back to UTC
        logger.debug("Could not resolve the workspace timezone for %s: %s", team_id, exc)
    return local_today(tz_name or "UTC")


def get_today_standups(team_id: str, for_date: date | None = None) -> list[dict]:
    """Return all standup submissions for today.

    `for_date` is the standup's local today; the UTC date is only a fallback
    for a caller with no timezone to go on.
    """
    sql = """
        SELECT * FROM standups
        WHERE team_id = %s AND standup_date = %s
        ORDER BY submitted_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, for_date or local_today("UTC")))
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


def skip_today(team_id: str, user_id: str, for_date: date | None = None) -> None:
    """Mark user as skipping today's standup.

    `for_date` must be the same local day the scheduler checks with, or a skip
    filed in the morning in Sydney lands on the previous UTC day and is ignored.
    """
    sql = """
        INSERT INTO user_skip (team_id, user_id, skip_date)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, for_date or local_today("UTC")))


def is_skipped_today(team_id: str, user_id: str, for_date: date | None = None) -> bool:
    """Return True if user has skipped `for_date` (the standup's local today)."""
    sql = "SELECT 1 FROM user_skip WHERE team_id=%s AND user_id=%s AND skip_date=%s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, for_date or local_today("UTC")))
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


# How far back a streak is looked for. A year of unbroken standups is already
# more than the App Home badge needs, and it keeps the query bounded.
STREAK_LOOKBACK_DAYS = 400


def streak_from_dates(standup_dates, working_days, today: date, holidays=()) -> int:
    """Count the member's consecutive scheduled days with a standup, newest first.

    Only the days the member is actually asked count: their schedules' weekdays
    minus company holidays. A weekend or a holiday between two answered days
    neither breaks the streak nor adds to it. Today counts once answered, but
    an unanswered today does not break anything yet, since the day is not over.
    The streak is 0 once the member has missed the most recent scheduled day
    before today.

    Pure, so the counting can be tested with plain dates.
    """
    answered = {d for d in (_as_date(v) for v in standup_dates or ()) if d is not None}
    if not answered:
        return 0
    weekdays = set(working_days or ()) or set(_WORKING_WEEK)
    days_off = {d for d in (_as_date(v) for v in holidays or ()) if d is not None}
    earliest = min(answered)
    streak = 0
    day = today
    while day >= earliest:
        scheduled = day.weekday() in weekdays and day not in days_off
        if scheduled:
            if day in answered:
                streak += 1
            elif day != today:
                break
        day -= timedelta(days=1)
    return streak


def get_standup_streak(team_id: str, user_id: str) -> int:
    """Return the member's current streak of answered scheduled days.

    The old SQL subtracted a descending ROW_NUMBER from each date, which puts
    consecutive days into different groups, so every streak read 1. It also
    counted calendar days, so a weekend would have broken it anyway. The
    counting now happens in streak_from_dates against the member's own
    schedule days and the workspace's holidays.
    """
    sql = """
        SELECT DISTINCT standup_date
        FROM standups
        WHERE team_id = %s AND user_id = %s AND standup_date >= CURRENT_DATE - %s * INTERVAL '1 day'
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, STREAK_LOOKBACK_DAYS))
            dates = [row[0] for row in cur.fetchall()]
    if not dates:
        return 0

    # The member's week is the union of the standups they are on. A schedule
    # with no participant list asks everyone.
    mine = [
        s
        for s in get_standup_schedules(team_id)
        if s.get("active", True) and (not s.get("participants") or user_id in (s.get("participants") or []))
    ]
    weekdays: set[int] = set()
    for schedule in mine:
        weekdays |= parse_schedule_days(schedule.get("schedule_days"))
    tz_name = next((s.get("schedule_tz") for s in mine if s.get("schedule_tz")), None)
    if not tz_name:
        tz_name = (get_workspace_config(team_id) or {}).get("schedule_tz")
    try:
        holidays = [h["date"] for h in list_holidays(team_id)]
    except Exception as exc:  # noqa: BLE001 - a missing calendar must not hide the streak
        logger.debug("No holiday list for %s: %s", team_id, exc)
        holidays = []
    return streak_from_dates(dates, weekdays, local_today(tz_name or "UTC"), holidays)


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
            return ZoneInfo(canonical_tz(name))
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


def _local_creation_date(schedule: dict, zone) -> date | None:
    """Return the date a schedule was created on, in its own timezone.

    `created_at` is a TIMESTAMPTZ, so psycopg2 hands back an aware datetime. A
    naive one (a test fixture, an old export) is read as UTC. A bare date or an
    ISO string is accepted too. None when the row has no usable value, which
    leaves the schedule counted across the whole window as before.
    """
    value = schedule.get("created_at")
    if isinstance(value, str) and value.strip():
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return _as_date(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(zone).date()
    if isinstance(value, date):
        return value
    return None


def _occurrence_dates(
    schedule: dict, days: int, now: datetime, end: date | None = None, holidays: frozenset[date] = frozenset()
) -> list[date]:
    """Return the dates a schedule fired on in the last N days, in its own timezone.

    With `end` the window is the N days ending on that date instead of today,
    which is how a report for a past range is judged; a day after the
    schedule's own today is never counted, because it has not happened yet.
    Company holidays are dropped: the standup does not run on them, so they
    are not a missed day.

    Days before the schedule existed are dropped. Counting them asked a
    standup created a few minutes ago for two weeks of answers nobody was ever
    sent, and reported it as "5%, needs a look" on its first afternoon. The day
    it was created on still counts, so a standup set up in the morning and run
    that day is judged on that day. Per-participant join dates are not
    recorded (`participants` is a plain array), so someone added to an older
    standup is still expected from the schedule's creation onwards.
    """
    zone = _resolve_zone(schedule.get("schedule_tz"))
    local_today = now.astimezone(zone).date()
    first = (end or local_today) - timedelta(days=days - 1)
    last = local_today if end is None else min(end, local_today)
    weekdays = parse_schedule_days(schedule.get("schedule_days"))
    window = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    created = _local_creation_date(schedule, zone)
    return [
        day
        for day in window
        if day.weekday() in weekdays and day not in holidays and (created is None or day >= created)
    ]


def _workspace_local_day(schedules: list[dict] | None, now: datetime) -> date:
    """The day the workspace is on: the first standup's timezone, else UTC.

    The same pick as insights.today.workspace_today, so the analytics grid and
    the Today view end on the same date. Using the UTC date put a Sydney team's
    whole morning in yesterday's column.
    """
    zone_name = next((s.get("schedule_tz") for s in schedules or [] if s.get("schedule_tz")), None)
    return now.astimezone(_resolve_zone(zone_name)).date()


# Longest window any participation or report query covers. compute_participation
# expands every schedule day by day, so an unbounded window (a date_from in year
# 2 is about 740,000 days) runs the pod out of memory. Matches DaysQuery.
MAX_WINDOW_DAYS = 365


def compute_participation(
    schedules: list[dict] | None,
    members: list[dict] | None,
    submissions: list[dict] | None,
    days: int = 7,
    now: datetime | None = None,
    end: date | None = None,
    start: date | None = None,
    holidays=None,
) -> dict:
    """Compute workspace, per-schedule and per-member participation from raw rows.

    The window is the `days` days ending on `end`, or on the workspace's local
    today when no end is given. A `start` overrides `days`, so a report for
    from..to covers exactly that range. `holidays` are company days off, which
    are not counted as expected.

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

    Submissions written since migration 026 name the schedule they belong to and
    are credited to it exactly. Older rows have no schedule id, so for those the
    per-schedule split still falls back to handing credit out in schedule_time
    order. That keeps the per-schedule numbers summing to the workspace
    numerator either way; only the split between a member's two standups on one
    day is a guess, and only for rows written before 026.

    Kept free of any database access so the arithmetic can be tested against
    hand-computed numbers. `schedules` are `standup_schedules` rows, `members`
    are `members` rows and `submissions` are `standups` rows covering at least
    the window (a day of slack either side is fine, it is filtered here).
    """
    now = now or _utc_now()
    active_schedules = sorted(
        (s for s in (schedules or []) if s.get("active", True)),
        key=lambda s: (_schedule_minutes(s), int(s.get("id") or 0)),
    )
    window_end = end or _workspace_local_day([s for s in (schedules or []) if s.get("active", True)], now)
    if start is not None:
        days = (window_end - start).days + 1
    days = min(max(1, int(days or 1)), MAX_WINDOW_DAYS)
    days_off = frozenset(d for d in (_as_date(h) for h in holidays or ()) if d is not None)

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
    # (member, day) -> the schedules the submissions actually name. Rows written
    # before standups carried a schedule id have none, so both paths are needed.
    attributed: dict[tuple[str, date], set[int]] = {}
    responses: dict[str, int] = {}
    blockers: dict[str, int] = {}
    # (member, day) pairs where a submission actually reported a blocker, so the
    # dashboard can mark the day rather than only the member.
    blocked_days: set[tuple[str, date]] = set()
    last_standup: dict[str, Any] = {}
    window_start = window_end - timedelta(days=days - 1)
    for row in submissions or []:
        user_id = row.get("user_id")
        day = _as_date(row.get("standup_date"))
        if not user_id or day is None:
            continue
        per_day[(user_id, day)] = per_day.get((user_id, day), 0) + 1
        named = row.get("schedule_id")
        if named:
            attributed.setdefault((user_id, day), set()).add(int(named))
        if window_start <= day <= window_end:
            responses[user_id] = responses.get(user_id, 0) + 1
            if row.get("has_blockers"):
                blockers[user_id] = blockers.get(user_id, 0) + 1
                blocked_days.add((user_id, day))
        submitted_at = row.get("submitted_at")
        if submitted_at is not None:
            previous = last_standup.get(user_id)
            try:
                if previous is None or submitted_at > previous:
                    last_standup[user_id] = submitted_at
            except TypeError:
                last_standup.setdefault(user_id, submitted_at)

    schedule_rows: dict[int, dict] = {}
    enrolled: set[str] = set()
    # (member, day) -> the schedule ids that asked them for a standup that day,
    # in schedule_time order.
    occurrences: dict[tuple[str, date], list[int]] = {}
    # Which schedules name each person, independent of whether any of those
    # schedules actually fired inside the window. Occurrences cannot answer
    # this: someone on leave, or on a weekly standup that did not come round
    # this week, has no occurrences at all and would look like a member of no
    # standup, which in turn hid them from the dashboard's per-standup filter.
    membership: dict[str, set[int]] = {}
    for schedule in active_schedules:
        schedule_id = int(schedule.get("id") or 0)
        dates = _occurrence_dates(schedule, days, now, end=end, holidays=days_off)
        counted: list[str] = []
        seen: set[str] = set()
        for user_id in schedule.get("participants") or []:
            if not user_id or user_id in seen:
                continue
            seen.add(user_id)
            enrolled.add(user_id)
            membership.setdefault(user_id, set()).add(schedule_id)
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
    # (schedule, day) counts, so each standup gets a trend line rather than a
    # single number for the whole window.
    per_schedule_day: dict[tuple[int, date], int] = {}
    expected_per_schedule_day: dict[tuple[int, date], int] = {}
    for (user_id, day), schedule_ids in occurrences.items():
        expected_here = len(schedule_ids)
        completed_here = min(per_day.get((user_id, day), 0), expected_here)
        expected_total += expected_here
        completed_total += completed_here
        stats = per_member.setdefault(user_id, {"expected": 0, "completed": 0, "schedules": set()})
        stats["expected"] += expected_here
        stats["completed"] += completed_here
        stats["schedules"].update(schedule_ids)
        # Credit the schedules the submissions name. Anything left over is a
        # submission from before standups recorded one, so it falls back to
        # handing out credit in schedule_time order, which is a guess but keeps
        # the per-schedule figures summing to the workspace total.
        named = attributed.get((user_id, day), set()) & set(schedule_ids)
        for schedule_id in named:
            schedule_rows[schedule_id]["completed"] += 1
            per_schedule_day[(schedule_id, day)] = per_schedule_day.get((schedule_id, day), 0) + 1
        remaining = completed_here - len(named)
        if remaining > 0:
            for schedule_id in [s for s in schedule_ids if s not in named][:remaining]:
                schedule_rows[schedule_id]["completed"] += 1
                per_schedule_day[(schedule_id, day)] = per_schedule_day.get((schedule_id, day), 0) + 1
        for schedule_id in schedule_ids:
            expected_per_schedule_day[(schedule_id, day)] = expected_per_schedule_day.get((schedule_id, day), 0) + 1

    # Oldest first, so a grid reads left to right like a calendar.
    window_days = [window_start + timedelta(days=offset) for offset in range(days)]

    member_rows = []
    for user_id, member in known.items():
        if not member["active"]:
            continue
        stats = per_member.get(user_id) or {"expected": 0, "completed": 0, "schedules": set()}
        member_schedules = membership.get(user_id) or set()
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
                # One entry per day in the window, so the dashboard can draw a
                # member-by-day grid instead of collapsing a week into a single
                # ratio. A day nobody asked about is expected 0, which reads as
                # "not scheduled" rather than "missed".
                "days": [
                    {
                        "date": day.isoformat(),
                        "expected": len(occurrences.get((user_id, day), [])),
                        "completed": min(per_day.get((user_id, day), 0), len(occurrences.get((user_id, day), []))),
                        "blocked": (user_id, day) in blocked_days,
                    }
                    for day in window_days
                ],
                # Which standups this person is on. Names for display, ids so
                # the dashboard's "filter by standup" control has something to
                # compare against: it was matching a numeric id against this
                # list of names, missing every time, and emptying the table for
                # every standup you picked.
                "schedules": [schedule_rows[sid]["name"] for sid in sorted(member_schedules) if sid in schedule_rows],
                "schedule_ids": sorted(sid for sid in member_schedules if sid in schedule_rows),
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

    for schedule_id, row in schedule_rows.items():
        row["missed"] = row["expected"] - row["completed"]
        row["completion_rate"] = _percentage(row["completed"], row["expected"])
        # Completion rate per day. Days the schedule did not run are None rather
        # than 0, so a weekly standup does not draw as five days of failure.
        row["series"] = [
            _percentage(
                per_schedule_day.get((schedule_id, day), 0),
                expected_per_schedule_day.get((schedule_id, day), 0),
            )
            if expected_per_schedule_day.get((schedule_id, day))
            else None
            for day in window_days
        ]

    return {
        "days": days,
        "window_days": [day.isoformat() for day in window_days],
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


def _fetch_participation_inputs(team_id: str, lower: date, upper: date) -> tuple[list[dict], list[dict], list[dict]]:
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
        SELECT id, name, schedule_time, schedule_tz, schedule_days, participants, active, created_at
        FROM standup_schedules
        WHERE team_id = %s AND active = TRUE
        ORDER BY schedule_time, id
    """
    sql_members = """
        SELECT user_id, real_name, active, COALESCE(on_vacation, FALSE) AS on_vacation
        FROM members
        WHERE team_id = %s AND active = TRUE
    """
    # The bounds carry a day of slack either side, for schedules whose local
    # date differs from the one the window was computed in.
    sql_submissions = """
        SELECT user_id, standup_date, has_blockers, submitted_at, schedule_id
        FROM standups
        WHERE team_id = %s AND standup_date >= %s AND standup_date <= %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql_schedules, (team_id,))
            schedules = [dict(r) for r in cur.fetchall()]
            cur.execute(sql_members, (team_id,))
            members = [dict(r) for r in cur.fetchall()]
            cur.execute(sql_submissions, (team_id, lower, upper))
            submissions = [dict(r) for r in cur.fetchall()]
    return schedules, members, submissions


def get_participation_overview(team_id: str, days: int = 7, end: date | None = None, start: date | None = None) -> dict:
    """Return workspace, per-schedule and per-member participation.

    The last N days by default. With `start` and/or `end` the window is that
    date range instead, which is what a report for a chosen period needs.
    """
    days = min(max(1, int(days or 1)), MAX_WINDOW_DAYS)
    anchor = end or _utc_now().date()
    upper = anchor + timedelta(days=1)
    lower = (start or anchor - timedelta(days=days)) - timedelta(days=1)
    lower = max(lower, upper - timedelta(days=MAX_WINDOW_DAYS + 2))
    schedules, members, submissions = _fetch_participation_inputs(team_id, lower, upper)
    return compute_participation(
        schedules,
        members,
        submissions,
        days=days,
        end=end,
        start=start,
        holidays=_holiday_dates(team_id),
    )


def _holiday_dates(team_id: str) -> list[date]:
    """The workspace's company holidays, or none when they cannot be read.

    A calendar that fails to load must not break the participation figures, it
    only means holidays count as ordinary days, as they did before.
    """
    try:
        return [h["date"] for h in list_holidays(team_id)]
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.debug("No holiday list for %s: %s", team_id, exc)
        return []


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
        "digest_email",
        "digest_enabled",
        "nudge_missing",
        "nudge_minutes_before",
        "awaiting_invite_by",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if "questions" in fields and isinstance(fields["questions"], list):
        fields["questions"] = json.dumps(fields["questions"])
    if "schedule_tz" in fields:
        fields["schedule_tz"] = canonical_tz(fields["schedule_tz"])
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


def waiting_standups(team_id: str, channel_id: str) -> list[dict]:
    """Standups saved from the quick start that wait for the bot to join this channel."""
    sql = """
        SELECT id, awaiting_invite_by, schedule_time FROM standup_schedules
        WHERE team_id = %s AND channel_id = %s AND awaiting_invite_by IS NOT NULL
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, channel_id))
            return [dict(r) for r in cur.fetchall()]


def activate_waiting_standup(schedule_id: int) -> bool:
    """Switch a waiting standup on. True only for the call that did it, so the
    creator is told once. updated_at moves, so the scheduler's change poll
    registers the job."""
    sql = """
        UPDATE standup_schedules SET active = TRUE, awaiting_invite_by = NULL, updated_at = NOW()
        WHERE id = %s AND awaiting_invite_by IS NOT NULL RETURNING 1
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (schedule_id,))
            return cur.fetchone() is not None


def upsert_daily_thread(
    team_id: str, channel_id: str, thread_date: str, parent_ts: str, schedule_id: int = 0
) -> str | None:
    """Persist the parent message ts for today's standup thread; return the stored one.

    Scoped by schedule_id so workspaces running multiple standups on the same
    channel (morning + evening) get a distinct thread parent per schedule.

    Two people finishing at the same moment both post a header. Only the first
    insert wins, so this returns whichever ts is actually stored: the caller's
    own when it won, the other one when it lost. The no-op DO UPDATE is there
    because DO NOTHING returns no row on conflict. None means the write failed.
    """
    sql = """
        INSERT INTO daily_standup_threads (team_id, channel_id, thread_date, schedule_id, parent_ts)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (team_id, channel_id, thread_date, schedule_id)
        DO UPDATE SET parent_ts = daily_standup_threads.parent_ts
        RETURNING parent_ts
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, (team_id, channel_id, thread_date, int(schedule_id or 0), parent_ts))
                row = cur.fetchone()
            except Exception as exc:
                logger.warning("Could not store daily thread for %s/%s: %s", team_id, channel_id, exc)
                return None
    return row[0] if row else None


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


def schedules_change_marker() -> tuple:
    """A cheap fingerprint of every standup schedule, for the change poll.

    Creating, editing, pausing or enabling a schedule moves the latest
    timestamp; deleting one changes the count. One indexed aggregate over a
    small table, so the scheduler can afford to ask every few seconds.
    """
    sql = "SELECT COUNT(*), MAX(GREATEST(COALESCE(updated_at, created_at), created_at)) FROM standup_schedules"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
    return tuple(row) if row else ()


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
            tz = pytz.timezone(canonical_tz(tz_name))
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
            tz = pytz.timezone(canonical_tz(tz_name))
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
        "digest_email",
        "digest_enabled",
        "nudge_missing",
        "nudge_minutes_before",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_standup_schedule(team_id, schedule_id)
    if "questions" in fields and isinstance(fields["questions"], list):
        fields["questions"] = json.dumps(fields["questions"])
    if "schedule_tz" in fields:
        fields["schedule_tz"] = canonical_tz(fields["schedule_tz"])
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


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------


def get_member_role(team_id: str, user_id: str) -> str:
    """Return 'admin' or 'member' for a user. Defaults to 'member' if not found.

    Whoever installed the app is always an admin, whatever the members row
    says. Without that a workspace can become permanently unmanageable: role
    changes require admin, so the moment the last admin is deactivated nobody
    can ever grant it again, and every admin-only route is closed for good.
    It is not hypothetical, most workspaces have exactly one admin.

    The installer is the safe choice for this: they hold the Slack side of the
    relationship already, and it grants nothing to anyone else.

    Only while they are still here, though. A person deactivated in Slack is
    a member, whatever their row or the installation says, so leaving the
    company ends their admin rights with everything else.
    """
    sql = "SELECT role, active FROM members WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
            if row and row[1] is False:
                return "member"
            role = (row[0] if row else None) or "member"
            if role == "admin":
                return role
            cur.execute("SELECT installed_by_user_id FROM installations WHERE team_id = %s", (team_id,))
            inst = cur.fetchone()
    if inst and inst[0] and user_id and inst[0] == user_id:
        return "admin"
    return role


def session_member_active(team_id: str, user_id: str) -> bool:
    """Whether a dashboard session for this person should still work.

    The installation has to be active and the person must not have been
    deactivated. A person with no members row yet (the roster sync has not
    reached them) is let through: departures always leave a row behind,
    because rows are never deleted, only flagged.
    """
    sql = """
        SELECT COALESCE(i.active, TRUE), m.active
        FROM installations i
        LEFT JOIN members m ON m.team_id = i.team_id AND m.user_id = %s
        WHERE i.team_id = %s
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, team_id))
            row = cur.fetchone()
    return bool(row and row[0] and row[1] is not False)


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


def generate_mcp_key(team_id: str, name: str = "Default", created_by: str | None = None) -> str:
    """Generate a new MCP API key, store its hash, return the full key.

    created_by ties the key to the admin who made it, so it stops working
    when they leave or stop being an admin (see verify_mcp_key).
    """
    key = "mrn_" + _secrets.token_urlsafe(32)
    key_hash = _hashlib.sha256(key.encode()).hexdigest()
    key_prefix = key[:12]
    sql = """
        INSERT INTO mcp_api_keys (team_id, key_hash, key_prefix, name, created_by)
        VALUES (%s, %s, %s, %s, %s)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, key_hash, key_prefix, name, created_by))
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
    """Verify an API key, update last_used_at, return team_id or None.

    A key is only as good as the admin who made it: once they are deactivated
    or no longer a workspace admin, it is treated as revoked. Keys from before
    the creator was recorded have none and keep working until revoked by hand.
    Nothing is written for a key that fails, so guessing costs one read.
    """
    if not key:
        return None
    key_hash = _hashlib.sha256(key.encode()).hexdigest()
    sql = """
        SELECT k.id, k.team_id, k.created_by
        FROM mcp_api_keys k
        JOIN installations i ON i.team_id = k.team_id
        WHERE k.key_hash = %s AND k.active = TRUE AND COALESCE(i.active, TRUE)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (key_hash,))
            row = cur.fetchone()
    if not row:
        return None
    key_id, team_id, created_by = row
    if created_by and get_member_role(team_id, created_by) != "admin":
        logger.info("MCP key %s refused: its creator is no longer an active admin", key_id)
        return None
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE mcp_api_keys SET last_used_at = NOW() WHERE id = %s", (key_id,))
    return team_id


# ── Removing a workspace: history first, then the data ──────────────────────

# Every table that holds a person or something they wrote, for one workspace,
# in the order the purge deletes them. Children come before parents where the
# foreign key is not ON DELETE CASCADE (standups before standup_schedules,
# rematch requests before matches). connect_pair_history has no team_id, only
# pairs of user IDs keyed by programme, so it is reached through its programme.
#
# A test reads every migration and fails when a table with a team_id is on
# neither this list nor KEPT_TABLES, so a new table has to be decided on.
_PURGE_STEPS: tuple[tuple[str, str], ...] = (
    ("webhook_deliveries", "team_id = %s"),
    ("webhooks", "team_id = %s"),
    ("workflow_rules", "team_id = %s"),
    ("connect_slot_votes", "team_id = %s"),
    ("connect_rematch_requests", "team_id = %s"),
    ("connect_followups", "team_id = %s"),
    ("connect_matches", "team_id = %s"),
    ("connect_optouts", "team_id = %s"),
    ("connect_pair_history", "program_id IN (SELECT id FROM connect_programs WHERE team_id = %s)"),
    ("connect_rounds", "team_id = %s"),
    ("connect_programs", "team_id = %s"),
    ("connect_zoom_links", "team_id = %s"),
    ("celebration_posts", "team_id = %s"),
    ("celebration_settings", "team_id = %s"),
    ("kudos", "team_id = %s"),
    ("kudos_config", "team_id = %s"),
    ("daily_standup_threads", "team_id = %s"),
    ("user_away", "team_id = %s"),
    ("user_skip", "team_id = %s"),
    ("standups", "team_id = %s"),
    ("standup_schedules", "team_id = %s"),
    ("member_profiles", "team_id = %s"),
    ("module_admins", "team_id = %s"),
    ("mcp_api_keys", "team_id = %s"),
    ("members", "team_id = %s"),
    ("workspace_holidays", "team_id = %s"),
    ("workspace_modules", "team_id = %s"),
    ("workspace_config", "team_id = %s"),
    ("setup_email_consents", "team_id = %s"),
    ("install_emails", "team_id = %s"),
)
PURGED_TABLES: tuple[str, ...] = tuple(table for table, _ in _PURGE_STEPS)

# Tables with a team_id that the purge keeps, and why:
#   installations      stripped to team_id, team_name, dates and the reason,
#                      with every token and the installer's user ID cleared
#   workspace_history  counts and dates only, the point of keeping anything
#   email_consents     a person's own opt-in to product email, keyed by their
#                      address and kept as the proof the law asks for. Only
#                      the link to the workspace is cleared.
KEPT_TABLES: tuple[str, ...] = ("installations", "workspace_history", "email_consents")

# Written with the same expressions whether it runs for one workspace or all
# of them. Counts and dates only: no user IDs, names, addresses or text.
# A purged workspace is skipped, because its counts would all read zero.
_HISTORY_SQL = """
    INSERT INTO workspace_history (
        team_id, team_name, installed_at, removed_at, removal_reason, install_source,
        members_count, standups_created, standup_answers, first_answer_at,
        last_activity_at, kudos_count, coffee_rounds, modules_used,
        days_installed, updated_at)
    SELECT i.team_id, i.team_name, i.installed_at,
           CASE WHEN i.active THEN NULL ELSE i.deactivated_at END,
           CASE WHEN i.active THEN NULL ELSE i.deactivated_reason END,
           i.install_source,
           (SELECT COUNT(*) FROM members m WHERE m.team_id = i.team_id AND m.active),
           sc.n, st.n, st.first_at,
           GREATEST(st.last_at, k.last_at, c.last_at),
           k.n, c.n,
           ARRAY_REMOVE(ARRAY[
               CASE WHEN sc.n > 0 OR st.n > 0 THEN 'standup' END,
               CASE WHEN k.n > 0 THEN 'kudos' END,
               CASE WHEN c.n > 0 THEN 'connect' END,
               CASE WHEN EXISTS (SELECT 1 FROM celebration_posts p WHERE p.team_id = i.team_id)
                    THEN 'celebrations' END,
               CASE WHEN EXISTS (SELECT 1 FROM mcp_api_keys a WHERE a.team_id = i.team_id) THEN 'mcp' END
           ]::text[], NULL),
           GREATEST(0, COALESCE(CASE WHEN i.active THEN NULL ELSE i.deactivated_at END, NOW())::date
                       - COALESCE(i.installed_at, NOW())::date),
           NOW()
    FROM installations i
    CROSS JOIN LATERAL (SELECT COUNT(*) AS n FROM standup_schedules WHERE team_id = i.team_id) sc
    CROSS JOIN LATERAL (
        SELECT COUNT(*) AS n, MIN(submitted_at) AS first_at, MAX(submitted_at) AS last_at
        FROM standups WHERE team_id = i.team_id) st
    CROSS JOIN LATERAL (
        SELECT COUNT(*) AS n, MAX(created_at) AS last_at FROM kudos WHERE team_id = i.team_id) k
    CROSS JOIN LATERAL (
        SELECT COUNT(*) AS n, MAX(delivered_at) AS last_at
        FROM connect_matches WHERE team_id = i.team_id AND delivered_at IS NOT NULL) c
    WHERE {where}
    ON CONFLICT (team_id) DO UPDATE SET
        team_name = EXCLUDED.team_name,
        installed_at = EXCLUDED.installed_at,
        removed_at = EXCLUDED.removed_at,
        removal_reason = EXCLUDED.removal_reason,
        install_source = COALESCE(workspace_history.install_source, EXCLUDED.install_source),
        members_count = EXCLUDED.members_count,
        standups_created = EXCLUDED.standups_created,
        standup_answers = EXCLUDED.standup_answers,
        first_answer_at = EXCLUDED.first_answer_at,
        last_activity_at = EXCLUDED.last_activity_at,
        kudos_count = EXCLUDED.kudos_count,
        coffee_rounds = EXCLUDED.coffee_rounds,
        modules_used = EXCLUDED.modules_used,
        days_installed = EXCLUDED.days_installed,
        updated_at = NOW()
"""


def record_workspace_history(team_id: str) -> bool:
    """Refresh one workspace's history row from the live tables.

    Returns False when there is nothing to record: no such installation, or
    one already purged, whose last counts must not be overwritten with zeros.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_HISTORY_SQL.format(where="i.team_id = %s AND i.purged_at IS NULL"), (team_id,))
            return (cur.rowcount or 0) > 0


def record_all_workspace_history() -> int:
    """Refresh history for every installation, live or retired. Returns how many.

    Nightly, so the row is current whenever a workspace goes, and the first
    run fills it in for every workspace installed before the table existed.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_HISTORY_SQL.format(where="i.purged_at IS NULL"))
            return cur.rowcount or 0


def _existing_tables(cur) -> set[str]:
    """The purge tables this database has. A module's tables may be absent."""
    cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = ANY(%s)",
        (list(PURGED_TABLES),),
    )
    return {row[0] for row in cur.fetchall()}


def workspace_data_counts(team_id: str) -> dict[str, int]:
    """Rows the purge would delete, per table. Reads only; for the dry run."""
    counts: dict[str, int] = {}
    with db_conn() as conn:
        with conn.cursor() as cur:
            present = _existing_tables(cur)
            for table, where in _PURGE_STEPS:
                if table not in present:
                    continue
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", (team_id,))
                row = cur.fetchone()
                counts[table] = int(row[0]) if row else 0
    return counts


def purge_workspace(
    team_id: str,
    reason: str | None = None,
    expect_deactivated_at: datetime | None = None,
) -> dict[str, int] | None:
    """Delete everything a workspace holds about people, keeping its history.

    One transaction: record history, delete every table in PURGED_TABLES for
    this team, detach product email consent, and strip the installation row
    to team_id, team_name, dates and the reason. Returns rows deleted per
    table, or None when nothing was done.

    Idempotent: a workspace already purged is left alone. The sweep passes
    expect_deactivated_at, the retirement time it judged the grace period by,
    and the purge is refused if the row has since come back to life or been
    retired again. The row is locked while that is checked, so a reinstall
    cannot slip in between. Slack's own uninstall events pass neither and
    purge an active row straight away, as the listing promises.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT active, purged_at, deactivated_at FROM installations WHERE team_id = %s FOR UPDATE",
                (team_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            active, purged_at, deactivated_at = row
            if purged_at is not None:
                return None
            if expect_deactivated_at is not None and (active or deactivated_at != expect_deactivated_at):
                logger.info("Not purging %s: it came back or was retired again since the sweep looked", team_id)
                return None

            cur.execute(
                """
                UPDATE installations
                SET active = FALSE,
                    deactivated_at = COALESCE(deactivated_at, NOW()),
                    deactivated_reason = COALESCE(%s, deactivated_reason)
                WHERE team_id = %s
                """,
                (reason[:200] if reason else None, team_id),
            )
            cur.execute(_HISTORY_SQL.format(where="i.team_id = %s AND i.purged_at IS NULL"), (team_id,))

            present = _existing_tables(cur)
            deleted: dict[str, int] = {}
            for table, where in _PURGE_STEPS:
                if table not in present:
                    continue
                cur.execute(f"DELETE FROM {table} WHERE {where}", (team_id,))
                deleted[table] = cur.rowcount or 0

            cur.execute("UPDATE email_consents SET team_id = NULL WHERE team_id = %s", (team_id,))
            cur.execute(
                """
                UPDATE installations
                SET bot_token = '', bot_user_id = '', bot_refresh_token = NULL,
                    bot_token_expires_at = NULL, installed_by_user_id = NULL,
                    granted_scopes = NULL, purged_at = NOW(), updated_at = NOW()
                WHERE team_id = %s
                """,
                (team_id,),
            )
            cur.execute("UPDATE workspace_history SET purged_at = NOW() WHERE team_id = %s", (team_id,))
    logger.info("Purged workspace %s: %d rows deleted", team_id, sum(deleted.values()))
    return deleted


def purge_candidates() -> list[dict]:
    """Retired installations whose data has not been purged yet."""
    sql = """
        SELECT team_id, team_name, deactivated_at, deactivated_reason
        FROM installations
        WHERE NOT active AND purged_at IS NULL AND deactivated_at IS NOT NULL
        ORDER BY deactivated_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def set_install_source(team_id: str, source: str) -> None:
    """Remember where the first install of a workspace came from.

    Only fills an empty source, so a reinstall or a dashboard sign-in through
    a tagged link never rewrites where the workspace first came from.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE installations SET install_source = %s WHERE team_id = %s AND install_source IS NULL",
                (source, team_id),
            )


def usage_report_rows() -> list[dict]:
    """One row per workspace for the Monday usage report: counts, never people.

    Live installations, and those removed in the last week. A removed
    workspace whose data is purged keeps a bare installations row, and its
    history row fills in what the purge cleared; a workspace with only a
    history row left is added from workspace_history. people_7d counts
    distinct people who answered a standup or gave kudos in the last week.
    """
    sql = """
        SELECT i.team_id,
               COALESCE(i.team_name, h.team_name) AS team_name,
               i.active,
               i.installed_at,
               CASE WHEN i.active THEN NULL ELSE COALESCE(i.deactivated_at, h.removed_at) END AS removed_at,
               COALESCE(i.install_source, h.install_source) AS install_source,
               p.n AS people_7d,
               st.n AS answers_7d,
               k.n AS kudos_7d,
               EXISTS (SELECT 1 FROM standup_schedules s WHERE s.team_id = i.team_id) AS has_standup,
               i.installed_at > NOW() - INTERVAL '7 days' AS installed_this_week,
               (NOT i.active AND COALESCE(i.deactivated_at, h.removed_at) > NOW() - INTERVAL '7 days')
                   AS removed_this_week,
               COALESCE(st.first_at > NOW() - INTERVAL '7 days', FALSE) AS activated_this_week,
               EXISTS (SELECT 1 FROM install_emails e WHERE e.team_id = i.team_id AND e.kind = 'nudge:day2')
                   AS nudged
        FROM installations i
        LEFT JOIN workspace_history h ON h.team_id = i.team_id
        CROSS JOIN LATERAL (
            SELECT COUNT(*) FILTER (WHERE submitted_at > NOW() - INTERVAL '7 days') AS n,
                   MIN(submitted_at) AS first_at
            FROM standups WHERE team_id = i.team_id) st
        CROSS JOIN LATERAL (
            SELECT COUNT(*) AS n FROM kudos
            WHERE team_id = i.team_id AND created_at > NOW() - INTERVAL '7 days') k
        CROSS JOIN LATERAL (
            SELECT COUNT(*) AS n FROM (
                SELECT user_id FROM standups
                WHERE team_id = i.team_id AND submitted_at > NOW() - INTERVAL '7 days'
                UNION
                SELECT from_user FROM kudos
                WHERE team_id = i.team_id AND created_at > NOW() - INTERVAL '7 days') u) p
        WHERE i.active OR COALESCE(i.deactivated_at, h.removed_at) > NOW() - INTERVAL '7 days'
        UNION ALL
        SELECT h.team_id, h.team_name, FALSE, h.installed_at, h.removed_at, h.install_source,
               0, 0, 0, FALSE, h.installed_at > NOW() - INTERVAL '7 days', TRUE, FALSE, FALSE
        FROM workspace_history h
        WHERE h.removed_at > NOW() - INTERVAL '7 days'
          AND NOT EXISTS (SELECT 1 FROM installations i WHERE i.team_id = h.team_id)
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def parse_scope_field(scope: str | None) -> list[str]:
    """Split the comma-separated `scope` field from oauth.v2.access."""
    if not scope:
        return []
    return [s.strip() for s in scope.split(",") if s.strip()]


def granted_scopes(team_id: str) -> set[str]:
    """Scopes Slack granted this workspace, from the OAuth response.

    Returns an empty set when the column is NULL, which means the workspace
    installed before this was recorded. Modules that declare required_scopes
    stay off for those workspaces until an admin re-authorises, which is the
    safe direction to fail in.
    """
    sql = "SELECT granted_scopes FROM installations WHERE team_id = %s"
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (team_id,))
                row = cur.fetchone()
    except Exception as exc:
        logger.warning("granted_scopes lookup failed for %s: %s", team_id, exc)
        return set()
    return set(row[0]) if row and row[0] else set()


def has_scopes(team_id: str, required) -> bool:
    """True when the workspace holds every scope in `required`."""
    required = list(required)
    if not required:
        return True
    return set(required).issubset(granted_scopes(team_id))


def _fetch_module_rows(team_id: str):
    sql = "SELECT module, enabled FROM workspace_modules WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            return cur.fetchall()


def module_settings(team_id: str) -> dict[str, bool]:
    """Explicit per-workspace module toggles.

    An absent key means the module falls back to its own default_enabled, so
    this only ever reports choices an admin actually made. A database error
    degrades to "no explicit choices" rather than taking down a DM.
    """
    try:
        return {module: enabled for module, enabled in _fetch_module_rows(team_id)}
    except Exception as exc:
        logger.warning("module_settings lookup failed for %s: %s", team_id, exc)
        return {}


def set_module_enabled(team_id: str, module: str, enabled: bool) -> None:
    """Record an explicit admin choice for one module."""
    sql = """
        INSERT INTO workspace_modules (team_id, module, enabled, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (team_id, module) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            updated_at = NOW()
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, module, enabled))


def count_admins(team_id: str) -> int:
    """Active admins in a workspace, for refusing to demote the last one."""
    sql = "SELECT COUNT(*) FROM members WHERE team_id = %s AND role = 'admin' AND active"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            return int(cur.fetchone()[0])


# ── Per-feature administrators ──────────────────────────────────────────────


def module_admin_grants(team_id: str, user_id: str) -> set[str]:
    """Which features this person administers, ignoring their workspace role."""
    sql = "SELECT module FROM module_admins WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            return {r[0] for r in cur.fetchall()}


def team_module_admins(team_id: str) -> dict:
    """`{user_id: {module, ...}}` for everyone with a grant in this workspace."""
    out: dict = {}
    sql = "SELECT user_id, module FROM module_admins WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            for user_id, module in cur.fetchall():
                out.setdefault(user_id, set()).add(module)
    return out


def grant_module_admin(team_id: str, user_id: str, module: str, granted_by: str = "") -> None:
    sql = """
        INSERT INTO module_admins (team_id, user_id, module, granted_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (team_id, user_id, module) DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, module, granted_by or None))


def revoke_module_admin(team_id: str, user_id: str, module: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM module_admins WHERE team_id = %s AND user_id = %s AND module = %s",
                (team_id, user_id, module),
            )


def can_administer(team_id: str, user_id: str, module: str | None = None) -> bool:
    """Whether this person may change `module`, or anything when it is None.

    A workspace admin always may. Otherwise they need a grant for that exact
    feature, and a route that names no feature stays workspace-admin only,
    because the things that name none are the workspace-wide ones: roles,
    invitations, API keys, the public feed.
    """
    if get_member_role(team_id, user_id) == "admin":
        return True
    if not module:
        return False
    return module in module_admin_grants(team_id, user_id)


# ── Email suppression and install follow-ups ────────────────────────────────


def email_is_suppressed(email: str) -> bool:
    """Whether this address has asked not to be emailed."""
    if not email:
        return True
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM email_suppressions WHERE email = %s", (email.lower(),))
            return cur.fetchone() is not None


def suppress_email(email: str, reason: str = "unsubscribed") -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_suppressions (email, reason) VALUES (%s, %s)
                ON CONFLICT (email) DO UPDATE SET reason = EXCLUDED.reason
                """,
                (email.lower(), reason),
            )


def install_email_sent(team_id: str, kind: str) -> bool:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM install_emails WHERE team_id = %s AND kind = %s", (team_id, kind))
            return cur.fetchone() is not None


def record_install_email(team_id: str, kind: str, to_email: str = "") -> bool:
    """Remember that this workspace has had this message, so it cannot go twice.

    True when this call wrote the record, False when it was already there, so
    a caller that records before sending can tell whether it should send.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO install_emails (team_id, kind, to_email) VALUES (%s, %s, %s)
                ON CONFLICT (team_id, kind) DO NOTHING RETURNING 1
                """,
                (team_id, kind, to_email or None),
            )
            return cur.fetchone() is not None


def workspaces_without_standup(hours: int) -> list[dict]:
    """Live installs older than `hours` and under two weeks old, with no standup
    at all (a quick start one waiting for its invite counts as started), whose
    installer has not had the day-2 nudge."""
    sql = """
        SELECT i.team_id, i.bot_token, i.installed_by_user_id
        FROM installations i
        WHERE i.active
          AND i.purged_at IS NULL
          AND i.installed_at < NOW() - make_interval(hours => %s)
          AND i.installed_at > NOW() - INTERVAL '14 days'
          AND NOT EXISTS (SELECT 1 FROM standup_schedules s WHERE s.team_id = i.team_id)
          AND NOT EXISTS (SELECT 1 FROM install_emails e WHERE e.team_id = i.team_id AND e.kind = 'nudge:day2')
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (hours,))
            return [dict(r) for r in cur.fetchall()]


def workspaces_awaiting_followup(days: int = 7) -> list[dict]:
    """Installed at least `days` ago, still live, opted in, and not yet followed up.

    Returns enough to choose which of the two messages to send: a workspace
    with no schedule has never run a standup, which is the case worth asking
    about.
    """
    sql = """
        SELECT i.team_id, i.team_name, i.installed_by_user_id,
               (SELECT COUNT(*) FROM standup_schedules s
                 WHERE s.team_id = i.team_id AND s.active) AS schedules,
               (SELECT COUNT(*) FROM standups st WHERE st.team_id = i.team_id) AS standups,
               (SELECT COUNT(DISTINCT user_id) FROM standups st
                 WHERE st.team_id = i.team_id) AS people
        FROM installations i
        JOIN setup_email_consents c ON c.team_id = i.team_id AND c.revoked_at IS NULL
        WHERE i.active
          AND i.installed_at < NOW() - make_interval(days => %s)
          AND NOT EXISTS (
              SELECT 1 FROM install_emails e
               WHERE e.team_id = i.team_id AND e.kind LIKE 'followup%%')
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (days,))
            return [dict(r) for r in cur.fetchall()]


# ── Consent to be emailed about the product ─────────────────────────────────


def grant_email_consent(email: str, team_id: str = "", source: str = "welcome-email", ip: str = "") -> None:
    """Record an express opt-in. The row is the proof, so it keeps the details."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_consents (email, team_id, source, ip, granted_at, revoked_at)
                VALUES (%s, %s, %s, %s, NOW(), NULL)
                ON CONFLICT (email) DO UPDATE
                   SET granted_at = NOW(), revoked_at = NULL,
                       source = EXCLUDED.source, ip = EXCLUDED.ip
                """,
                (email.lower(), team_id or None, source, ip or None),
            )


def revoke_email_consent(email: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE email_consents SET revoked_at = NOW() WHERE email = %s AND revoked_at IS NULL",
                (email.lower(),),
            )


def has_email_consent(email: str) -> bool:
    if not email:
        return False
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM email_consents WHERE email = %s AND revoked_at IS NULL",
                (email.lower(),),
            )
            return cur.fetchone() is not None


def consented_contacts(unsynced_only: bool = False) -> list[dict]:
    """Everyone who has opted in, for pushing to the contact list."""
    sql = """
        SELECT email, team_id, granted_at, synced_at FROM email_consents
         WHERE revoked_at IS NULL
    """
    if unsynced_only:
        sql += " AND synced_at IS NULL"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def mark_contact_synced(email: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE email_consents SET synced_at = NOW() WHERE email = %s", (email.lower(),))


# ── Consent to email the installer's Slack address ──────────────────────────


def grant_setup_email_consent(team_id: str, user_id: str) -> None:
    """Record that this person pressed "Email me setup tips"."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO setup_email_consents (team_id, user_id, granted_at, revoked_at)
                VALUES (%s, %s, NOW(), NULL)
                ON CONFLICT (team_id) DO UPDATE
                   SET user_id = EXCLUDED.user_id, granted_at = NOW(), revoked_at = NULL
                """,
                (team_id, user_id),
            )


def revoke_setup_email_consent(team_id: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE setup_email_consents SET revoked_at = NOW() WHERE team_id = %s AND revoked_at IS NULL",
                (team_id,),
            )


def setup_email_consent(team_id: str) -> dict | None:
    """The live consent for a workspace, or None when nobody has opted in."""
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, granted_at FROM setup_email_consents WHERE team_id = %s AND revoked_at IS NULL",
                (team_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def count_standups(team_id: str) -> int:
    """How many standups a workspace ever filed. Used on the way out."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM standups WHERE team_id = %s", (team_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0


def count_installations() -> int:
    """How many workspaces have the app right now. Used in the install alert."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM installations WHERE active")
            row = cur.fetchone()
            return int(row[0]) if row else 0
