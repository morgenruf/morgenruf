"""Polls storage.

A named poll keys each vote by the voter's user id, so the message can show
who picked what. An anonymous poll keys it by HMAC-SHA256(poll salt, user id):
while the poll is open that is enough to tell "this person already voted",
and close_poll clears the salt, after which no one can work out whose vote a
row is, not even with the database in hand.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime

import psycopg2.extras

from src.core.db import db_conn

SALT_BYTES = 32

_POLL_COLUMNS = """
    id, team_id, created_by, channel_id, message_ts, question, options, anonymous,
    multiple, hide_results, salt, closes_at, closed_at, created_at
"""


def _row(row) -> dict | None:
    if not row:
        return None
    poll = dict(row)
    if poll.get("salt") is not None:
        poll["salt"] = bytes(poll["salt"])
    poll["options"] = list(poll.get("options") or [])
    return poll


def create_poll(
    team_id: str,
    created_by: str,
    channel_id: str,
    question: str,
    options: list[str],
    anonymous: bool,
    multiple: bool,
    hide_results: bool,
    closes_at: datetime | None,
) -> int:
    """Store a new open poll and return its id. Anonymous polls get a fresh salt."""
    salt = os.urandom(SALT_BYTES) if anonymous else None
    sql = """
        INSERT INTO polls (team_id, created_by, channel_id, question, options, anonymous,
                           multiple, hide_results, salt, closes_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    params = (
        team_id,
        created_by,
        channel_id,
        question,
        psycopg2.extras.Json(list(options)),
        bool(anonymous),
        bool(multiple),
        bool(hide_results),
        salt,
        closes_at,
    )
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()[0])


def set_message(poll_id: int, message_ts: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE polls SET message_ts = %s WHERE id = %s", (message_ts, poll_id))


def delete_poll(poll_id: int) -> None:
    """Remove a poll whose message never made it to Slack."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM polls WHERE id = %s", (poll_id,))


def voter_key(poll: dict, user_id: str) -> str:
    """What a vote by this person is stored under.

    The user id on a named poll. On an anonymous poll, an HMAC of it under the
    poll's salt. An anonymous poll without a salt is closed, and a key for it
    would be the user id in the clear, so that is refused.
    """
    if not poll.get("anonymous"):
        return user_id
    salt = poll.get("salt")
    if not salt:
        raise ValueError("an anonymous poll without a salt is closed")
    return hmac.new(bytes(salt), user_id.encode(), hashlib.sha256).hexdigest()


def toggle_vote(poll_id: int, option_idx: int, key: str, multiple: bool) -> bool:
    """Pick or unpick one option for one voter. False when the poll is closed or gone.

    Picking an option already picked removes it. On a one choice poll the
    voter's other options are removed in the same transaction. The poll row is
    share-locked so a close cannot land halfway through, and an advisory lock
    per voter makes concurrent clicks by the same person run one at a time, so
    a one choice poll never ends up with two rows for them.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT closed_at FROM polls WHERE id = %s FOR SHARE", (poll_id,))
            row = cur.fetchone()
            if not row or row[0] is not None:
                return False
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"polls:{poll_id}:{key}",))
            cur.execute(
                "DELETE FROM poll_votes WHERE poll_id = %s AND option_idx = %s AND voter_key = %s",
                (poll_id, option_idx, key),
            )
            if cur.rowcount:
                return True
            if not multiple:
                cur.execute(
                    "DELETE FROM poll_votes WHERE poll_id = %s AND voter_key = %s AND option_idx <> %s",
                    (poll_id, key, option_idx),
                )
            cur.execute(
                "INSERT INTO poll_votes (poll_id, option_idx, voter_key) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (poll_id, option_idx, key),
            )
            return True


def tally(poll_id: int) -> list[int]:
    """Votes per option, in option order."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT jsonb_array_length(options) FROM polls WHERE id = %s", (poll_id,))
            row = cur.fetchone()
            if not row:
                return []
            counts = [0] * int(row[0])
            cur.execute(
                "SELECT option_idx, COUNT(*) FROM poll_votes WHERE poll_id = %s GROUP BY option_idx",
                (poll_id,),
            )
            for idx, n in cur.fetchall():
                if 0 <= idx < len(counts):
                    counts[idx] = int(n)
    return counts


def voters(poll_id: int) -> dict[int, list[str]]:
    """User ids per option index, for a named poll only."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT anonymous FROM polls WHERE id = %s", (poll_id,))
            row = cur.fetchone()
            if not row:
                return {}
            if row[0]:
                raise ValueError("an anonymous poll has no voters to show")
            cur.execute(
                "SELECT option_idx, voter_key FROM poll_votes WHERE poll_id = %s ORDER BY option_idx, voter_key",
                (poll_id,),
            )
            result: dict[int, list[str]] = {}
            for idx, key in cur.fetchall():
                result.setdefault(int(idx), []).append(key)
    return result


def my_choices(poll_id: int, key: str) -> list[int]:
    """The options one voter has picked, by their voter_key. For their eyes only."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT option_idx FROM poll_votes WHERE poll_id = %s AND voter_key = %s ORDER BY option_idx",
                (poll_id, key),
            )
            return [int(r[0]) for r in cur.fetchall()]


def get_poll(poll_id: int) -> dict | None:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT {_POLL_COLUMNS} FROM polls WHERE id = %s", (poll_id,))
            return _row(cur.fetchone())


def redraw(poll_id: int, draw) -> bool:  # noqa: ANN001
    """Call draw(poll, counts, voters_by_option) with the poll as stored right now.

    A transaction-scoped advisory lock per poll is held across the read and
    the draw (the chat.update), so two redraws of one poll run one at a time
    and the later one always draws the later state. A vote racing a close can
    then never put the Vote buttons back on a closed poll. voters_by_option is
    None for an anonymous poll. False when the poll is gone.
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"polls:redraw:{poll_id}",))
            cur.execute(f"SELECT {_POLL_COLUMNS} FROM polls WHERE id = %s", (poll_id,))
            poll = _row(cur.fetchone())
            if not poll:
                return False
            cur.execute(
                "SELECT option_idx, voter_key FROM poll_votes WHERE poll_id = %s ORDER BY option_idx, voter_key",
                (poll_id,),
            )
            rows = [(int(r["option_idx"]), r["voter_key"]) for r in cur.fetchall()]
            counts = [0] * len(poll["options"])
            names: dict[int, list[str]] = {}
            for idx, key in rows:
                if 0 <= idx < len(counts):
                    counts[idx] += 1
                    names.setdefault(idx, []).append(key)
            draw(poll, counts, None if poll["anonymous"] else names)
            return True


def close_poll(poll_id: int) -> bool:
    """Close an open poll and drop its salt. False when it was already closed."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE polls SET closed_at = NOW(), salt = NULL WHERE id = %s AND closed_at IS NULL RETURNING 1",
                (poll_id,),
            )
            return cur.fetchone() is not None


def due_polls(team_id: str) -> list[dict]:
    """Open polls whose closing time has passed."""
    sql = f"""
        SELECT {_POLL_COLUMNS} FROM polls
        WHERE team_id = %s AND closed_at IS NULL AND closes_at IS NOT NULL AND closes_at <= NOW()
        ORDER BY closes_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            return [_row(r) for r in cur.fetchall()]


def open_poll_count(team_id: str) -> int:
    """Open polls with a closing time: the ones the auto-close job is for."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM polls WHERE team_id = %s AND closed_at IS NULL AND closes_at IS NOT NULL",
                (team_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0


def open_poll_ids(team_id: str) -> list[int]:
    """Every open poll in a workspace, for closing them all when Polls is turned off."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM polls WHERE team_id = %s AND closed_at IS NULL ORDER BY id", (team_id,))
            return [int(r[0]) for r in cur.fetchall()]


def open_polls_by(team_id: str, user_id: str, limit: int = 3) -> list[dict]:
    """The newest open polls one person started, for their App Home."""
    sql = """
        SELECT id, channel_id, question FROM polls
        WHERE team_id = %s AND created_by = %s AND closed_at IS NULL
        ORDER BY created_at DESC
        LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id, limit))
            return [dict(r) for r in cur.fetchall()]


def list_polls(team_id: str, limit: int = 50) -> list[dict]:
    """Newest polls first, each with its vote count per option. No salt."""
    sql = """
        SELECT p.id, p.created_by, p.channel_id, p.message_ts, p.question, p.options, p.anonymous,
               p.multiple, p.hide_results, p.closes_at, p.closed_at, p.created_at,
               COALESCE(v.counts, '{}'::jsonb) AS counts
        FROM polls p
        LEFT JOIN LATERAL (
            SELECT jsonb_object_agg(option_idx, n) AS counts
            FROM (SELECT option_idx, COUNT(*) AS n FROM poll_votes WHERE poll_id = p.id GROUP BY option_idx) c
        ) v ON TRUE
        WHERE p.team_id = %s
        ORDER BY p.created_at DESC
        LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, limit))
            rows = cur.fetchall()
    result = []
    for r in rows:
        poll = dict(r)
        options = list(poll.get("options") or [])
        by_idx = poll.pop("counts") or {}
        poll["options"] = options
        poll["counts"] = [int(by_idx.get(str(i), 0)) for i in range(len(options))]
        result.append(poll)
    return result
