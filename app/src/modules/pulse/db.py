"""Pulse storage.

An answer is a row in pulse_answers with a random id, the round, the question
and the value: no user id and no timestamp. Who answered is a separate row in
pulse_respondents, with no value, used only to stop a second answer and to
remind the people who have not answered. The two are written in one
transaction, and the answer only when the respondent row was new.

Results leave this module only through round_results and trend, which apply
privacy.MIN_GROUP.
"""

from __future__ import annotations

import psycopg2.extras

from src.core.db import db_conn
from src.modules.pulse import privacy, questions

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
            if cur.fetchone() is None:
                return False
            cur.execute(
                "INSERT INTO pulse_answers (round_id, question_key, value) VALUES (%s, %s, %s)",
                (round_id, question_key, value),
            )
            return True


# ── Results, through the privacy gate ───────────────────────────────────────


def _question_result(values: list[int], key: str) -> dict:
    """One question's numbers, or Nones when too few people answered it."""
    if not privacy.visible(len(values)):
        return {}
    if key == questions.MOOD:
        return {
            "mood_avg": round(sum(values) / len(values), 2),
            "mood_dist": [values.count(v) for v in questions.values(questions.MOOD)],
        }
    if key == questions.ENPS:
        return {"enps": questions.enps_score(values)}
    return {}


def round_results(round_id: int) -> dict:
    """A round's team results: {respondents, invited, hidden, mood_avg, mood_dist, enps}.

    Hidden below MIN_GROUP respondents, and then the answers are not even
    read. A question answered by fewer than MIN_GROUP people stays None even
    when the round is shown.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, team_id, invited, includes_enps, sent_on FROM pulse_rounds WHERE id = %s",
                (round_id,),
            )
            row = cur.fetchone()
            if not row:
                return {}
            _, _, invited, includes_enps, sent_on = row
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
            if not privacy.visible(respondents):
                result["needed"] = privacy.MIN_GROUP
                return result
            cur.execute("SELECT question_key, value FROM pulse_answers WHERE round_id = %s", (round_id,))
            by_question: dict[str, list[int]] = {}
            for key, value in cur.fetchall():
                by_question.setdefault(key, []).append(int(value))
    result["hidden"] = False
    for key, values in by_question.items():
        result.update(_question_result(values, key))
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
                    **privacy.hidden_payload(result["respondents"]),
                }
            )
        else:
            out.append(result)
    return out
