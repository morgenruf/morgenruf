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
