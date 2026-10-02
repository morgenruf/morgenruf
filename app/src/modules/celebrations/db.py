"""Celebrations storage: settings, and a record of every post.

Birthdays and start dates are read from core's member_profiles; the working
week and holidays from core's workspace calendar. Neither is written here.
"""

from __future__ import annotations

from datetime import date

import psycopg2.extras

from src.core.db import db_conn

DEFAULT_POST_TIME = "09:00"
# celebration_posts rows are kept this long, then deleted. A post is only
# looked up again on the day it is made, so a year is generous.
POST_RETENTION_DAYS = 400

_SETTING_FIELDS = ("channel_id", "timezone", "post_time", "birthdays", "anniversaries", "banners")


def default_settings(team_id: str) -> dict:
    return {
        "team_id": team_id,
        "channel_id": None,
        "timezone": None,
        "post_time": DEFAULT_POST_TIME,
        "birthdays": True,
        "anniversaries": True,
        "banners": True,
        "updated_by": None,
        "updated_at": None,
    }


def is_ready(settings: dict | None) -> bool:
    """Whether there is enough to post: a channel and a timezone."""
    return bool(settings and settings.get("channel_id") and settings.get("timezone"))


def get_settings(team_id: str) -> dict:
    """This workspace's settings, with the defaults when it has never saved any."""
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM celebration_settings WHERE team_id = %s", (team_id,))
            row = cur.fetchone()
    return {**default_settings(team_id), **dict(row)} if row else default_settings(team_id)


def save_settings(team_id: str, fields: dict, updated_by: str) -> dict:
    """Store the given settings. The caller validates; this only writes."""
    columns = [c for c in _SETTING_FIELDS if c in fields]
    names = ", ".join(["team_id", *columns, "updated_by", "updated_at"])
    placeholders = ", ".join(["%s"] * (len(columns) + 2) + ["NOW()"])
    updates = ", ".join(
        [f"{c} = EXCLUDED.{c}" for c in columns] + ["updated_by = EXCLUDED.updated_by", "updated_at = NOW()"]
    )
    sql = f"""
        INSERT INTO celebration_settings ({names})
        VALUES ({placeholders})
        ON CONFLICT (team_id) DO UPDATE SET {updates}
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, *[fields[c] for c in columns], updated_by))
            row = cur.fetchone()
    return {**default_settings(team_id), **dict(row)} if row else get_settings(team_id)


def celebrants(team_id: str) -> list[dict]:
    """Everyone who may be celebrated, with the dates to check.

    Active means the profile has not been marked as left and the person is
    not a deactivated member. A profile with no members row (dates imported
    for someone the bot has never met) counts as active: the member sync
    stamps left_at on those when the person leaves Slack.
    """
    sql = """
        SELECT p.user_id, p.birth_month, p.birth_day, p.start_date,
               m.real_name, m.display_name
        FROM member_profiles p
        LEFT JOIN members m ON m.team_id = p.team_id AND m.user_id = p.user_id
        WHERE p.team_id = %s
          AND p.celebrate
          AND p.left_at IS NULL
          AND COALESCE(m.active, TRUE)
          AND (p.birth_month IS NOT NULL OR p.start_date IS NOT NULL)
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            return [dict(r) for r in cur.fetchall()]


def claim_post(
    team_id: str, kind: str, celebration_date: date, posted_on: date, channel_id: str, user_ids: list[str]
) -> bool:
    """Reserve one post. True only for the one caller that inserted the row.

    The primary key (team, kind, date) is the lock: a restart, a later pass
    the same day or a second pod finds the row and backs off.
    """
    sql = """
        INSERT INTO celebration_posts (team_id, kind, celebration_date, posted_on, channel_id, user_ids)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (team_id, kind, celebration_date) DO NOTHING
        RETURNING 1
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, kind, celebration_date, posted_on, channel_id, list(user_ids)))
            return cur.fetchone() is not None


def record_post(team_id: str, kind: str, celebration_date: date, ts: str, banner: str | None = None) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE celebration_posts SET ts = %s, banner = %s "
                "WHERE team_id = %s AND kind = %s AND celebration_date = %s",
                (ts, banner, team_id, kind, celebration_date),
            )


def last_banner(team_id: str, kind: str) -> str | None:
    """The banner on this workspace's latest post of this kind, so the next one differs."""
    sql = """
        SELECT banner FROM celebration_posts
        WHERE team_id = %s AND kind = %s AND banner IS NOT NULL
        ORDER BY created_at DESC LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, kind))
            row = cur.fetchone()
    return row[0] if row else None


def release_post(team_id: str, kind: str, celebration_date: date) -> None:
    """Give a claim back when Slack refused the post, so a later pass retries it.

    Only a claim that never got a ts is released; a post Slack accepted is
    never deleted, so it can never be sent twice.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM celebration_posts "
                "WHERE team_id = %s AND kind = %s AND celebration_date = %s AND ts IS NULL",
                (team_id, kind, celebration_date),
            )


def posted_keys(team_id: str, since: date) -> set[tuple[str, date]]:
    """(kind, date) of every post from `since` on, for showing what already went out."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT kind, celebration_date FROM celebration_posts WHERE team_id = %s AND celebration_date >= %s",
                (team_id, since),
            )
            return {(kind, day) for kind, day in cur.fetchall()}


def purge_old_posts(team_id: str, days: int = POST_RETENTION_DAYS) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM celebration_posts WHERE team_id = %s AND celebration_date < CURRENT_DATE - %s",
                (team_id, int(days)),
            )
            return cur.rowcount or 0


def purge(team_id: str) -> None:
    """Delete this module's data for one workspace. Profiles and the calendar are core's."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM celebration_posts WHERE team_id = %s", (team_id,))
            cur.execute("DELETE FROM celebration_settings WHERE team_id = %s", (team_id,))
