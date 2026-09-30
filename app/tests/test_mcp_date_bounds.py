"""MCP tools never read more than a year of standups.

get_standups with from_date=2000-01-01, or search_standups with days=100000,
loaded a workspace's whole history into memory, the same failure as the
reports page before 1.9.1.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
import src.modules.mcp.http as mcp_http


@pytest.fixture
def db(monkeypatch):
    fake = MagicMock()
    fake.get_standups.return_value = []
    fake.get_participation_stats.return_value = {}
    fake.workspace_local_today.return_value = date.today()
    monkeypatch.setattr(mcp_http, "db", fake)
    return fake


def test_an_ancient_from_date_is_moved_up_to_a_year(db):
    mcp_http._call_tool("get_standups", {"from_date": "2000-01-01"}, "T1")
    from_date = date.fromisoformat(db.get_standups.call_args.kwargs["from_date"])
    assert from_date == date.today() - timedelta(days=mcp_http.MAX_DAYS - 1)


def test_a_recent_from_date_is_kept(db):
    wanted = (date.today() - timedelta(days=3)).isoformat()
    mcp_http._call_tool("get_standups", {"from_date": wanted}, "T1")
    assert db.get_standups.call_args.kwargs["from_date"] == wanted


def test_a_malformed_from_date_falls_back_to_a_week(db):
    mcp_http._call_tool("get_standups", {"from_date": "0002"}, "T1")
    assert db.get_standups.call_args.kwargs["from_date"] == (date.today() - timedelta(days=7)).isoformat()


@pytest.mark.parametrize("tool", ["search_standups", "get_blockers", "get_participation"])
@pytest.mark.parametrize(("given", "used"), [(100000, 365), (-5, 1), ("lots", None)])
def test_days_are_clamped(db, tool, given, used):
    mcp_http._call_tool(tool, {"days": given, "query": "x"}, "T1")
    target = db.get_participation_stats if tool == "get_participation" else db.get_standups
    days = target.call_args.kwargs["days"]
    assert 1 <= days <= 365
    if used is not None:
        assert days == used


SYDNEY_TODAY = date(2026, 9, 30)


@pytest.mark.parametrize("tool", ["get_today_standups", "get_workspace_summary"])
def test_today_is_the_workspaces_local_day(db, tool):
    """At 23:30 UTC a Sydney team is already on the next day; its answers are filed there."""
    db.workspace_local_today.return_value = SYDNEY_TODAY
    mcp_http._call_tool(tool, {}, "T1")
    kwargs = db.get_standups.call_args_list[0].kwargs
    assert kwargs["from_date"] == kwargs["to_date"] == "2026-09-30"


def test_default_range_ends_on_the_local_day(db):
    db.workspace_local_today.return_value = SYDNEY_TODAY
    mcp_http._call_tool("get_standups", {}, "T1")
    assert db.get_standups.call_args.kwargs["to_date"] == "2026-09-30"
    assert db.get_standups.call_args.kwargs["from_date"] == "2026-09-23"
