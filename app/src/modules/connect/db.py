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


def create_program(
    team_id: str,
    channel_id: str,
    name: str,
    interval_weeks: int,
    day_of_week: int,
    hour: int,
    minute: int,
    timezone: str,
) -> dict:
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


def update_program(team_id: str, program_id: int, **fields) -> dict | None:
    """Change a programme's settings.

    A coffee chat could previously only be created and deleted, so changing a
    time meant losing the round history with it. Only these columns may be
    written, and unknown keys are dropped rather than trusted.
    """
    allowed = {
        "name",
        "channel_id",
        "interval_weeks",
        "day_of_week",
        "hour",
        "minute",
        "timezone",
        "enabled",
        "match_working_hours",
        "meeting_minutes",
        "meeting_link",
        "suggest_times",
        "use_icebreaker",
        "post_stats",
        "group_size",
        "strict_group_size",
        "intro_tone",
        "video_mode",
        "next_round_date",
    }
    changes = {k: v for k, v in fields.items() if k in allowed}
    if not changes:
        return get_program(program_id)
    cols = ", ".join(f"{k} = %s" for k in changes)
    sql = f"UPDATE connect_programs SET {cols} WHERE id = %s AND team_id = %s RETURNING *"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (*changes.values(), program_id, team_id))
            row = cur.fetchone()
    return dict(row) if row else None


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
            return {(a, b): PairStat(times_paired=n, last_round_id=r) for a, b, n, r in cur.fetchall()}


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
                    for b in group[i + 1 :]:
                        lo, hi = (a, b) if a < b else (b, a)
                        cur.execute(sql, (program_id, lo, hi, round_id))


def program_for_channel(team_id: str, channel_id: str) -> dict | None:
    """The enabled programme drawing from this channel, if there is one."""
    sql = """
        SELECT p.*,
               (SELECT MAX(scheduled_for) FROM connect_rounds r WHERE r.program_id = p.id) AS last_round
        FROM connect_programs p
        WHERE p.team_id = %s AND p.channel_id = %s AND p.enabled
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, channel_id))
            row = cur.fetchone()
    return dict(row) if row else None


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


def recent_rounds(team_id: str, program_id: int, limit: int = 10) -> list[dict]:
    """Round history with attendance broken out.

    A match sits in exactly one of four states, and the three that are not
    "met" mean different things: said no, never answered, or never reached
    them at all. Collapsing them into "not met" hides whether the problem is
    the people or the delivery.
    """
    sql = """
        SELECT r.*,
               COUNT(m.id) AS matches,
               COUNT(*) FILTER (WHERE m.met IS TRUE) AS met,
               COUNT(*) FILTER (WHERE m.met IS FALSE) AS missed,
               COUNT(*) FILTER (WHERE m.met IS NULL AND m.delivered_at IS NOT NULL) AS no_reply,
               COUNT(*) FILTER (WHERE m.delivered_at IS NULL) AS undelivered,
               -- Agreeing a time is the step between an introduction and a
               -- meeting, so it is the leading indicator: a round where nobody
               -- agreed anything is failing earlier than one where they agreed
               -- and did not turn up.
               COUNT(*) FILTER (WHERE m.agreed_slot_utc IS NOT NULL) AS agreed,
               COUNT(*) FILTER (WHERE m.zoom_join_url IS NOT NULL) AS with_zoom,
               (SELECT COUNT(*) FROM connect_rematch_requests q WHERE q.round_id = r.id) AS rematch_requests
        FROM connect_rounds r
        LEFT JOIN connect_matches m ON m.round_id = r.id
        WHERE r.program_id = %s AND r.team_id = %s
        GROUP BY r.id
        ORDER BY r.scheduled_for DESC
        LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (program_id, team_id, limit))
            return [dict(r) for r in cur.fetchall()]


def round_matches(team_id: str, round_id: int) -> list[dict]:
    """Every pairing in one round, and what became of it."""
    sql = """
        SELECT m.id, m.member_ids, m.met, m.delivered_at, m.nudged_at,
               m.mpim_channel_id, m.agreed_slot_utc, m.zoom_join_url
        FROM connect_matches m
        WHERE m.round_id = %s AND m.team_id = %s
        ORDER BY m.id
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (round_id, team_id))
            return [dict(r) for r in cur.fetchall()]


def participation(team_id: str, program_id: int, rounds: int = 6) -> list[dict]:
    """Per person, across the last N rounds: paired, met, missed, silent.

    Ordered by who is drifting, because that is the question this answers.
    Someone matched four times who met nobody is the reason to look at all.
    """
    sql = """
        WITH recent AS (
            SELECT id FROM connect_rounds
            WHERE program_id = %s AND team_id = %s
            ORDER BY scheduled_for DESC
            LIMIT %s
        ),
        per_person AS (
            SELECT UNNEST(m.member_ids) AS user_id, m.met, m.delivered_at,
                   r.scheduled_for
            FROM connect_matches m
            JOIN connect_rounds r ON r.id = m.round_id
            WHERE m.round_id IN (SELECT id FROM recent)
        )
        SELECT user_id,
               COUNT(*) AS paired,
               COUNT(*) FILTER (WHERE met IS TRUE) AS met,
               COUNT(*) FILTER (WHERE met IS FALSE) AS missed,
               COUNT(*) FILTER (WHERE met IS NULL AND delivered_at IS NOT NULL) AS no_reply,
               MAX(scheduled_for) FILTER (WHERE met IS TRUE) AS last_met
        FROM per_person
        GROUP BY user_id
        ORDER BY COUNT(*) FILTER (WHERE met IS TRUE) ASC, COUNT(*) DESC, user_id
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (program_id, team_id, rounds))
            return [dict(r) for r in cur.fetchall()]


def owns_program(team_id: str, program_id: int) -> bool:
    """Guard for anything addressed by programme id alone."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM connect_programs WHERE id = %s AND team_id = %s",
                (program_id, team_id),
            )
            return cur.fetchone() is not None


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


def opt_in(team_id: str, program_id: int, user_id: str) -> None:
    """Undo an opt-out. Pausing from the App Home has to be reversible there."""
    sql = "DELETE FROM connect_optouts WHERE team_id = %s AND program_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, program_id, user_id))


def snooze(team_id: str, program_id: int, user_id: str, until) -> None:
    """Stop matching this person until a date.

    The eligibility query has understood mode='paused' with a paused_until for
    as long as the table has existed; nothing ever wrote one, so a snooze was a
    column with no feature attached.
    """
    opt_out(team_id, program_id, user_id, mode="paused", paused_until=until)


def personal_state(team_id: str, program_id: int, user_id: str) -> dict:
    """How this person currently stands with one programme."""
    sql = """
        SELECT mode, paused_until FROM connect_optouts
        WHERE team_id = %s AND program_id = %s AND user_id = %s
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, program_id, user_id))
            row = cur.fetchone()
    if not row:
        return {"state": "in", "until": None}
    mode, until = row
    if mode == "paused" and until:
        return {"state": "snoozed", "until": until}
    return {"state": "out", "until": None}


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


# ── Agreeing a time ─────────────────────────────────────────────────────────
#
# The gap Donut leaves: two willing people and nobody wanting to be the one who
# picks. A tap per acceptable slot is enough for the bot to settle it as soon as
# everyone has accepted the same one.


def match_by_id(match_id: int) -> dict | None:
    sql = "SELECT * FROM connect_matches WHERE id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (match_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def accept_slot(match_id: int, team_id: str, user_id: str, slot_utc) -> None:
    """Record that this person can make this time. Tapping twice is harmless."""
    sql = """
        INSERT INTO connect_slot_votes (match_id, team_id, user_id, slot_utc)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (match_id, user_id, slot_utc) DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (match_id, team_id, user_id, slot_utc))


def withdraw_slot(match_id: int, user_id: str, slot_utc) -> None:
    """Undo one acceptance, for a mis-tap."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM connect_slot_votes WHERE match_id = %s AND user_id = %s AND slot_utc = %s",
                (match_id, user_id, slot_utc),
            )


def slot_votes(match_id: int) -> dict:
    """`{slot_iso: [user_id, ...]}` for every slot anyone has accepted."""
    sql = """
        SELECT slot_utc, user_id FROM connect_slot_votes
        WHERE match_id = %s ORDER BY slot_utc, user_id
    """
    out: dict = {}
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (match_id,))
            for slot, user_id in cur.fetchall():
                out.setdefault(slot, []).append(user_id)
    return out


def agree_slot(match_id: int, slot_utc) -> bool:
    """Settle the match on this time, unless it is already settled.

    Conditional on agreed_slot_utc still being NULL, so two people tapping the
    last slot at the same moment cannot produce two confirmations.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE connect_matches SET agreed_slot_utc = %s
                   WHERE id = %s AND agreed_slot_utc IS NULL""",
                (slot_utc, match_id),
            )
            return cur.rowcount == 1


def program_for_round(round_id: int) -> dict | None:
    """The programme a round belongs to, for the settings a match message needs
    (the meeting room, the length) without the caller tracking the programme id."""
    sql = """
        SELECT p.* FROM connect_programs p
        JOIN connect_rounds r ON r.program_id = p.id
        WHERE r.id = %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (round_id,))
            row = cur.fetchone()
    return dict(row) if row else None


# ── Zoom links ──────────────────────────────────────────────────────────────


def save_zoom_link(
    team_id: str,
    user_id: str,
    access_token: str,
    refresh_token: str,
    access_expires_at,
    refresh_expires_at=None,
) -> None:
    """Store or replace one person's Zoom authorisation.

    Called on first link and again on every refresh, because Zoom rotates the
    refresh token: the one in a refresh response has already replaced the
    stored one on Zoom's side, so not writing it here loses the link.

    Re-linking clears revoked_at, so somebody who reconnects after their
    refresh token expired is simply linked again.
    """
    sql = """
        INSERT INTO connect_zoom_links
            (team_id, user_id, access_token, refresh_token, access_expires_at, refresh_expires_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (team_id, user_id) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            access_expires_at = EXCLUDED.access_expires_at,
            refresh_expires_at = EXCLUDED.refresh_expires_at,
            revoked_at = NULL,
            updated_at = NOW()
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (team_id, user_id, access_token, refresh_token, access_expires_at, refresh_expires_at),
            )


def set_zoom_identity(team_id: str, user_id: str, zoom_user_id: str, zoom_email: str) -> None:
    """Record which Zoom account was linked, so the UI can name it."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE connect_zoom_links SET zoom_user_id = %s, zoom_email = %s, updated_at = NOW()
                   WHERE team_id = %s AND user_id = %s""",
                (zoom_user_id, zoom_email, team_id, user_id),
            )


def zoom_link(team_id: str, user_id: str) -> dict | None:
    """One person's live link, or None if absent or revoked."""
    sql = """
        SELECT * FROM connect_zoom_links
        WHERE team_id = %s AND user_id = %s AND revoked_at IS NULL
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return dict(row) if row else None


def revoke_zoom_link(team_id: str, user_id: str) -> None:
    """Mark a link unusable without deleting it.

    Kept rather than deleted so the App Home can say "reconnect Zoom" instead
    of silently showing an unlinked state, which looks like the link was never
    made and invites a support question.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE connect_zoom_links SET revoked_at = NOW(), updated_at = NOW() "
                "WHERE team_id = %s AND user_id = %s",
                (team_id, user_id),
            )


def zoom_linked_user_ids(team_id: str, user_ids: list) -> list:
    """Which of these people have a live Zoom link, in the order given."""
    if not user_ids:
        return []
    sql = """
        SELECT user_id FROM connect_zoom_links
        WHERE team_id = %s AND user_id = ANY(%s) AND revoked_at IS NULL
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, list(user_ids)))
            live = {r[0] for r in cur.fetchall()}
    return [u for u in user_ids if u in live]


def set_match_meeting(match_id: int, join_url: str, meeting_id: str) -> bool:
    """Attach a created meeting to a match, once.

    Conditional on there being none, so a retry or a second delivery cannot
    leave two meetings on somebody's Zoom account.
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE connect_matches SET zoom_join_url = %s, zoom_meeting_id = %s
                   WHERE id = %s AND zoom_join_url IS NULL""",
                (join_url, meeting_id, match_id),
            )
            return cur.rowcount == 1


# ── Re-match requests ───────────────────────────────────────────────────────
#
# A round has no spare people: everyone eligible is already matched. So a
# request to be re-matched waits for a second one, and the two people who both
# asked are introduced to each other.


def request_rematch(round_id: int, match_id: int, team_id: str, user_id: str) -> None:
    """Record an open request. Asking twice in a round changes nothing."""
    sql = """
        INSERT INTO connect_rematch_requests (round_id, match_id, team_id, user_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (round_id, user_id) DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (round_id, match_id, team_id, user_id))


def claim_rematch_partner(round_id: int, user_id: str) -> str | None:
    """Resolve this person against another open request, if there is one.

    Both rows are closed in one statement so two people asking at the same
    moment cannot both be handed the other and then each wait for a third.
    Returns the partner's user_id, or None if nobody else is waiting.
    """
    sql = """
        WITH partner AS (
            SELECT id, user_id FROM connect_rematch_requests
            WHERE round_id = %s AND user_id <> %s AND resolved_at IS NULL
            ORDER BY created_at
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        ), closed AS (
            UPDATE connect_rematch_requests r
            SET resolved_at = NOW(),
                paired_with = CASE WHEN r.user_id = %s THEN (SELECT user_id FROM partner) ELSE %s END
            WHERE r.round_id = %s
              AND r.resolved_at IS NULL
              AND (r.user_id = %s OR r.id = (SELECT id FROM partner))
              AND EXISTS (SELECT 1 FROM partner)
            RETURNING r.user_id
        )
        SELECT user_id FROM closed WHERE user_id <> %s
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (round_id, user_id, user_id, user_id, round_id, user_id, user_id))
            row = cur.fetchone()
    return row[0] if row else None


def open_rematch_count(round_id: int) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM connect_rematch_requests WHERE round_id = %s AND resolved_at IS NULL",
                (round_id,),
            )
            return int(cur.fetchone()[0])


def zoom_link_summary(team_id: str) -> dict:
    """How many people have Zoom connected, and how many need reconnecting.

    A revoked row is kept precisely so this can tell the two apart: somebody
    who never linked needs an invitation, somebody whose refresh token expired
    needs telling.
    """
    sql = """
        SELECT COUNT(*) FILTER (WHERE revoked_at IS NULL)  AS linked,
               COUNT(*) FILTER (WHERE revoked_at IS NOT NULL) AS needs_reconnect
        FROM connect_zoom_links WHERE team_id = %s
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            linked, stale = cur.fetchone()
    return {"linked": int(linked or 0), "needs_reconnect": int(stale or 0)}


def member_states(team_id: str, program_id: int) -> dict:
    """`{user_id: {"state", "until"}}` for everyone with a recorded state.

    One query rather than personal_state per person: a members table for a
    channel of 57 would otherwise be 57 round trips, which is how a page ends
    up taking two seconds to say almost nothing.
    """
    sql = """
        SELECT user_id, mode, paused_until FROM connect_optouts
        WHERE team_id = %s AND program_id = %s
    """
    out: dict = {}
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, program_id))
            for user_id, mode, until in cur.fetchall():
                if mode == "paused" and until:
                    out[user_id] = {"state": "snoozed", "until": until}
                else:
                    out[user_id] = {"state": "out", "until": None}
    return out


def pair_counts(team_id: str, program_id: int) -> dict:
    """`{user_id: times_paired}` for this programme, so the members table can
    show who has actually been introduced and who keeps being left out."""
    sql = """
        SELECT member, COUNT(*) FROM (
            SELECT UNNEST(m.member_ids) AS member
            FROM connect_matches m
            JOIN connect_rounds r ON r.id = m.round_id
            WHERE r.program_id = %s AND m.team_id = %s
        ) x GROUP BY member
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (program_id, team_id))
            return {u: int(n) for u, n in cur.fetchall()}
