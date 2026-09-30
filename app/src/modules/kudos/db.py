"""Kudos persistence, extracted verbatim from core.db.

The function bodies below are unchanged. A test asserts that with an AST
comparison against the previous revision, so the extraction cannot silently
alter behavior.
"""

from __future__ import annotations

import re

import psycopg2.extras

from src.core.db import db_conn
from src.modules.kudos.allowance import day_bounds_utc, remaining


def save_kudos(
    team_id: str, from_user: str, to_user: str, message: str, channel_id: str = "", emoji: str | None = None
) -> dict:
    """Save a kudos entry and return it."""
    sql = """
        INSERT INTO kudos (team_id, from_user, to_user, message, channel_id, emoji)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, from_user, to_user, message, channel_id, emoji))
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


DEFAULT_EMOJI = "\N{MAPLE LEAF}"  # upgraded to :morgenruf: once that emoji exists
DEFAULT_ALLOWANCE = 5

# A Slack shortcode (`:tada:`, `:wave::skin-tone-2:`) or unicode emoji. The
# token is posted into channels, so anything that could carry markup (angle
# brackets, formatting characters, plain words) is refused.
_SHORTCODE = re.compile(r"^(?::[a-z0-9_+'-]{1,40}:)+$")
_MARKUP = set("<>&*_~`|:")


def valid_emoji(value: str) -> bool:
    """True for a shortcode or a unicode emoji of at most 16 characters."""
    if not value or len(value) > 16:
        return False
    if _SHORTCODE.match(value):
        return True
    if any(ch in _MARKUP or ch.isspace() or ch.isascii() and ch.isalpha() for ch in value):
        return False
    return any(not ch.isascii() for ch in value)


def get_config(team_id: str) -> dict:
    """The workspace's token, daily allowance and channel, with defaults applied.

    A workspace that has never opened the settings has no row, which is not an
    error: it means the defaults. An empty channel_id means no kudos channel.
    """
    defaults = {"emoji": DEFAULT_EMOJI, "daily_allowance": DEFAULT_ALLOWANCE, "token_auto": True, "channel_id": ""}
    sql = "SELECT emoji, daily_allowance, token_auto, channel_id FROM kudos_config WHERE team_id = %s"
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (team_id,))
                row = cur.fetchone()
    except Exception:
        return defaults
    if not row:
        return defaults
    return {
        # A token saved before it was validated falls back to the default
        # rather than reaching Slack as markup.
        "emoji": row[0] if valid_emoji(row[0] or "") else DEFAULT_EMOJI,
        "daily_allowance": row[1],
        "token_auto": bool(row[2]) if row[2] is not None else True,
        "channel_id": row[3] or "",
    }


def set_config(team_id: str, emoji: str, daily_allowance: int, channel_id: str | None = None) -> dict:
    """Save the settings form.

    Choosing a token turns off the automatic one for good. Changing only the
    allowance must not: the form submits every field, so treating any save as
    a token choice quietly opted people out of the branded emoji for editing
    an unrelated number.

    channel_id None leaves the saved channel as it is, so a caller that does
    not know about the channel cannot clear it. An empty string clears it.
    """
    sql = """
        INSERT INTO kudos_config (team_id, emoji, daily_allowance, channel_id, token_auto, updated_at)
        VALUES (%s, %s, %s, %s, FALSE, NOW())
        ON CONFLICT (team_id) DO UPDATE SET
            emoji = EXCLUDED.emoji,
            daily_allowance = EXCLUDED.daily_allowance,
            channel_id = COALESCE(EXCLUDED.channel_id, kudos_config.channel_id),
            token_auto = CASE
                WHEN kudos_config.emoji IS DISTINCT FROM EXCLUDED.emoji THEN FALSE
                ELSE kudos_config.token_auto
            END,
            updated_at = NOW()
        RETURNING emoji, daily_allowance, token_auto, channel_id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, emoji, daily_allowance, channel_id))
            row = cur.fetchone()
    return {"emoji": row[0], "daily_allowance": row[1], "token_auto": bool(row[2]), "channel_id": row[3] or ""}


def set_token_automatically(team_id: str, emoji: str) -> None:
    """Move a workspace that has not chosen for itself. Never touches one that has."""
    sql = """
        INSERT INTO kudos_config (team_id, emoji, daily_allowance, token_auto, updated_at)
        VALUES (%s, %s, %s, TRUE, NOW())
        ON CONFLICT (team_id) DO UPDATE SET
            emoji = EXCLUDED.emoji,
            updated_at = NOW()
        WHERE kudos_config.token_auto
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, emoji, DEFAULT_ALLOWANCE))


def given_today(team_id: str, from_user: str, tz_name: str, now_utc) -> int:
    """How many kudos this person has given inside their own local day."""
    start, end = day_bounds_utc(tz_name, now_utc)
    sql = """
        SELECT COUNT(*) FROM kudos
        WHERE team_id = %s AND from_user = %s
          AND created_at >= %s AND created_at < %s
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, from_user, start, end))
            return int(cur.fetchone()[0])


def allowance_state(team_id: str, from_user: str, tz_name: str, now_utc) -> dict:
    """Everything the handler needs to decide whether a kudos may be sent."""
    cfg = get_config(team_id)
    used = given_today(team_id, from_user, tz_name, now_utc)
    left = remaining(cfg["daily_allowance"], used)
    return {
        "emoji": cfg["emoji"],
        "allowance": cfg["daily_allowance"],
        "used": used,
        "remaining": left,
        "can_give": left > 0,
    }


def get_giver_leaderboard(team_id: str, days: int = 30) -> list[dict]:
    """Top givers. Recognising the people who recognise others is the half
    most tools leave out, and it is what keeps the habit alive."""
    sql = """
        SELECT from_user AS user_id, COUNT(*) AS given, MAX(created_at) AS last_given
        FROM kudos
        WHERE team_id = %s AND created_at > NOW() - (%s || ' days')::interval
        GROUP BY from_user
        ORDER BY given DESC, last_given DESC
        LIMIT 10
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, days))
            return [dict(r) for r in cur.fetchall()]
