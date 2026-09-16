"""Connect persistence."""

from __future__ import annotations

import psycopg2.extras

from src.core.db import db_conn
from src.modules.connect.matcher import PairStat


def get_programs(team_id: str) -> list[dict]:
    sql = """
        SELECT p.*,
               (SELECT COUNT(*) FROM connect_rounds r WHERE r.program_id = p.id) AS round_count,
               (SELECT MAX(scheduled_for) FROM connect_rounds r WHERE r.program_id = p.id) AS last_round
        FROM connect_programs p
        WHERE p.team_id = %s
        ORDER BY p.created_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            return [dict(r) for r in cur.fetchall()]


def create_program(team_id: str, channel_id: str, name: str, interval_weeks: int,
                   day_of_week: int, hour: int, minute: int, timezone: str) -> dict:
    sql = """
        INSERT INTO connect_programs
            (team_id, channel_id, name, interval_weeks, day_of_week, hour, minute, timezone)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (team_id, channel_id) DO UPDATE SET
            name = EXCLUDED.name,
            interval_weeks = EXCLUDED.interval_weeks,
            day_of_week = EXCLUDED.day_of_week,
            hour = EXCLUDED.hour,
            minute = EXCLUDED.minute,
            timezone = EXCLUDED.timezone,
            enabled = TRUE
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, channel_id, name, interval_weeks, day_of_week, hour, minute, timezone))
            return dict(cur.fetchone())


def set_program_enabled(team_id: str, program_id: int, enabled: bool) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE connect_programs SET enabled = %s WHERE id = %s AND team_id = %s",
                (enabled, program_id, team_id),
            )


def delete_program(team_id: str, program_id: int) -> bool:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM connect_programs WHERE id = %s AND team_id = %s", (program_id, team_id))
            return (cur.rowcount or 0) > 0


def pair_history(program_id: int) -> dict[tuple[str, str], PairStat]:
    """Everyone who has already met in this program, keyed by normalised pair."""
    sql = "SELECT member_a, member_b, times_paired, last_round_id FROM connect_pair_history WHERE program_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (program_id,))
            return {
                (a, b): PairStat(times_paired=n, last_round_id=r)
                for a, b, n, r in cur.fetchall()
            }


def record_pairs(program_id: int, round_id: int, groups: list[list[str]]) -> None:
    """Write every edge in every group, so a trio counts as three meetings."""
    sql = """
        INSERT INTO connect_pair_history (program_id, member_a, member_b, times_paired, last_round_id)
        VALUES (%s, %s, %s, 1, %s)
        ON CONFLICT (program_id, member_a, member_b) DO UPDATE SET
            times_paired = connect_pair_history.times_paired + 1,
            last_round_id = EXCLUDED.last_round_id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            for group in groups:
                for i, a in enumerate(group):
                    for b in group[i + 1:]:
                        lo, hi = (a, b) if a < b else (b, a)
                        cur.execute(sql, (program_id, lo, hi, round_id))


def optout_user_ids(team_id: str, program_id: int) -> set[str]:
    sql = """
        SELECT user_id FROM connect_optouts
        WHERE team_id = %s AND program_id = %s
          AND (mode = 'off' OR (mode = 'paused' AND (paused_until IS NULL OR paused_until >= CURRENT_DATE)))
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, program_id))
            return {r[0] for r in cur.fetchall()}


def recent_rounds(program_id: int, limit: int = 10) -> list[dict]:
    sql = """
        SELECT r.*,
               (SELECT COUNT(*) FROM connect_matches m WHERE m.round_id = r.id) AS matches,
               (SELECT COUNT(*) FROM connect_matches m WHERE m.round_id = r.id AND m.met IS TRUE) AS met
        FROM connect_rounds r
        WHERE r.program_id = %s
        ORDER BY r.scheduled_for DESC
        LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (program_id, limit))
            return [dict(r) for r in cur.fetchall()]


def purge(team_id: str) -> None:
    """Remove this module's data for a workspace that has disabled it.

    Uninstall is already handled by the foreign key cascade; this covers the
    narrower case of staying installed but asking for the data to go.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM connect_programs WHERE team_id = %s", (team_id,))


def active_programs() -> list[dict]:
    """Every enabled programme across all workspaces, for job planning."""
    sql = """
        SELECT p.*, (SELECT MAX(scheduled_for)::date FROM connect_rounds r WHERE r.program_id = p.id) AS last_round
        FROM connect_programs p
        WHERE p.enabled IS TRUE
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def get_program(program_id: int) -> dict | None:
    sql = """
        SELECT p.*, (SELECT MAX(scheduled_for)::date FROM connect_rounds r WHERE r.program_id = p.id) AS last_round
        FROM connect_programs p WHERE p.id = %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (program_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def create_round(program_id: int, team_id: str, scheduled_for) -> dict | None:
    """Start a round, or return None if one already exists for this slot.

    The unique constraint is the idempotency guard: a duplicate job fire or a
    scheduler restart cannot produce a second round, and therefore cannot
    double-message anyone.
    """
    sql = """
        INSERT INTO connect_rounds (program_id, team_id, scheduled_for, state)
        VALUES (%s, %s, %s, 'pending')
        ON CONFLICT (program_id, scheduled_for) DO NOTHING
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (program_id, team_id, scheduled_for))
            row = cur.fetchone()
    return dict(row) if row else None


def set_round_state(round_id: int, state: str, member_count: int | None = None) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            if member_count is None:
                cur.execute("UPDATE connect_rounds SET state = %s WHERE id = %s", (state, round_id))
            else:
                cur.execute(
                    "UPDATE connect_rounds SET state = %s, member_count = %s WHERE id = %s",
                    (state, member_count, round_id),
                )


def create_matches(round_id: int, team_id: str, groups: list[list[str]]) -> list[dict]:
    sql = """
        INSERT INTO connect_matches (round_id, team_id, member_ids)
        VALUES (%s, %s, %s) RETURNING *
    """
    out = []
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for g in groups:
                cur.execute(sql, (round_id, team_id, g))
                out.append(dict(cur.fetchone()))
    return out


def undelivered_matches(round_id: int) -> list[dict]:
    """Matches still to be sent, so a restart mid-delivery resumes rather than
    starting over and messaging people twice."""
    sql = "SELECT * FROM connect_matches WHERE round_id = %s AND delivered_at IS NULL ORDER BY id"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (round_id,))
            return [dict(r) for r in cur.fetchall()]


def mark_delivered(match_id: int, mpim_channel_id: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE connect_matches SET delivered_at = NOW(), mpim_channel_id = %s WHERE id = %s",
                (mpim_channel_id, match_id),
            )


def matches_for_nudge(round_id: int) -> list[dict]:
    sql = """
        SELECT * FROM connect_matches
        WHERE round_id = %s AND delivered_at IS NOT NULL AND nudged_at IS NULL
          AND mpim_channel_id IS NOT NULL
        ORDER BY id
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (round_id,))
            return [dict(r) for r in cur.fetchall()]


def mark_nudged(match_id: int) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE connect_matches SET nudged_at = NOW() WHERE id = %s", (match_id,))


def set_met(match_id: int, met: bool) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE connect_matches SET met = %s WHERE id = %s", (met, match_id))


def opt_out(team_id: str, program_id: int, user_id: str, mode: str = "off", paused_until=None) -> None:
    sql = """
        INSERT INTO connect_optouts (team_id, program_id, user_id, mode, paused_until)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (team_id, program_id, user_id) DO UPDATE SET
            mode = EXCLUDED.mode, paused_until = EXCLUDED.paused_until
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, program_id, user_id, mode, paused_until))


def matches_for_close(round_id: int) -> list[dict]:
    """Delivered matches with a real conversation, still to be asked whether
    they met. Undeliverable ones carry an empty channel and are skipped."""
    sql = """
        SELECT * FROM connect_matches
        WHERE round_id = %s AND delivered_at IS NOT NULL
          AND mpim_channel_id IS NOT NULL AND mpim_channel_id <> ''
          AND met IS NULL
        ORDER BY id
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (round_id,))
            return [dict(r) for r in cur.fetchall()]
