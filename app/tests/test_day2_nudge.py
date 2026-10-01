"""One Slack DM for workspaces that installed and never started a standup.

Two days after install the installer gets one DM with the quick start
button. Never by email, never twice, and never to anyone but the installer.
The record is written before sending, so a crash cannot double-send.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
import src.core.scheduler as scheduler
from src.core import activation

ROW = {"team_id": "T1", "bot_token": "xoxb-1", "installed_by_user_id": "U1"}


@pytest.fixture(autouse=True)
def _stored_token_is_fresh(monkeypatch):
    """Token refresh reads the database; these tests use the stored token."""
    monkeypatch.setattr(activation, "_bot_token", lambda team_id, stored: stored)


def test_nudges_the_installer_once_with_the_button():
    client = MagicMock()
    client.conversations_open.return_value = {"channel": {"id": "D1"}}
    with (
        patch("src.core.db.workspaces_without_standup", return_value=[ROW]),
        patch("src.core.db.record_install_email", return_value=True) as record,
        patch.object(activation, "WebClient", return_value=client) as web,
    ):
        assert activation.send_day2_nudges() == (1, 0)
    record.assert_called_once_with("T1", "nudge:day2")
    web.assert_called_once_with(token="xoxb-1")
    client.conversations_open.assert_called_once_with(users="U1")
    kwargs = client.chat_postMessage.call_args.kwargs
    assert kwargs["channel"] == "D1"
    assert any(b.get("block_id") == "quickstart" for b in kwargs["blocks"])


def test_already_recorded_means_not_sent_again():
    client = MagicMock()
    with (
        patch("src.core.db.workspaces_without_standup", return_value=[ROW]),
        patch("src.core.db.record_install_email", return_value=False),
        patch.object(activation, "WebClient", return_value=client),
    ):
        assert activation.send_day2_nudges() == (0, 1)
    client.chat_postMessage.assert_not_called()


def test_a_removed_workspace_is_skipped_without_raising():
    client = MagicMock()
    client.conversations_open.side_effect = Exception("account_inactive")
    with (
        patch("src.core.db.workspaces_without_standup", return_value=[ROW]),
        patch("src.core.db.record_install_email", return_value=True),
        patch.object(activation, "WebClient", return_value=client),
    ):
        assert activation.send_day2_nudges() == (0, 1)


def test_one_failing_workspace_does_not_stop_the_next():
    good = MagicMock()
    good.conversations_open.return_value = {"channel": {"id": "D2"}}
    bad = MagicMock()
    bad.conversations_open.side_effect = Exception("account_inactive")
    rows = [ROW, {**ROW, "team_id": "T2", "bot_token": "xoxb-2", "installed_by_user_id": "U2"}]
    with (
        patch("src.core.db.workspaces_without_standup", return_value=rows),
        patch("src.core.db.record_install_email", return_value=True),
        patch.object(activation, "WebClient", side_effect=[bad, good]),
    ):
        assert activation.send_day2_nudges() == (1, 1)


def test_internal_workspaces_are_never_nudged(monkeypatch):
    monkeypatch.setenv("MORGENRUF_INTERNAL_TEAMS", "T1")
    client = MagicMock()
    with (
        patch("src.core.db.workspaces_without_standup", return_value=[ROW]),
        patch("src.core.db.record_install_email") as record,
        patch.object(activation, "WebClient", return_value=client),
    ):
        assert activation.send_day2_nudges() == (0, 1)
    record.assert_not_called()
    client.chat_postMessage.assert_not_called()


def test_the_hourly_job_also_runs_the_invite_sweep():
    with (
        patch("src.core.activation.send_day2_nudges") as nudges,
        patch("src.core.standup_invites.sweep_waiting_standups") as sweep,
    ):
        scheduler._send_day2_nudges()
    nudges.assert_called_once()
    sweep.assert_called_once()


def test_a_failing_sweep_does_not_stop_the_nudges():
    with (
        patch("src.core.activation.send_day2_nudges") as nudges,
        patch("src.core.standup_invites.sweep_waiting_standups", side_effect=RuntimeError("db down")),
    ):
        scheduler._send_day2_nudges()
    nudges.assert_called_once()


def test_no_installer_is_skipped():
    with (
        patch("src.core.db.workspaces_without_standup", return_value=[{**ROW, "installed_by_user_id": None}]),
        patch("src.core.db.record_install_email") as record,
    ):
        assert activation.send_day2_nudges() == (0, 1)
    record.assert_not_called()


def test_a_purged_row_with_no_token_is_skipped():
    with (
        patch("src.core.db.workspaces_without_standup", return_value=[{**ROW, "bot_token": ""}]),
        patch("src.core.db.record_install_email") as record,
    ):
        assert activation.send_day2_nudges() == (0, 1)
    record.assert_not_called()


# ── Database ────────────────────────────────────────────────────────────────


def test_candidates_are_live_installs_with_no_standup_and_no_nudge(fake_cursor_db):
    from src.core import db

    db.workspaces_without_standup(hours=48)
    sql, params = fake_cursor_db.calls[0]
    assert "i.active" in sql and "i.purged_at IS NULL" in sql
    assert "NOT EXISTS (SELECT 1 FROM standup_schedules" in sql
    assert "kind = 'nudge:day2'" in sql
    assert "INTERVAL '14 days'" in sql
    assert params == (48,)


def test_record_install_email_says_whether_it_wrote(fake_cursor_db):
    from src.core import db

    fake_cursor_db._fetchone = [(1,), None]
    assert db.record_install_email("T1", "nudge:day2") is True
    assert db.record_install_email("T1", "nudge:day2") is False
    sql = fake_cursor_db.calls[0][0]
    assert "ON CONFLICT (team_id, kind) DO NOTHING RETURNING 1" in sql


# ── Scheduling ──────────────────────────────────────────────────────────────


def test_it_runs_hourly_on_one_replica():
    with patch.dict(sys.modules, {"src.core.db": MagicMock()}):
        built = scheduler.build_scheduler([])
    job = built.get_job("day2_nudge")
    assert job is not None
    assert job.executor == scheduler.BULK_EXECUTOR
    assert str(job.trigger.fields[job.trigger.FIELD_NAMES.index("minute")]) == "17"
    assert str(job.trigger.fields[job.trigger.FIELD_NAMES.index("hour")]) == "*"


def test_a_failing_run_does_not_raise_into_the_scheduler():
    with patch("src.core.db.workspaces_without_standup", side_effect=RuntimeError("db down")):
        scheduler._send_day2_nudges()
