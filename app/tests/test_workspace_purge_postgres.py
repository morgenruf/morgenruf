"""The purge against a real Postgres, because a mocked cursor cannot prove a row is gone.

Skipped unless MORGENRUF_TEST_DATABASE_URL points at a scratch database with
every migration applied. It seeds two workspaces with a row in every table the
purge covers, purges one, and checks the other is untouched. Never point it at
a database whose data matters: it writes and deletes rows.

    DATABASE_URL=postgresql://localhost/scratch python src/migrate.py
    MORGENRUF_TEST_DATABASE_URL=postgresql://localhost/scratch pytest tests/test_workspace_purge_postgres.py
"""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

URL = os.environ.get("MORGENRUF_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="MORGENRUF_TEST_DATABASE_URL is not set")

SECRET_WORDS = ("Person Name", "person@example.com", "shipped the thing", "thanks for the help")


@pytest.fixture
def pg(monkeypatch):
    # Other test modules stub psycopg2 with a MagicMock; this one needs the real driver.
    for name in [n for n in sys.modules if n.split(".")[0] == "psycopg2"]:
        if isinstance(sys.modules[name], MagicMock):
            del sys.modules[name]
    import psycopg2
    import psycopg2.extras
    import src.core.db as db

    conn = psycopg2.connect(URL)

    @contextmanager
    def real_conn():
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    monkeypatch.setattr(db, "psycopg2", psycopg2)
    monkeypatch.setattr(db, "db_conn", real_conn)
    teams = []
    yield db, conn, teams
    conn.rollback()
    with conn.cursor() as cur:
        for team in teams:
            db.purge_workspace(team)
            cur.execute("DELETE FROM workspace_history WHERE team_id = %s", (team,))
            cur.execute("DELETE FROM email_consents WHERE email LIKE %s", (f"%{team.lower()}%",))
            cur.execute("DELETE FROM installations WHERE team_id = %s", (team,))
    conn.commit()
    conn.close()


def seed(conn, team: str) -> None:
    """One row in every purged table, using the words a leak would show."""
    name, email, answer, thanks = SECRET_WORDS
    user = f"U{team}"
    with conn.cursor() as cur:

        def one(sql, *params):
            cur.execute(sql, params)
            return cur.fetchone()[0] if "RETURNING" in sql else None

        one(
            "INSERT INTO installations (team_id, team_name, bot_token, bot_user_id, app_id, installed_by_user_id,"
            " bot_refresh_token, granted_scopes, installed_at) VALUES (%s, %s, 'xoxb-secret', 'B1', 'A1', %s,"
            " 'xoxe-secret', ARRAY['chat:write'], NOW() - INTERVAL '40 days')",
            team,
            f"Workspace {team}",
            user,
        )
        one("INSERT INTO workspace_config (team_id, manager_email) VALUES (%s, %s)", team, email)
        one(
            "INSERT INTO members (team_id, user_id, real_name, email, active) VALUES (%s, %s, %s, %s, TRUE)",
            team,
            user,
            name,
            email,
        )
        one("INSERT INTO member_profiles (team_id, user_id) VALUES (%s, %s)", team, user)
        sched = one("INSERT INTO standup_schedules (team_id) VALUES (%s) RETURNING id", team)
        one(
            "INSERT INTO standups (team_id, user_id, yesterday, today, schedule_id, submitted_at)"
            " VALUES (%s, %s, %s, %s, %s, NOW() - INTERVAL '30 days')",
            team,
            user,
            answer,
            answer,
            sched,
        )
        one(
            "INSERT INTO standups (team_id, user_id, today, submitted_at) VALUES (%s, %s, %s, NOW() - INTERVAL '5 days')",
            team,
            user,
            answer,
        )
        one(
            "INSERT INTO daily_standup_threads (team_id, channel_id, thread_date, parent_ts) VALUES (%s, 'C1', CURRENT_DATE, '1.2')",
            team,
        )
        one("INSERT INTO user_away (team_id, user_id, away_date) VALUES (%s, %s, CURRENT_DATE)", team, user)
        one("INSERT INTO user_skip (team_id, user_id, skip_date) VALUES (%s, %s, CURRENT_DATE)", team, user)
        hook = one(
            "INSERT INTO webhooks (team_id, webhook_url) VALUES (%s, 'https://example.com/h') RETURNING id", team
        )
        one("INSERT INTO webhook_deliveries (webhook_id, team_id, event_type) VALUES (%s, %s, 'x')", hook, team)
        one(
            "INSERT INTO workflow_rules (team_id, name, trigger, action, action_target) VALUES (%s, 'r', 't', 'a', 'x')",
            team,
        )
        one(
            "INSERT INTO kudos (team_id, from_user, to_user, message) VALUES (%s, %s, 'U2', %s)",
            team,
            user,
            thanks,
        )
        one("INSERT INTO kudos_config (team_id) VALUES (%s)", team)
        prog = one("INSERT INTO connect_programs (team_id, channel_id) VALUES (%s, 'C1') RETURNING id", team)
        rnd = one(
            "INSERT INTO connect_rounds (program_id, team_id, scheduled_for) VALUES (%s, %s, NOW()) RETURNING id",
            prog,
            team,
        )
        match = one(
            "INSERT INTO connect_matches (round_id, team_id, member_ids, delivered_at)"
            " VALUES (%s, %s, ARRAY[%s, 'U2'], NOW() - INTERVAL '2 days') RETURNING id",
            rnd,
            team,
            user,
        )
        one("INSERT INTO connect_matches (round_id, team_id, member_ids) VALUES (%s, %s, ARRAY['U3'])", rnd, team)
        one(
            "INSERT INTO connect_slot_votes (match_id, team_id, user_id, slot_utc) VALUES (%s, %s, %s, NOW())",
            match,
            team,
            user,
        )
        one(
            "INSERT INTO connect_rematch_requests (round_id, match_id, team_id, user_id) VALUES (%s, %s, %s, %s)",
            rnd,
            match,
            team,
            user,
        )
        one(
            "INSERT INTO connect_followups (round_id, kind, team_id, due_at) VALUES (%s, 'nudge', %s, NOW())",
            rnd,
            team,
        )
        one("INSERT INTO connect_optouts (team_id, program_id, user_id) VALUES (%s, %s, %s)", team, prog, user)
        one("INSERT INTO connect_pair_history (program_id, member_a, member_b) VALUES (%s, %s, 'U2')", prog, user)
        one(
            "INSERT INTO connect_zoom_links (team_id, user_id, access_token, refresh_token, access_expires_at)"
            " VALUES (%s, %s, 'z', 'z', NOW())",
            team,
            user,
        )
        one(
            "INSERT INTO celebration_posts (team_id, kind, celebration_date, posted_on, channel_id, user_ids)"
            " VALUES (%s, 'birthday', CURRENT_DATE, CURRENT_DATE, 'C1', ARRAY[%s])",
            team,
            user,
        )
        one("INSERT INTO celebration_settings (team_id) VALUES (%s)", team)
        one("INSERT INTO module_admins (team_id, user_id, module) VALUES (%s, %s, 'kudos')", team, user)
        one("INSERT INTO mcp_api_keys (team_id, key_hash, key_prefix) VALUES (%s, %s, 'mk')", team, uuid.uuid4().hex)
        one("INSERT INTO workspace_holidays (team_id, date, name) VALUES (%s, CURRENT_DATE, 'h')", team)
        one("INSERT INTO workspace_modules (team_id, module, enabled) VALUES (%s, 'kudos', TRUE)", team)
        one("INSERT INTO setup_email_consents (team_id, user_id) VALUES (%s, %s)", team, user)
        one("INSERT INTO install_emails (team_id, kind, to_email) VALUES (%s, 'welcome', %s)", team, email)
        one("INSERT INTO email_consents (email, team_id) VALUES (%s, %s)", f"{team.lower()}@example.com", team)
    conn.commit()


def new_team(teams) -> str:
    team = "TZ" + uuid.uuid4().hex[:10].upper()
    teams.append(team)
    return team


def history(conn, team) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM workspace_history WHERE team_id = %s", (team,))
        row = cur.fetchone()
        return dict(zip([d[0] for d in cur.description], row)) if row else {}


def test_history_counts_what_the_workspace_did(pg):
    db, conn, teams = pg
    team = new_team(teams)
    seed(conn, team)
    assert db.record_workspace_history(team) is True
    row = history(conn, team)
    assert row["members_count"] == 1
    assert row["standups_created"] == 1
    assert row["standup_answers"] == 2
    assert row["kudos_count"] == 1
    assert row["coffee_rounds"] == 1, "only the delivered match counts"
    assert set(row["modules_used"]) == {"standup", "kudos", "connect", "celebrations", "mcp"}
    assert row["days_installed"] == 40
    assert row["first_answer_at"] is not None and row["last_activity_at"] > row["first_answer_at"]
    assert row["removed_at"] is None, "still installed"
    text = repr(row)
    for word in (*SECRET_WORDS, f"U{team}", "xoxb-secret"):
        assert word not in text


def test_purge_deletes_that_workspace_only(pg):
    db, conn, teams = pg
    gone, stays = new_team(teams), new_team(teams)
    seed(conn, gone)
    seed(conn, stays)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE installations SET active = FALSE, deactivated_at = NOW() - INTERVAL '3 days',"
            " deactivated_reason = 'account_inactive' WHERE team_id = %s",
            (gone,),
        )
    conn.commit()
    before_other = db.workspace_data_counts(stays)

    dry = db.workspace_data_counts(gone)
    assert set(dry) == set(db.PURGED_TABLES)
    assert all(n >= 1 for n in dry.values()), f"seed missed a table: {[t for t, n in dry.items() if not n]}"
    assert db.workspace_data_counts(gone) == dry, "counting deleted something"

    deleted = db.purge_workspace(gone)
    assert deleted == dry
    assert all(n == 0 for n in db.workspace_data_counts(gone).values())
    assert db.workspace_data_counts(stays) == before_other

    inst = db.get_installation(gone)
    assert inst["team_name"] == f"Workspace {gone}" and inst["active"] is False
    assert inst["purged_at"] is not None and inst["deactivated_reason"] == "account_inactive"
    assert inst["bot_token"] == "" and inst["bot_refresh_token"] is None
    assert inst["installed_by_user_id"] is None and inst["granted_scopes"] is None

    row = history(conn, gone)
    assert row["standup_answers"] == 2 and row["purged_at"] is not None
    assert row["removal_reason"] == "account_inactive" and row["days_installed"] == 37

    with conn.cursor() as cur:
        cur.execute("SELECT team_id FROM email_consents WHERE email = %s", (f"{gone.lower()}@example.com",))
        assert cur.fetchone()[0] is None

    # Idempotent: a second purge and a later refresh change nothing.
    assert db.purge_workspace(gone) is None
    assert db.record_workspace_history(gone) is False
    assert history(conn, gone)["standup_answers"] == 2


def test_the_sweep_path_refuses_a_workspace_that_came_back(pg):
    db, conn, teams = pg
    team = new_team(teams)
    seed(conn, team)
    since = datetime.now(timezone.utc) - timedelta(days=3)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE installations SET active = FALSE, deactivated_at = %s, deactivated_reason = 'invalid_auth'"
            " WHERE team_id = %s",
            (since, team),
        )
    conn.commit()
    db.reactivate_installation(team)
    assert db.purge_workspace(team, expect_deactivated_at=since) is None
    assert db.workspace_data_counts(team)["members"] == 1


def test_uninstall_path_purges_an_active_workspace(pg):
    db, conn, teams = pg
    team = new_team(teams)
    seed(conn, team)
    assert db.purge_workspace(team, reason="app_uninstalled") is not None
    inst = db.get_installation(team)
    assert inst["active"] is False and inst["deactivated_reason"] == "app_uninstalled"
    assert history(conn, team)["removal_reason"] == "app_uninstalled"


def test_reinstall_after_purge_is_a_new_install(pg):
    db, conn, teams = pg
    team = new_team(teams)
    seed(conn, team)
    db.purge_workspace(team, reason="app_uninstalled")
    db.reactivate_installation(team)
    assert db.save_installation(team, "Back", "xoxb-new", "B1", "A1", "U9") is True
    inst = db.get_installation(team)
    assert inst["purged_at"] is None and inst["active"] is True
    assert inst["installed_by_user_id"] == "U9"
    assert db.save_installation(team, "Back", "xoxb-new", "B1", "A1", "U9") is False


def test_the_sweep_is_a_dry_run_until_switched_on(pg, monkeypatch, caplog):
    import logging

    from src.core import workspace_retention

    db, conn, teams = pg
    team = new_team(teams)
    seed(conn, team)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE installations SET active = FALSE, deactivated_at = NOW() - INTERVAL '2 days',"
            " deactivated_reason = 'account_inactive' WHERE team_id = %s",
            (team,),
        )
    conn.commit()
    monkeypatch.delenv("PURGE_INACTIVE_WORKSPACES", raising=False)
    with caplog.at_level(logging.INFO):
        report = workspace_retention.sweep_inactive_workspaces()
    mine = [r for r in report if r["team_id"] == team]
    assert mine and mine[0]["action"] == "would_purge"
    assert f"would purge {team}" in caplog.text
    assert db.workspace_data_counts(team)["standups"] == 2

    monkeypatch.setenv("PURGE_INACTIVE_WORKSPACES", "1")
    report = workspace_retention.sweep_inactive_workspaces()
    assert [r["action"] for r in report if r["team_id"] == team] == ["purged"]
    assert db.workspace_data_counts(team)["standups"] == 0
    assert [r for r in workspace_retention.sweep_inactive_workspaces() if r["team_id"] == team] == []
