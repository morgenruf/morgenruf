"""Polls, pulse, celebrations and watercooler over MCP: read only, and nothing anonymous leaks."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import src.modules.celebrations.db as cdb
import src.modules.pulse.db as pulse_db
from src.core.mcp_tools import module_tools
from src.modules.celebrations import jobs as celebration_jobs
from src.modules.celebrations.mcp import tools as celebration_tools
from src.modules.polls.mcp import tools as poll_tools
from src.modules.pulse.mcp import tools as pulse_tools
from src.modules.watercooler.mcp import tools as watercooler_tools

from tests.support import patch_modules


def call(tools, name, args=None, team_id="T1"):
    return next(t for t in tools() if t["name"] == name)["handler"](args or {}, team_id)


@pytest.fixture(autouse=True)
def members(monkeypatch):
    monkeypatch.setattr(
        "src.core.db.get_all_members",
        lambda team_id: [
            {"user_id": "U1", "real_name": "Priya", "email": "priya@example.com"},
            {"user_id": "U2", "real_name": "Sam", "email": None},
        ],
    )


# ── Polls ───────────────────────────────────────────────────────────────────


def poll(**over):
    return {
        "id": 7,
        "team_id": "T1",
        "created_by": "U1",
        "channel_id": "C1",
        "question": "Lunch?",
        "options": ["Pizza", "Sushi"],
        "anonymous": False,
        "multiple": False,
        "hide_results": False,
        "closes_at": None,
        "closed_at": None,
        "created_at": datetime.now(timezone.utc),
        **over,
    }


@pytest.fixture
def polls(monkeypatch):
    state = {"poll": poll(), "voters": {0: ["U1"], 1: ["U2"]}}
    monkeypatch.setattr("src.modules.polls.db.get_poll", lambda poll_id: state["poll"])
    monkeypatch.setattr("src.modules.polls.db.tally", lambda poll_id: [3, 1])

    def voters(poll_id):
        if state["poll"]["anonymous"]:
            raise AssertionError("voters read for an anonymous poll")
        return state["voters"]

    monkeypatch.setattr("src.modules.polls.db.voters", voters)
    return state


def test_named_poll_shows_who_picked_what(polls):
    out = call(poll_tools, "get_poll_results", {"poll_id": 7})
    assert out["options"][0] == {
        "text": "Pizza",
        "votes": 3,
        "percent": 75.0,
        "voters": [{"user_id": "U1", "name": "Priya", "email": "priya@example.com"}],
    }
    assert out["options"][1]["voters"] == [{"user_id": "U2", "name": "Sam"}]


def test_anonymous_poll_returns_counts_and_never_a_name(polls):
    polls["poll"] = poll(anonymous=True)
    out = call(poll_tools, "get_poll_results", {"poll_id": 7})
    assert [o["votes"] for o in out["options"]] == [3, 1]
    assert all("voters" not in o for o in out["options"])
    assert "Priya" not in str(out) and "U1" not in str(out["options"])


def test_hidden_results_stay_hidden_while_the_poll_is_open(polls):
    polls["poll"] = poll(hide_results=True)
    out = call(poll_tools, "get_poll_results", {"poll_id": 7})
    assert out["results_hidden_until_close"] is True
    assert all(o["votes"] is None and "voters" not in o for o in out["options"])


def test_another_workspaces_poll_is_not_found(polls):
    polls["poll"] = poll(team_id="T_OTHER")
    assert call(poll_tools, "get_poll_results", {"poll_id": 7}) == {"error": "Poll not found."}


def test_poll_id_is_required():
    assert "list_polls" in call(poll_tools, "get_poll_results")["error"]


def test_list_polls_keeps_the_window(monkeypatch):
    old = poll(id=1, created_at=datetime.now(timezone.utc) - timedelta(days=40), counts=[1])
    new = poll(id=2, closed_at=datetime.now(timezone.utc), counts=[2, 3])
    monkeypatch.setattr("src.modules.polls.db.list_polls", lambda team_id, limit: [new, old])
    out = call(poll_tools, "list_polls", {"days": 30})
    assert [p["id"] for p in out] == [2]
    assert out[0]["status"] == "closed" and out[0]["total_votes"] == 5
    assert out[0]["created_by"]["name"] == "Priya"


# ── Pulse ───────────────────────────────────────────────────────────────────


def test_pulse_results_respect_the_group_floors(monkeypatch):
    today = date.today()
    rows = [
        # Open: nothing from the answers.
        {"sent_on": today, "respondents": 12, "invited": 20, "open": True, "hidden": True, "mood_avg": 4.0},
        # Too few to show at all.
        {"sent_on": today - timedelta(days=7), "respondents": 3, "invited": 20, "hidden": False, "mood_avg": 2.0},
        # An average, but no breakdown or eNPS under ten.
        {
            "sent_on": today - timedelta(days=14),
            "respondents": 6,
            "invited": 20,
            "hidden": False,
            "mood_avg": 3.5,
            "mood_dist": [0, 1, 2, 2, 1],
            "enps": 10,
        },
    ]
    monkeypatch.setattr("src.modules.pulse.db.trend", lambda team_id, limit: list(reversed(rows)))
    out = call(pulse_tools, "get_pulse_results")
    by_size = {r["respondents"]: r for r in out["rounds"]}
    assert "mood_avg" not in by_size[12] and by_size[12]["open"] is True
    assert "mood_avg" not in by_size[3] and by_size[3]["hidden"] is True
    assert by_size[6]["mood_avg"] == 3.5
    assert "mood_dist" not in by_size[6] and "enps" not in by_size[6]


def test_pulse_survey_lists_its_questions(monkeypatch):
    monkeypatch.setattr("src.modules.pulse.db.get_program", lambda team_id: pulse_db.default_program(team_id))
    monkeypatch.setattr(
        "src.modules.pulse.db.trend",
        lambda team_id, limit: [{"sent_on": date(2026, 10, 8), "respondents": 5, "invited": 10}],
    )
    (survey,) = call(pulse_tools, "list_pulse_surveys")
    assert [q["id"] for q in survey["questions"]] == ["mood", "enps"]
    assert survey["last_response_rate"] == 50.0
    assert survey["cadence"] == "weekly, Friday 14:00 UTC"


# ── Celebrations ────────────────────────────────────────────────────────────


@pytest.fixture
def celebrations(monkeypatch):
    settings = {**cdb.default_settings("T1"), "timezone": "UTC", "channel_id": "C1"}
    monkeypatch.setattr("src.modules.celebrations.db.get_settings", lambda team_id: settings)
    monkeypatch.setattr("src.core.db.get_working_days", lambda team_id: "mon,tue,wed,thu,fri,sat,sun")
    monkeypatch.setattr("src.core.db.list_holidays", lambda team_id: [])
    return settings


def test_upcoming_birthday_carries_no_birth_year(celebrations, monkeypatch):
    soon = celebration_jobs.local_today("UTC") + timedelta(days=5)
    monkeypatch.setattr(
        "src.modules.celebrations.db.celebrants",
        lambda team_id: [
            {
                "user_id": "U1",
                "birth_month": soon.month,
                "birth_day": soon.day,
                "start_date": None,
                "real_name": "Priya",
            }
        ],
    )
    monkeypatch.setattr("src.modules.celebrations.db.posted_keys", lambda team_id, since: set())
    (row,) = call(celebration_tools, "get_upcoming_celebrations", {"days": 10})
    assert row["kind"] == "birthday" and row["date"] == soon and row["posted"] is False
    assert row["email"] == "priya@example.com"
    assert "birth_month" not in row and "years" not in row


def test_celebration_history(celebrations, monkeypatch):
    day = date(2026, 10, 1)
    monkeypatch.setattr(
        "src.modules.celebrations.db.recent_posts",
        lambda team_id, since, limit: [
            {
                "kind": "anniversary",
                "celebration_date": day,
                "posted_on": day,
                "channel_id": "C1",
                "user_ids": ["U2"],
                "ts": "1.2",
            }
        ],
    )
    (row,) = call(celebration_tools, "get_celebration_history")
    assert row["people"] == [{"user_id": "U2", "name": "Sam"}] and row["posted"] is True


# ── Watercooler ─────────────────────────────────────────────────────────────


def test_watercooler_topics_resolve_their_question(monkeypatch):
    from src.modules.watercooler import bank

    q = bank.QUESTIONS[0]
    monkeypatch.setattr(
        "src.modules.watercooler.db.recent_posts",
        lambda team_id, since, limit: [
            {"channel_id": "C1", "posted_on": date(2026, 10, 1), "question_ref": f"b:{q.key}", "ts": "1.1"},
            {"channel_id": "C1", "posted_on": date(2026, 9, 29), "question_ref": "c:4", "ts": "1.0"},
        ],
    )
    monkeypatch.setattr("src.modules.watercooler.db.list_questions", lambda team_id: [{"id": 4, "text": "Best snack?"}])
    out = call(watercooler_tools, "list_watercooler_topics")
    assert [(t["question"], t["category"]) for t in out] == [(q.text, q.category), ("Best snack?", "custom")]


# ── The module gate, with the real specs ────────────────────────────────────


class FakeDb:
    def __init__(self, settings):
        self._settings = settings

    def granted_scopes(self, team_id):
        return ()

    def module_settings(self, team_id):
        return self._settings


def _registry(settings):
    import types

    from src.modules.celebrations import MODULE as celebrations_module
    from src.modules.polls import MODULE as polls_module
    from src.modules.pulse import MODULE as pulse_module
    from src.modules.watercooler import MODULE as watercooler_module

    mods = types.ModuleType("src.modules")
    mods.REGISTRY = [polls_module, pulse_module, celebrations_module, watercooler_module]
    return patch_modules({"src.modules": mods, "src.core.db": FakeDb(settings)})


NEW_TOOLS = {
    "list_polls",
    "get_poll_results",
    "list_pulse_surveys",
    "get_pulse_results",
    "get_upcoming_celebrations",
    "get_celebration_history",
    "list_watercooler_topics",
}


def test_tools_appear_when_the_modules_are_on(monkeypatch):
    monkeypatch.delenv("MORGENRUF_MODULES", raising=False)
    on = {"polls": True, "pulse": True, "celebrations": True, "watercooler": True}
    with _registry(on):
        assert set(module_tools("T1")) == NEW_TOOLS


def test_tools_are_hidden_when_the_modules_are_off(monkeypatch):
    monkeypatch.delenv("MORGENRUF_MODULES", raising=False)
    off = {"polls": False, "pulse": False, "celebrations": False, "watercooler": False}
    with _registry(off):
        assert module_tools("T1") == {}
