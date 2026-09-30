"""Removed workspaces: keep what they did, delete who they were.

The listing and the privacy page promise that removing the app deletes the
workspace's data. Workspaces Slack reports as gone were only marked inactive,
so their members, answers and kudos stayed. These tests hold the code to:

  * workspace_history keeps counts and dates, never a person
  * the purge deletes every table that holds people or content, for that
    workspace only, and records history first
  * the sweep deletes nothing unless PURGE_INACTIVE_WORKSPACES=1
  * a workspace that came back is never purged, and invalid_auth gets a week
  * running any of it twice changes nothing the second time
"""

from __future__ import annotations

import importlib
import logging
import pathlib
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import src.core.db as real_db
import src.core.scheduler as scheduler
from src.core import workspace_retention as retention

APP = pathlib.Path(__file__).resolve().parents[1]
SRC = APP / "src"
MIGRATION = SRC / "core/migrations/062_workspace_history.sql"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class FakeCursor:
    """Records every statement, answers fetchone/fetchall/rowcount from a script."""

    def __init__(self, fetchone=None, fetchall=None, rowcount=2):
        self.calls: list[tuple[str, tuple]] = []
        self._fetchone = list(fetchone or [])
        self._fetchall = list(fetchall or [])
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), tuple(params)))

    def fetchone(self):
        return self._fetchone.pop(0) if self._fetchone else None

    def fetchall(self):
        return self._fetchall.pop(0) if self._fetchall else []


@pytest.fixture
def cursor(monkeypatch):
    cur = FakeCursor()
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(real_db, "db_conn", fake_conn)
    return cur


def every_table_name() -> list[tuple[str]]:
    return [(t,) for t in real_db.PURGED_TABLES]


# ── The table itself ────────────────────────────────────────────────────────


def history_columns() -> list[str]:
    sql = re.sub(r"/\*.*?\*/", "", MIGRATION.read_text(), flags=re.S)
    body = sql[sql.index("CREATE TABLE IF NOT EXISTS workspace_history") :]
    body = body[body.index("(") + 1 : body.index(");")]
    names = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        names.append(line.split()[0])
    return names


class TestTheHistoryTable:
    def test_it_is_the_next_migration(self):
        numbers = sorted(int(p.name[:3]) for p in SRC.rglob("migrations/*.sql"))
        assert numbers[-1] == 62
        assert MIGRATION.exists()

    def test_it_has_the_columns_we_learn_from(self):
        cols = set(history_columns())
        for wanted in (
            "team_id",
            "team_name",
            "installed_at",
            "removed_at",
            "removal_reason",
            "install_source",
            "members_count",
            "standups_created",
            "standup_answers",
            "first_answer_at",
            "last_activity_at",
            "kudos_count",
            "coffee_rounds",
            "modules_used",
            "days_installed",
            "updated_at",
        ):
            assert wanted in cols, wanted

    def test_no_column_can_hold_a_person_or_what_they_wrote(self):
        forbidden = re.compile(r"user|email|real_name|display_name|message|answer_text|yesterday|today|blocker|token")
        offenders = [c for c in history_columns() if forbidden.search(c)]
        assert not offenders, f"personal or content columns in workspace_history: {offenders}"

    def test_team_id_is_the_key(self):
        assert re.search(r"team_id\s+TEXT PRIMARY KEY", MIGRATION.read_text())


# ── Recording history ───────────────────────────────────────────────────────


class TestRecordHistory:
    def test_it_upserts_one_row_for_the_team(self, cursor):
        cursor.rowcount = 1
        assert real_db.record_workspace_history("T1") is True
        (sql, params), *_ = cursor.calls
        assert sql.startswith("INSERT INTO workspace_history")
        assert "ON CONFLICT (team_id) DO UPDATE" in sql
        assert params == ("T1",)

    def test_it_counts_from_the_live_tables(self, cursor):
        real_db.record_workspace_history("T1")
        sql = cursor.calls[0][0]
        assert "FROM members" in sql and "m.active" in sql
        assert "FROM standup_schedules" in sql
        assert "FROM standups" in sql and "MIN(submitted_at)" in sql
        assert "FROM kudos" in sql
        assert "FROM connect_matches" in sql and "delivered_at IS NOT NULL" in sql
        assert "modules_used" in sql and "days_installed" in sql

    def test_it_reads_no_personal_column(self, cursor):
        real_db.record_workspace_history("T1")
        sql = cursor.calls[0][0].lower()
        for column in (
            "email",
            "real_name",
            "display_name",
            "message",
            "yesterday",
            "blockers",
            "from_user",
            "to_user",
        ):
            assert column not in sql, column

    def test_an_already_purged_workspace_keeps_its_last_counts(self, cursor):
        """Once the rows are gone every count would read zero."""
        real_db.record_workspace_history("T1")
        assert "i.purged_at IS NULL" in cursor.calls[0][0]

    def test_install_source_is_never_overwritten(self, cursor):
        real_db.record_workspace_history("T1")
        update = cursor.calls[0][0].split("DO UPDATE SET", 1)[1]
        assert "install_source" not in update

    def test_the_nightly_refresh_covers_every_installation(self, cursor):
        cursor.rowcount = 12
        assert real_db.record_all_workspace_history() == 12
        sql, params = cursor.calls[0]
        assert "i.team_id = %s" not in sql
        main_filter = sql.split("ON CONFLICT")[0].rsplit("WHERE", 1)[1].strip()
        assert main_filter == "i.purged_at IS NULL", "retired workspaces are refreshed too"
        assert params == ()


# ── Purging one workspace ───────────────────────────────────────────────────


def purge_script(cursor, active=False, purged_at=None, deactivated_at=NOW - timedelta(days=30)):
    cursor._fetchone = [(active, purged_at, deactivated_at)]
    cursor._fetchall = [every_table_name()]


def statements(cursor, verb):
    return [(sql, params) for sql, params in cursor.calls if sql.startswith(verb)]


def deleted_tables(cursor) -> list[str]:
    return [sql.split()[2] for sql, _ in statements(cursor, "DELETE FROM")]


class TestPurgeWorkspace:
    def test_it_deletes_every_personal_table(self, cursor):
        purge_script(cursor)
        result = real_db.purge_workspace("T1", reason="app_uninstalled")
        assert result is not None
        assert set(deleted_tables(cursor)) == set(real_db.PURGED_TABLES)
        assert set(result) >= set(real_db.PURGED_TABLES)

    def test_every_delete_is_scoped_to_that_team(self, cursor):
        purge_script(cursor)
        real_db.purge_workspace("T1")
        deletes = statements(cursor, "DELETE FROM")
        assert deletes
        for sql, params in deletes:
            assert "team_id = %s" in sql, sql
            assert params == ("T1",), sql

    def test_it_never_deletes_the_installation_or_the_history(self, cursor):
        purge_script(cursor)
        real_db.purge_workspace("T1")
        tables = deleted_tables(cursor)
        assert "installations" not in tables
        assert "workspace_history" not in tables

    def test_history_is_recorded_before_anything_is_deleted(self, cursor):
        purge_script(cursor)
        real_db.purge_workspace("T1")
        sqls = [sql for sql, _ in cursor.calls]
        first_history = next(i for i, s in enumerate(sqls) if s.startswith("INSERT INTO workspace_history"))
        first_delete = next(i for i, s in enumerate(sqls) if s.startswith("DELETE FROM"))
        assert first_history < first_delete

    def test_the_installation_row_is_stripped_to_the_bare_minimum(self, cursor):
        purge_script(cursor)
        real_db.purge_workspace("T1", reason="tokens_revoked")
        strip = [s for s, _ in statements(cursor, "UPDATE installations") if "purged_at = NOW()" in s]
        assert len(strip) == 1
        sql = strip[0]
        for cleared in (
            "bot_token = ''",
            "bot_refresh_token = NULL",
            "bot_token_expires_at = NULL",
            "installed_by_user_id = NULL",
            "granted_scopes = NULL",
        ):
            assert cleared in sql, cleared
        assert "active = FALSE" in " ".join(s for s, _ in statements(cursor, "UPDATE installations"))

    def test_the_reason_from_slack_is_kept(self, cursor):
        purge_script(cursor, active=True, deactivated_at=None)
        real_db.purge_workspace("T1", reason="app_uninstalled")
        retire = statements(cursor, "UPDATE installations")[0]
        assert "deactivated_reason" in retire[0]
        assert "app_uninstalled" in retire[1]

    def test_product_email_consent_is_detached_not_kept_against_the_team(self, cursor):
        purge_script(cursor)
        real_db.purge_workspace("T1")
        detach = [c for c in statements(cursor, "UPDATE email_consents")]
        assert detach and "team_id = NULL" in detach[0][0] and detach[0][1] == ("T1",)

    def test_history_is_marked_purged(self, cursor):
        purge_script(cursor)
        real_db.purge_workspace("T1")
        marks = statements(cursor, "UPDATE workspace_history")
        assert marks and "purged_at = NOW()" in marks[0][0]

    def test_a_table_missing_from_this_deployment_is_skipped(self, cursor):
        cursor._fetchone = [(False, None, NOW)]
        cursor._fetchall = [[("members",), ("standups",)]]
        real_db.purge_workspace("T1")
        assert set(deleted_tables(cursor)) == {"members", "standups"}

    def test_an_already_purged_workspace_is_left_alone(self, cursor):
        purge_script(cursor, purged_at=NOW)
        assert real_db.purge_workspace("T1") is None
        assert not statements(cursor, "DELETE FROM")
        assert not statements(cursor, "UPDATE")
        assert not statements(cursor, "INSERT")

    def test_an_unknown_workspace_is_left_alone(self, cursor):
        cursor._fetchone = [None]
        assert real_db.purge_workspace("T404") is None
        assert not statements(cursor, "DELETE FROM")

    def test_the_row_is_locked_while_it_is_checked(self, cursor):
        purge_script(cursor)
        real_db.purge_workspace("T1")
        assert "FOR UPDATE" in cursor.calls[0][0]

    def test_the_sweep_refuses_a_workspace_that_came_back(self, cursor):
        """Reinstalled between the sweep listing it and purging it."""
        purge_script(cursor, active=True, deactivated_at=None)
        assert real_db.purge_workspace("T1", expect_deactivated_at=NOW - timedelta(days=30)) is None
        assert not statements(cursor, "DELETE FROM")

    def test_the_sweep_refuses_a_workspace_retired_again_since(self, cursor):
        """Came back and dropped again: the grace period starts over."""
        purge_script(cursor, deactivated_at=NOW)
        assert real_db.purge_workspace("T1", expect_deactivated_at=NOW - timedelta(days=30)) is None
        assert not statements(cursor, "DELETE FROM")

    def test_counting_deletes_nothing(self, cursor):
        cursor._fetchall = [every_table_name()]
        cursor._fetchone = [(3,)] * len(real_db.PURGED_TABLES)
        counts = real_db.workspace_data_counts("T1")
        assert set(counts) == set(real_db.PURGED_TABLES)
        assert all(n == 3 for n in counts.values())
        assert not statements(cursor, "DELETE")
        assert not statements(cursor, "UPDATE")
        assert not statements(cursor, "INSERT")


class TestEveryTeamTableIsAccountedFor:
    """A table added later with a team_id must be put on one list or the other."""

    def tables_with_team_id(self) -> set[str]:
        found = set()
        for path in SRC.rglob("migrations/*.sql"):
            sql = re.sub(r"-{2}[^\n]*|/\*.*?\*/", "", path.read_text(), flags=re.S)
            for name, body in re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)\s*\((.*?)\n\);", sql, re.S):
                if re.search(r"\bteam_id\b", body):
                    found.add(name)
            for name in re.findall(r"ALTER TABLE (\w+)\s+ADD COLUMN(?: IF NOT EXISTS)? team_id\b", sql):
                found.add(name)
        return found

    def test_the_scan_finds_the_known_tables(self):
        found = self.tables_with_team_id()
        assert {"members", "standups", "kudos", "connect_matches", "daily_standup_threads"} <= found

    def test_each_is_purged_or_deliberately_kept(self):
        unaccounted = self.tables_with_team_id() - set(real_db.PURGED_TABLES) - set(real_db.KEPT_TABLES)
        assert not unaccounted, f"decide whether the purge deletes these: {sorted(unaccounted)}"

    def test_nothing_personal_is_on_the_keep_list(self):
        assert set(real_db.KEPT_TABLES) == {"installations", "workspace_history", "email_consents"}

    def test_pair_history_goes_with_its_programme(self):
        """connect_pair_history has no team_id, only user IDs keyed by programme."""
        assert "connect_pair_history" in real_db.PURGED_TABLES


# ── The sweep ───────────────────────────────────────────────────────────────


def candidate(team_id, reason, age, name="Workspace"):
    return {"team_id": team_id, "team_name": name, "deactivated_reason": reason, "deactivated_at": NOW - age}


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    fake.workspace_data_counts.return_value = {"members": 4, "standups": 9}
    fake.purge_workspace.return_value = {"members": 4, "standups": 9}
    monkeypatch.setitem(sys.modules, "src.core.db", fake)
    monkeypatch.setattr(importlib.import_module("src.core"), "db", fake)
    return fake


class TestGracePeriods:
    @pytest.mark.parametrize("reason", ["account_inactive", "token_revoked", "tokens_revoked", "app_uninstalled"])
    def test_gone_for_good_waits_a_day(self, reason):
        assert not retention.is_due(candidate("T1", reason, timedelta(hours=23)), NOW)
        assert retention.is_due(candidate("T1", reason, timedelta(hours=25)), NOW)

    @pytest.mark.parametrize("reason", ["invalid_auth", "not_authed"])
    def test_an_auth_failure_waits_a_week(self, reason):
        """It can be a token refresh problem, fixed by a reinstall."""
        assert not retention.is_due(candidate("T1", reason, timedelta(days=3)), NOW)
        assert not retention.is_due(candidate("T1", reason, timedelta(days=6, hours=23)), NOW)
        assert retention.is_due(candidate("T1", reason, timedelta(days=7, hours=1)), NOW)

    @pytest.mark.parametrize("reason", ["unknown", "team_disabled", "", None])
    def test_any_other_reason_is_never_purged(self, reason):
        assert not retention.is_due(candidate("T1", reason, timedelta(days=365)), NOW)

    def test_no_deactivation_time_is_never_purged(self):
        row = candidate("T1", "account_inactive", timedelta(days=30))
        row["deactivated_at"] = None
        assert not retention.is_due(row, NOW)


class TestSweep:
    def test_it_is_a_dry_run_unless_switched_on(self, fake_db, monkeypatch, caplog):
        monkeypatch.delenv("PURGE_INACTIVE_WORKSPACES", raising=False)
        fake_db.purge_candidates.return_value = [candidate("T1", "account_inactive", timedelta(days=30), "Alpha")]
        with caplog.at_level(logging.INFO):
            report = retention.sweep_inactive_workspaces(now=NOW)
        fake_db.purge_workspace.assert_not_called()
        assert report == [{"team_id": "T1", "team_name": "Alpha", "action": "would_purge", "rows": 13}]
        assert "dry run" in caplog.text.lower()
        assert "T1" in caplog.text and "Alpha" in caplog.text
        assert "members=4" in caplog.text and "standups=9" in caplog.text

    @pytest.mark.parametrize("value", ["", "0", "true", "yes", "2"])
    def test_only_exactly_one_switches_it_on(self, fake_db, monkeypatch, value):
        monkeypatch.setenv("PURGE_INACTIVE_WORKSPACES", value)
        fake_db.purge_candidates.return_value = [candidate("T1", "account_inactive", timedelta(days=30))]
        retention.sweep_inactive_workspaces(now=NOW)
        fake_db.purge_workspace.assert_not_called()

    def test_switched_on_it_purges_what_is_due(self, fake_db, monkeypatch):
        monkeypatch.setenv("PURGE_INACTIVE_WORKSPACES", "1")
        due = candidate("T1", "account_inactive", timedelta(days=30))
        fake_db.purge_candidates.return_value = [
            due,
            candidate("T2", "invalid_auth", timedelta(days=2)),
            candidate("T3", "unknown", timedelta(days=90)),
        ]
        report = retention.sweep_inactive_workspaces(now=NOW)
        fake_db.purge_workspace.assert_called_once_with("T1", expect_deactivated_at=due["deactivated_at"])
        assert [r["action"] for r in report] == ["purged"]

    def test_invalid_auth_is_purged_after_a_week(self, fake_db, monkeypatch):
        monkeypatch.setenv("PURGE_INACTIVE_WORKSPACES", "1")
        fake_db.purge_candidates.return_value = [candidate("T2", "invalid_auth", timedelta(days=8))]
        retention.sweep_inactive_workspaces(now=NOW)
        fake_db.purge_workspace.assert_called_once()

    def test_a_workspace_that_came_back_is_reported_skipped(self, fake_db, monkeypatch):
        """purge_workspace re-checks under a row lock and returns None."""
        monkeypatch.setenv("PURGE_INACTIVE_WORKSPACES", "1")
        fake_db.purge_candidates.return_value = [candidate("T1", "account_inactive", timedelta(days=30))]
        fake_db.purge_workspace.return_value = None
        report = retention.sweep_inactive_workspaces(now=NOW)
        assert report == [{"team_id": "T1", "team_name": "Workspace", "action": "skipped", "rows": 0}]

    def test_only_inactive_unpurged_workspaces_are_candidates(self, cursor):
        real_db.purge_candidates()
        sql = cursor.calls[0][0]
        assert "NOT active" in sql and "purged_at IS NULL" in sql and "deactivated_at IS NOT NULL" in sql

    def test_one_failure_does_not_stop_the_rest(self, fake_db, monkeypatch):
        monkeypatch.setenv("PURGE_INACTIVE_WORKSPACES", "1")
        fake_db.purge_candidates.return_value = [
            candidate("T1", "account_inactive", timedelta(days=30)),
            candidate("T2", "account_inactive", timedelta(days=30)),
        ]
        fake_db.purge_workspace.side_effect = [RuntimeError("boom"), {"members": 1}]
        report = retention.sweep_inactive_workspaces(now=NOW)
        assert [r["action"] for r in report] == ["failed", "purged"]

    def test_running_it_twice_purges_once(self, fake_db, monkeypatch):
        monkeypatch.setenv("PURGE_INACTIVE_WORKSPACES", "1")
        row = candidate("T1", "account_inactive", timedelta(days=30))
        fake_db.purge_candidates.side_effect = [[row], []]
        retention.sweep_inactive_workspaces(now=NOW)
        assert retention.sweep_inactive_workspaces(now=NOW) == []
        assert fake_db.purge_workspace.call_count == 1


class TestScheduling:
    def test_both_jobs_run_nightly(self):
        with patch.dict(sys.modules, {"src.core.db": MagicMock()}):
            built = scheduler.build_scheduler([])
        history = built.get_job("workspace_history_refresh")
        sweep = built.get_job("inactive_workspace_sweep")
        assert history is not None and sweep is not None
        for job in (history, sweep):
            assert ":" not in job.id, "a namespaced id would be removed by module job reconciliation"

    def test_a_failing_refresh_does_not_raise_into_the_scheduler(self, fake_db):
        fake_db.record_all_workspace_history.side_effect = RuntimeError("db down")
        scheduler._refresh_workspace_history()

    def test_a_failing_sweep_does_not_raise_into_the_scheduler(self, fake_db):
        fake_db.purge_candidates.side_effect = RuntimeError("db down")
        scheduler._sweep_inactive_workspaces()


# ── Slack telling us the app was removed ────────────────────────────────────


def registered_events():
    from src.modules.standup import handlers

    events = {}
    app = MagicMock()

    def event(name, *args, **kwargs):
        def register(fn):
            events[name] = fn
            return fn

        return register

    app.event.side_effect = event
    handlers.register_handlers(app)
    return events


@pytest.fixture
def uninstall_side_effects(monkeypatch):
    calls = []
    monkeypatch.setattr("src.core.alerts.departed", lambda t: calls.append(("departed", t)))
    monkeypatch.setattr("src.core.mailer.farewell", lambda t: calls.append(("farewell", t)))
    monkeypatch.setattr("src.core.analytics.capture", lambda *a, **k: calls.append(("capture", a[1])))
    return calls


class TestUninstallEvents:
    @pytest.mark.parametrize("event_name", ["tokens_revoked", "app_uninstalled"])
    def test_it_purges_straight_away_with_the_event_as_reason(self, fake_db, uninstall_side_effects, event_name):
        fake_db.get_installation.return_value = {"team_id": "T1", "active": True, "purged_at": None}
        registered_events()[event_name]({"team_id": "T1"}, MagicMock())
        fake_db.purge_workspace.assert_called_once_with("T1", reason=event_name)
        assert [c[0] for c in uninstall_side_effects] == ["departed", "farewell", "capture"]

    @pytest.mark.parametrize("event_name", ["tokens_revoked", "app_uninstalled"])
    def test_the_second_event_of_the_pair_does_nothing(self, fake_db, uninstall_side_effects, event_name):
        """Slack sends both. The second must not alert or email about an empty workspace."""
        fake_db.get_installation.return_value = {"team_id": "T1", "active": False, "purged_at": NOW}
        registered_events()[event_name]({"team_id": "T1"}, MagicMock())
        fake_db.purge_workspace.assert_not_called()
        assert uninstall_side_effects == []

    def test_the_old_delete_is_gone(self):
        assert not hasattr(real_db, "delete_installation")


# ── Coming back after a purge ───────────────────────────────────────────────


class TestReinstallAfterPurge:
    def test_it_counts_as_a_new_install(self, cursor):
        """The welcome DM and the email offer go to new installs only."""
        cursor._fetchone = [(True,)]
        assert real_db.save_installation("T1", "Name", "xoxb", "B1", "A1", "U1") is True
        sql, params = cursor.calls[0]
        assert "purged_at IS NOT NULL" in sql.split("RETURNING", 1)[1]
        assert params[0] == "T1"

    def test_it_clears_the_purge_and_restarts_the_clock(self, cursor):
        cursor._fetchone = [(True,)]
        real_db.save_installation("T1", "Name", "xoxb", "B1", "A1", "U1")
        sql = cursor.calls[0][0]
        assert "purged_at = NULL" in sql
        assert "WHEN installations.purged_at IS NOT NULL THEN NOW()" in sql
