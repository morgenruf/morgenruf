"""The Monday usage report to the operator's alert channel.

Counts and workspace names only, never a person. Internal workspaces
(MORGENRUF_INTERNAL_TEAMS) are left out, so the number says whether outside
teams use it.
"""

from __future__ import annotations

import sys
from datetime import date
from unittest.mock import MagicMock, patch

import src.core.scheduler as scheduler
from src.core import usage_report


def _row(team, people, **kw):
    base = {
        "team_id": team,
        "team_name": team.lower(),
        "active": True,
        "people_7d": people,
        "answers_7d": people * 3,
        "kudos_7d": 0,
        "has_standup": people > 0,
        "install_source": None,
        "installed_this_week": False,
        "removed_this_week": False,
        "activated_this_week": False,
        "nudged": False,
    }
    return {**base, **kw}


def test_internal_workspaces_are_left_out():
    text = usage_report.build([_row("T1", 6), _row("TINT", 20)], internal={"TINT"})
    assert "Weekly active people: 6" in text
    assert "tint" not in text


def test_groups_active_trying_and_idle():
    text = usage_report.build([_row("T1", 6), _row("T2", 1), _row("T3", 0)], internal=set())
    assert "Active teams (3+ people): t1 6" in text
    assert "Trying (1 to 2 people): t2 1" in text
    assert "no standup yet: t3" in text


def test_a_standup_with_no_answers_is_its_own_group():
    text = usage_report.build([_row("T1", 0, has_standup=True)], internal=set())
    assert "Standup set, no answers this week: t1" in text
    assert "no standup yet" not in text


def test_nudged_workspaces_are_marked():
    text = usage_report.build([_row("T1", 0), _row("T2", 0, nudged=True)], internal=set())
    assert "no standup yet: t1, t2 (nudged: t2)" in text


def test_the_headline_counts():
    rows = [
        _row("T1", 6, activated_this_week=True),
        _row("T2", 0),
        _row("T3", 0, active=False, removed_this_week=True),
    ]
    text = usage_report.build(rows, internal=set(), today=date(2026, 10, 12))
    assert text.splitlines()[0] == "*Morgenruf, week to Mon 12 Oct*"
    assert "Outside workspaces: 2 installed, 1 activated this week, 1 removed" in text
    assert "Removed this week: t3" in text


def test_a_removed_workspace_is_not_counted_as_active_or_idle():
    text = usage_report.build([_row("T3", 0, active=False, removed_this_week=True)], internal=set())
    assert "no standup yet" not in text


def test_sources_count_new_installs_and_unknown_is_direct():
    rows = [
        _row("T1", 0, installed_this_week=True, install_source="linkedin"),
        _row("T2", 0, installed_this_week=True),
    ]
    assert "linkedin 1" in usage_report.build(rows, internal=set())
    assert "direct 1" in usage_report.build(rows, internal=set())


def test_workspace_names_are_escaped():
    text = usage_report.build([_row("T1", 6, team_name="<!channel>")], internal=set())
    assert "<!channel>" not in text


def test_empty_week_still_posts_a_line():
    assert "Weekly active people: 0" in usage_report.build([], internal=set())


def test_a_row_left_half_empty_by_a_purge_does_not_crash():
    row = _row("T1", 0, team_name=None, people_7d=None, answers_7d=None, has_standup=None)
    text = usage_report.build([row], internal=set())
    assert "T1" in text


def test_internal_teams_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("MORGENRUF_INTERNAL_TEAMS", " T1, T2 ,,")
    assert usage_report._internal_teams() == {"T1", "T2"}
    monkeypatch.delenv("MORGENRUF_INTERNAL_TEAMS")
    assert usage_report._internal_teams() == set()


def test_post_weekly_sends_the_report_to_the_alert_channel(monkeypatch):
    monkeypatch.setenv("MORGENRUF_INTERNAL_TEAMS", "TINT")
    with (
        patch("src.core.db.usage_report_rows", return_value=[_row("T1", 4), _row("TINT", 9)]),
        patch("src.core.alerts.notify", return_value=True) as notify,
    ):
        assert usage_report.post_weekly() is True
    text = notify.call_args.args[0]
    assert "Weekly active people: 4" in text and "tint" not in text


# ── Database ────────────────────────────────────────────────────────────────


def test_the_rows_query_reads_counts_not_people(fake_cursor_db):
    from src.core import db

    db.usage_report_rows()
    sql = fake_cursor_db.calls[0][0]
    assert "FROM installations i" in sql
    assert "workspace_history" in sql
    assert "INTERVAL '7 days'" in sql
    assert "nudge:day2" in sql
    columns_read = sql.lower().replace("install_emails", "")
    for column in ("email", "real_name", "yesterday", "blockers", "message"):
        assert column not in columns_read, column


# ── Scheduling ──────────────────────────────────────────────────────────────


def test_it_runs_on_monday_morning():
    with patch.dict(sys.modules, {"src.core.db": MagicMock()}):
        built = scheduler.build_scheduler([])
    job = built.get_job("weekly_usage_report")
    assert job is not None and job.executor == scheduler.BULK_EXECUTOR
    fields = {name: str(job.trigger.fields[i]) for i, name in enumerate(job.trigger.FIELD_NAMES)}
    assert (fields["day_of_week"], fields["hour"], fields["minute"]) == ("mon", "7", "30")


def test_a_failing_report_does_not_raise_into_the_scheduler():
    with patch("src.core.db.usage_report_rows", side_effect=RuntimeError("db down")):
        scheduler._post_usage_report()
