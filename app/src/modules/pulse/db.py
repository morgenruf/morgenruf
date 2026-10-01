"""Pulse storage.

No answer is kept as a row of its own. pulse_tallies holds a count per
round, question and value: no user id and no timestamp. Who answered is a
separate row in pulse_respondents, with no value, used only to stop a second
answer and to remind the people who have not answered.

The respondent row and the count are written in two transactions. Written in
one, both rows would carry the same transaction id (xmin), and anyone with
the database could join a person to the value they picked through it. A
count row is shared by everyone who picked that value, so its xmin only
names the last writer, and the claim it follows is a different transaction.

When a round closes, scrub_round stores its respondent counts on the round,
deletes the respondent and invite rows, and rewrites every tally row so they
all carry the closing transaction id. VACUUM then clears the dead row
versions an older count could be read back from. After that nothing about
the round names a person.

Results leave this module only through round_results and trend, which apply
privacy.MIN_GROUP.
"""

from __future__ import annotations

import logging

import psycopg2.extras

from src.core.db import db_conn, get_conn, release_conn
from src.modules.pulse import privacy, questions

logger = logging.getLogger(__name__)

_PROGRAM_FIELDS = ("enabled", "day_of_week", "hour", "minute", "timezone", "audience_channel_id")


# ── Programme ───────────────────────────────────────────────────────────────


def default_program(team_id: str) -> dict:
    return {
        "team_id": team_id,
        "enabled": False,
        "day_of_week": 4,
        "hour": 14,
        "minute": 0,
        "timezone": "UTC",
        "audience_channel_id": None,
        "updated_by": None,
        "updated_at": None,
    }


def get_program(team_id: str) -> dict:
    """This workspace's settings, with the defaults when it has never saved any."""
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM pulse_programs WHERE team_id = %s", (team_id,))
            row = cur.fetchone()
    return {**default_program(team_id), **dict(row)} if row else default_program(team_id)


def save_program(team_id: str, fields: dict, updated_by: str) -> dict:
    """Store the given settings. The caller validates; this only writes."""
    columns = [c for c in _PROGRAM_FIELDS if c in fields]
    names = ", ".join(["team_id", *columns, "updated_by", "updated_at"])
    placeholders = ", ".join(["%s"] * (len(columns) + 2) + ["NOW()"])
    updates = ", ".join(
        [f"{c} = EXCLUDED.{c}" for c in columns] + ["updated_by = EXCLUDED.updated_by", "updated_at = NOW()"]
    )
    sql = f"""
        INSERT INTO pulse_programs ({names})
        VALUES ({placeholders})
        ON CONFLICT (team_id) DO UPDATE SET {updates}
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, *[fields[c] for c in columns], updated_by))
            row = cur.fetchone()
    return {**default_program(team_id), **dict(row)} if row else get_program(team_id)


# ── Rounds ──────────────────────────────────────────────────────────────────


def create_round(team_id: str, sent_on, closes_at) -> dict | None:
    """Start today's round, or None when it already exists.

    The unique (team_id, sent_on) makes this the one claim on the day across
    pods, retries and a misfired job. eNPS is asked in the first round and
    every fourth after it, counted from the rounds already sent.
    """
    sql = """
        INSERT INTO pulse_rounds (team_id, sent_on, includes_enps, closes_at)
        SELECT %s, %s, MOD((SELECT COUNT(*) FROM pulse_rounds WHERE team_id = %s), 4) = 0, %s
        ON CONFLICT (team_id, sent_on) DO NOTHING
        RETURNING id, team_id, sent_on, includes_enps, closes_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, sent_on, team_id, closes_at))
            row = cur.fetchone()
    return dict(row) if row else None


def record_invites(round_id: int, user_ids: list[str]) -> int:
    """Who this round asked. Returns how many."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            if user_ids:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO pulse_invites (round_id, user_id) VALUES %s ON CONFLICT DO NOTHING",
                    [(round_id, u) for u in user_ids],
                )
            cur.execute(
                "UPDATE pulse_rounds SET invited = (SELECT COUNT(*) FROM pulse_invites WHERE round_id = %s)"
                " WHERE id = %s RETURNING invited",
                (round_id, round_id),
            )
            row = cur.fetchone()
    return int(row[0]) if row else 0


def get_round(round_id: int) -> dict | None:
    sql = """
        SELECT id, team_id, sent_on, includes_enps, invited, reminded_at, closes_at,
               closes_at <= NOW() AS closed
        FROM pulse_rounds WHERE id = %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (round_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def rounds_to_remind(team_id: str) -> list[dict]:
    """Open rounds sent more than a day ago that have not had their reminder."""
    sql = """
        SELECT r.id, r.includes_enps FROM pulse_rounds r
        WHERE r.team_id = %s AND r.reminded_at IS NULL AND r.closes_at > NOW()
          AND r.closes_at <= NOW() + INTERVAL '48 hours'
        ORDER BY r.id
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            return [dict(r) for r in cur.fetchall()]


def claim_reminder(round_id: int) -> bool:
    """Mark a round reminded. True only for the one caller that did it."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pulse_rounds SET reminded_at = NOW() WHERE id = %s AND reminded_at IS NULL RETURNING 1",
                (round_id,),
            )
            return cur.fetchone() is not None


def non_respondents(round_id: int) -> list[str]:
    """Invited people who have not answered anything in this round."""
    sql = """
        SELECT i.user_id FROM pulse_invites i
        WHERE i.round_id = %s
          AND NOT EXISTS (SELECT 1 FROM pulse_respondents r WHERE r.round_id = i.round_id AND r.user_id = i.user_id)
        ORDER BY i.user_id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (round_id,))
            return [r[0] for r in cur.fetchall()]


def answered(round_id: int, user_id: str) -> set[str]:
    """The questions this person has answered in this round. Keys, never values."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT question_key FROM pulse_respondents WHERE round_id = %s AND user_id = %s",
                (round_id, user_id),
            )
            return {r[0] for r in cur.fetchall()}


def round_count(team_id: str) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pulse_rounds WHERE team_id = %s", (team_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0


# ── Answers ─────────────────────────────────────────────────────────────────


def record_answer(round_id: int, user_id: str, question_key: str, value: int) -> bool:
    """Count one answer. False when it was a second answer, late, or not asked.

    The respondent row is claimed first, only for someone invited to a round
    that is still open; the answer is written only when that claim was new.
    The answer row never carries the user id.
    """
    if not questions.valid(question_key, value):
        return False
    claim = """
        INSERT INTO pulse_respondents (round_id, user_id, question_key)
        SELECT %s, %s, %s
        WHERE EXISTS (SELECT 1 FROM pulse_rounds WHERE id = %s AND closes_at > NOW())
          AND EXISTS (SELECT 1 FROM pulse_invites WHERE round_id = %s AND user_id = %s)
        ON CONFLICT DO NOTHING
        RETURNING 1
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(claim, (round_id, user_id, question_key, round_id, round_id, user_id))
            claimed = cur.fetchone() is not None
    # The claim is committed. The count goes in its own transaction on purpose
    # (see the module docstring). A crash between the two loses this one
    # answer: the person is marked as answered but not counted. That is the
    # accepted price of never writing both in one transaction.
    if not claimed:
        return False
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pulse_tallies (round_id, question_key, value, count) VALUES (%s, %s, %s, 1)
                ON CONFLICT (round_id, question_key, value) DO UPDATE SET count = pulse_tallies.count + 1
                """,
                (round_id, question_key, value),
            )
    return True


# ── Results, through the privacy gate ───────────────────────────────────────


def _question_result(counts: dict[int, int], key: str) -> dict:
    """One question's numbers from its counts per value.

    Nothing under MIN_GROUP answers; the average from MIN_GROUP; the
    breakdown and eNPS only from MIN_DETAIL.
    """
    total = sum(counts.values())
    if not privacy.visible(total):
        return {}
    if key == questions.MOOD:
        result = {"mood_avg": round(sum(v * n for v, n in counts.items()) / total, 2)}
        if privacy.detailed(total):
            result["mood_dist"] = [counts.get(v, 0) for v in questions.values(questions.MOOD)]
        return result
    if key == questions.ENPS and privacy.detailed(total):
        return {"enps": questions.enps_score_from_counts(counts)}
    return {}


def round_results(round_id: int) -> dict:
    """A round's team results: {respondents, invited, hidden, mood_avg, mood_dist, enps}.

    Only a closed (scrubbed) round shows anything; an open one returns its
    live respondent count with open=True and no results, and its counts are
    not read. A closed round is hidden below MIN_GROUP respondents. Per
    question, the average needs MIN_GROUP answers and the breakdown and eNPS
    MIN_DETAIL.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, team_id, invited, includes_enps, sent_on, scrubbed_at IS NOT NULL, respondents"
                " FROM pulse_rounds WHERE id = %s",
                (round_id,),
            )
            row = cur.fetchone()
            if not row:
                return {}
            _, _, invited, includes_enps, sent_on, scrubbed, stored = row
            if scrubbed:
                respondents = int(stored or 0)
            else:
                cur.execute("SELECT COUNT(DISTINCT user_id) FROM pulse_respondents WHERE round_id = %s", (round_id,))
                respondents = int((cur.fetchone() or (0,))[0])
            result = {
                "round_id": round_id,
                "sent_on": sent_on,
                "includes_enps": bool(includes_enps),
                "respondents": respondents,
                "invited": int(invited or 0),
                "hidden": True,
                "mood_avg": None,
                "mood_dist": None,
                "enps": None,
            }
            if not scrubbed:
                # Open: the live count only, never a number from the answers.
                result.update(open=True, needed=privacy.MIN_GROUP)
                return result
            if not privacy.visible(respondents):
                result["needed"] = privacy.MIN_GROUP
                return result
            cur.execute("SELECT question_key, value, count FROM pulse_tallies WHERE round_id = %s", (round_id,))
            by_question: dict[str, dict[int, int]] = {}
            for key, value, count in cur.fetchall():
                by_question.setdefault(key, {})[int(value)] = int(count)
    result["hidden"] = False
    for key, counts in by_question.items():
        result.update(_question_result(counts, key))
    return result


def trend(team_id: str, limit: int = 12) -> list[dict]:
    """The latest rounds, oldest first. A hidden round keeps only its date and counts."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM pulse_rounds WHERE team_id = %s ORDER BY sent_on DESC LIMIT %s",
                (team_id, limit),
            )
            ids = [r[0] for r in cur.fetchall()]
    out = []
    for round_id in reversed(ids):
        result = round_results(round_id)
        if not result:
            continue
        if result.get("hidden"):
            out.append(
                {
                    "sent_on": result["sent_on"],
                    "respondents": result["respondents"],
                    "invited": result["invited"],
                    **privacy.hidden_payload(result["respondents"], open_round=bool(result.get("open"))),
                }
            )
        else:
            out.append(result)
    return out


# ── Closing a round ─────────────────────────────────────────────────────────


def unscrubbed_count(team_id: str) -> int:
    """Rounds that still hold who answered: open ones, and closed ones not yet scrubbed."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pulse_rounds WHERE team_id = %s AND scrubbed_at IS NULL", (team_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0


def scrub_round(round_id: int) -> bool:
    """Close one round for good: keep its counts, forget who answered. True when this call did it.

    One transaction: store the respondent counts on the round, delete its
    respondent and invite rows, and rewrite its tally rows so every one of
    them carries this transaction's id instead of the id of the last person
    who picked that value. Only for a round past closes_at and not scrubbed
    yet, so running it again does nothing.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM pulse_rounds WHERE id = %s AND scrubbed_at IS NULL AND closes_at <= NOW() FOR UPDATE",
                (round_id,),
            )
            if cur.fetchone() is None:
                return False
            cur.execute(
                """
                UPDATE pulse_rounds SET
                    respondents = (SELECT COUNT(DISTINCT user_id) FROM pulse_respondents WHERE round_id = %s),
                    question_respondents = (
                        SELECT COALESCE(jsonb_object_agg(question_key, n), '{}'::jsonb)
                        FROM (SELECT question_key, COUNT(*) AS n FROM pulse_respondents
                              WHERE round_id = %s GROUP BY question_key) q
                    ),
                    scrubbed_at = NOW()
                WHERE id = %s
                """,
                (round_id, round_id, round_id),
            )
            cur.execute("DELETE FROM pulse_respondents WHERE round_id = %s", (round_id,))
            cur.execute("DELETE FROM pulse_invites WHERE round_id = %s", (round_id,))
            cur.execute("UPDATE pulse_tallies SET count = count WHERE round_id = %s", (round_id,))
            return True


def vacuum() -> None:
    """Clear dead row versions, so an older count or a deleted respondent row
    cannot be read back from the table pages. VACUUM cannot run inside a
    transaction, so this borrows a connection in autocommit mode. Raises on
    failure; close_due_rounds logs it and carries on."""
    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("VACUUM pulse_tallies, pulse_respondents")
    finally:
        conn.autocommit = False
        release_conn(conn)


def close_open_rounds(team_id: str) -> list[int]:
    """Close every open round now and scrub it. For when Pulse is turned off."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pulse_rounds SET closes_at = NOW() WHERE team_id = %s AND scrubbed_at IS NULL"
                " AND closes_at > NOW()",
                (team_id,),
            )
    return close_due_rounds(team_id)


def close_due_rounds(team_id: str) -> list[int]:
    """Scrub every round of this workspace past its closing time. Returns the ids closed now."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM pulse_rounds WHERE team_id = %s AND scrubbed_at IS NULL AND closes_at <= NOW()"
                " ORDER BY id",
                (team_id,),
            )
            due = [r[0] for r in cur.fetchall()]
    closed = [round_id for round_id in due if scrub_round(round_id)]
    if closed:
        try:
            vacuum()
        except Exception as exc:
            logger.warning("pulse: closed %d round(s) for %s but VACUUM failed: %s", len(closed), team_id, exc)
    return closed
