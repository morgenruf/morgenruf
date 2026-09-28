"""An assistant can read member profiles over MCP, and only read them."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

import pytest
import src.modules.mcp.http as mcp_http


@pytest.fixture
def db(monkeypatch):
    fake = MagicMock()
    fake.list_member_profiles.return_value = [
        {
            "user_id": "U1",
            "birth_month": 3,
            "birth_day": 4,
            "start_date": date(2023, 3, 1),
            "role": "Eng",
            "location": "Berlin",
            "ask_me_about": "Rust",
            "celebrate": False,
            "updated_by": "U_ADMIN",
            "nudged_at": None,
            "left_at": None,
        },
        {"user_id": "U2", "birth_month": None, "birth_day": None, "celebrate": True},
    ]
    fake.get_all_members.return_value = [{"user_id": "U1", "real_name": "Priya"}]
    monkeypatch.setattr(mcp_http, "db", fake)
    return fake


def test_the_tool_is_advertised_over_http_and_stdio():
    assert "get_member_profiles" in {t["name"] for t in mcp_http.TOOLS}


def test_reads_profile_fields(db):
    out = json.loads(mcp_http._call_tool("get_member_profiles", {}, "T1"))
    first = out[0]
    assert first == {
        "user_id": "U1",
        "name": "Priya",
        "role": "Eng",
        "location": "Berlin",
        "ask_me_about": "Rust",
        "birthday": "03-04",
        "start_date": "2023-03-01",
        "celebrate": False,
    }
    assert out[1]["birthday"] is None
    # The audit trail and job bookkeeping are not profile fields.
    assert "updated_by" not in first and "left_at" not in first
    db.list_member_profiles.assert_called_once_with("T1")  # people who left are excluded


def test_one_member(db):
    out = json.loads(mcp_http._call_tool("get_member_profiles", {"user_id": "U2"}, "T1"))
    assert [p["user_id"] for p in out] == ["U2"]
    assert mcp_http._call_tool("get_member_profiles", {"user_id": "U9"}, "T1") == "No profile found for that member."


def test_it_never_writes(db):
    mcp_http._call_tool("get_member_profiles", {}, "T1")
    db.upsert_member_profile.assert_not_called()
