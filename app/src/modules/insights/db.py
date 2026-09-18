"""Cross-signal queries.

These join standup participation against recognition, which no single
competitor can do: Geekbot holds the standups, HeyTaco holds the kudos, and
neither holds both.

The joins are at the SQL level rather than by importing another module's
Python, so the module contract still holds. A workspace that has the kudos
module removed simply has no rows in that table.
"""

from __future__ import annotations

import logging

import psycopg2.extras

from src.core.db import db_conn

logger = logging.getLogger(__name__)


def unrecognised_contributors(team_id: str, days: int = 30, min_standups: int = 8) -> list[dict]:
    """People who showed up consistently and were never thanked for it.

    The whole point is the pairing of the two numbers. A leaderboard shows who
    got kudos; it cannot show who earned them and got none, because a
    recognition tool does not know who did the work.
    """
    sql = """
        WITH participation AS (
            SELECT s.user_id, COUNT(*) AS standups, MAX(s.standup_date) AS last_standup
            FROM standups s
            WHERE s.team_id = %(team)s
              AND s.standup_date > CURRENT_DATE - %(days)s
            GROUP BY s.user_id
        ),
        received AS (
            SELECT k.to_user AS user_id, COUNT(*) AS kudos
            FROM kudos k
            WHERE k.team_id = %(team)s
              AND k.created_at > NOW() - (%(days)s || ' days')::interval
            GROUP BY k.to_user
        )
        SELECT p.user_id,
               p.standups,
               p.last_standup,
               COALESCE(r.kudos, 0) AS kudos,
               m.real_name
        FROM participation p
        LEFT JOIN received r ON r.user_id = p.user_id
        LEFT JOIN members m ON m.team_id = %(team)s AND m.user_id = p.user_id
        WHERE COALESCE(r.kudos, 0) = 0
          AND p.standups >= %(min_standups)s
          AND COALESCE(m.active, TRUE) IS TRUE
        ORDER BY p.standups DESC, p.user_id
    """
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, {"team": team_id, "days": days, "min_standups": min_standups})
                return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("unrecognised_contributors failed for %s: %s", team_id, exc)
        return []


def blocker_rows(team_id: str, days: int = 21) -> dict[str, list[dict]]:
    """Every blocker answer in the window, grouped by person.

    The run detection itself is a pure function, so this only fetches.
    """
    sql = """
        SELECT s.user_id, s.standup_date, s.blockers, m.real_name
        FROM standups s
        LEFT JOIN members m ON m.team_id = s.team_id AND m.user_id = s.user_id
        WHERE s.team_id = %s
          AND s.standup_date > CURRENT_DATE - %s
          AND s.blockers IS NOT NULL
          AND COALESCE(m.active, TRUE) IS TRUE
        ORDER BY s.user_id, s.standup_date
    """
    grouped: dict[str, list[dict]] = {}
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (team_id, days))
                for row in cur.fetchall():
                    grouped.setdefault(row["user_id"], []).append(dict(row))
    except Exception as exc:
        logger.warning("blocker_rows failed for %s: %s", team_id, exc)
    return grouped


def todays_standups(team_id: str) -> list[dict]:
    """Every standup filed today, newest first, with the person's name.

    CURRENT_DATE rather than a per-member local day, matching how the standup
    rows were written: standup_date is set by the server that took the answer.
    """
    sql = """
        SELECT s.user_id,
               s.standup_date,
               s.yesterday,
               s.today,
               s.blockers,
               COALESCE(s.has_blockers, FALSE) AS has_blockers,
               s.mood,
               s.submitted_at,
               s.schedule_id,
               m.real_name
        FROM standups s
        LEFT JOIN members m ON m.team_id = s.team_id AND m.user_id = s.user_id
        WHERE s.team_id = %s
          AND s.standup_date = CURRENT_DATE
        ORDER BY s.submitted_at DESC NULLS LAST, s.id DESC
    """
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (team_id,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("todays_standups failed for %s: %s", team_id, exc)
        return []


def active_schedules(team_id: str) -> list[dict]:
    """Live schedules with the fields needed to work out who was asked today."""
    sql = """
        SELECT id, name, channel_id, schedule_time, schedule_tz, schedule_days,
               participants, active
        FROM standup_schedules
        WHERE team_id = %s
          AND active IS TRUE
        ORDER BY schedule_time, id
    """
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (team_id,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("active_schedules failed for %s: %s", team_id, exc)
        return []


def recent_kudos(team_id: str, limit: int = 5) -> list[dict]:
    """The last few thank-yous, with both names resolved in SQL.

    Joined rather than imported: the kudos module owns the table, and a
    workspace that removed the module simply has no rows to join to.
    """
    sql = """
        SELECT k.id,
               k.from_user,
               k.to_user,
               k.message,
               k.created_at,
               gm.real_name AS from_name,
               rm.real_name AS to_name
        FROM kudos k
        LEFT JOIN members gm ON gm.team_id = k.team_id AND gm.user_id = k.from_user
        LEFT JOIN members rm ON rm.team_id = k.team_id AND rm.user_id = k.to_user
        WHERE k.team_id = %s
        ORDER BY k.created_at DESC, k.id DESC
        LIMIT %s
    """
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (team_id, limit))
                return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("recent_kudos failed for %s: %s", team_id, exc)
        return []


def connect_program_timing(team_id: str) -> dict | None:
    """The oldest enabled coffee chat programme and the dates around its rounds.

    Returns the next round already scheduled and the last one that ran, leaving
    the arithmetic for a missing next round to a pure function. A workspace
    without the connect module has no such table, which the except turns into
    "no programme" rather than a failed page.
    """
    sql = """
        SELECT p.id AS program_id,
               p.name,
               p.interval_weeks,
               -- The weekday the programme runs on. Without it a programme
               -- that has never run falls back to "today", whatever day it is.
               p.day_of_week,
               MIN(r.scheduled_for) FILTER (WHERE r.scheduled_for > NOW()) AS next_scheduled,
               MAX(r.scheduled_for) AS last_round
        FROM connect_programs p
        LEFT JOIN connect_rounds r ON r.program_id = p.id
        WHERE p.team_id = %s
          AND p.enabled IS TRUE
        GROUP BY p.id, p.name, p.interval_weeks, p.day_of_week, p.created_at
        ORDER BY p.created_at
        LIMIT 1
    """
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (team_id,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as exc:
        logger.warning("connect_program_timing failed for %s: %s", team_id, exc)
        return None
