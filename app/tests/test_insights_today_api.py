"""The Today endpoint, assembled over faked queries.

The queries themselves are SQL and are exercised against a real database; what
is worth pinning here is the shape the page is promised and the fact that a
workspace missing half the features still gets a usable answer.

Imports happen inside the fixtures because src.core.dashboard drags the whole
core in at import time, and other test modules in this suite stub parts of it.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

MEMBERS = [
    {"user_id": "U1", "real_name": "Ada", "tz": "UTC", "active": True, "on_vacation": False},
    {"user_id": "U2", "real_name": "Bob", "tz": "UTC", "active": True, "on_vacation": False},
    {"user_id": "U3", "real_name": "Away", "tz": "UTC", "active": True, "on_vacation": True},
    {"user_id": "U4", "real_name": "Left", "tz": "UTC", "active": False, "on_vacation": False},
]

SCHEDULES = [
    {
        "id": 1,
        "name": "Daily",
        "schedule_time": "09:00",
        "schedule_tz": "UTC",
        "schedule_days": "*",
        "participants": ["U1", "U2", "U3", "U4"],
        "active": True,
    }
]

RESPONSES = [
    {
        "user_id": "U1",
        "real_name": "Ada",
        "standup_date": dt.date(2026, 9, 14),
        "yesterday": "shipped the importer",
        "today": "today page",
        "blockers": "waiting on infra",
        "has_blockers": True,
        "mood": "😐",
        "submitted_at": dt.datetime(2026, 9, 14, 8, 30, tzinfo=dt.timezone.utc),
        "schedule_id": 1,
    }
]

KUDOS = [
    {
        "id": 7,
        "from_user": "U2",
        "to_user": "U1",
        "message": "saved the release",
        "created_at": dt.datetime(2026, 9, 14, 9, 0, tzinfo=dt.timezone.utc),
        "from_name": "Bob",
        "to_name": "Ada",
    }
]

PROGRAM = {
    "program_id": 3,
    "name": "Coffee chats",
    "interval_weeks": 1,
    "next_scheduled": dt.datetime(2026, 9, 21, 10, 0, tzinfo=dt.timezone.utc),
    "last_round": dt.datetime(2026, 9, 14, 10, 0, tzinfo=dt.timezone.utc),
}


@pytest.fixture()
def call():
    """Return a caller that runs the endpoint with the given fake query results."""
    import src.modules.insights.db as idb
    from flask import Flask
    from src.modules.insights import MODULE

    def run(*, responses=RESPONSES, schedules=SCHEDULES, kudos=KUDOS, program=PROGRAM, members=MEMBERS):
        flask_app = Flask(__name__)
        flask_app.config["TESTING"] = True
        flask_app.config["SECRET_KEY"] = "test-secret"
        with patch("src.core.roster.db") as roster_db:
            roster_db.get_all_members.return_value = members
            MODULE.register_routes(flask_app)
            client = flask_app.test_client()
            with client.session_transaction() as sess:
                sess["team_id"] = "T1"
                sess["user_id"] = "U1"
            with (
                patch.object(idb, "todays_standups", return_value=list(responses)),
                patch.object(idb, "active_schedules", return_value=list(schedules)),
                patch.object(idb, "recent_kudos", return_value=list(kudos)),
                patch.object(idb, "connect_program_timing", return_value=program),
            ):
                return client.get("/dashboard/api/today")

    return run


def test_it_needs_a_session():
    from flask import Flask
    from src.modules.insights import MODULE

    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = "test-secret"
    MODULE.register_routes(flask_app)
    assert flask_app.test_client().get("/dashboard/api/today").status_code == 401


def test_the_payload_has_every_section_the_page_needs(call):
    body = call().get_json()
    assert set(body) == {"date", "counts", "responses", "awaiting", "blocked", "kudos", "next_chat"}


def test_todays_answers_come_back_with_their_mood_and_text(call):
    row = call().get_json()["responses"][0]
    assert row["user_id"] == "U1"
    assert row["today"] == "today page"
    assert row["mood"] == "😐"
    assert row["submitted_at"] == "2026-09-14T08:30:00+00:00"


def test_people_away_or_deactivated_are_never_waited_on(call):
    """U3 is on vacation and U4 has left, so only U2 still owes a standup."""
    assert [r["user_id"] for r in call().get_json()["awaiting"]] == ["U2"]


def test_awaiting_carries_the_name_so_the_page_need_not_ask_slack(call):
    assert call().get_json()["awaiting"][0]["real_name"] == "Bob"


def test_blockers_are_surfaced_with_their_text(call):
    blocked = call().get_json()["blocked"]
    assert [(r["user_id"], r["blockers"]) for r in blocked] == [("U1", "waiting on infra")]


def test_the_counts_describe_the_morning(call):
    assert call().get_json()["counts"] == {
        "expected": 2,
        "answered": 1,
        "awaiting": 1,
        "blocked": 1,
    }


def test_two_standups_from_one_person_count_as_one_answer(call):
    twice = RESPONSES + [dict(RESPONSES[0], schedule_id=2, has_blockers=False, blockers=None)]
    assert call(responses=twice).get_json()["counts"]["answered"] == 1


def test_recent_kudos_name_both_sides(call):
    kudo = call().get_json()["kudos"][0]
    assert (kudo["from_name"], kudo["to_name"], kudo["message"]) == ("Bob", "Ada", "saved the release")
    assert kudo["created_at"] == "2026-09-14T09:00:00+00:00"


def test_the_next_coffee_chat_is_a_plain_date(call):
    assert call().get_json()["next_chat"] == {
        "program_id": 3,
        "name": "Coffee chats",
        "date": "2026-09-21",
    }


def test_a_workspace_without_connect_gets_a_null_rather_than_an_error(call):
    assert call(program=None).get_json()["next_chat"] is None


def test_an_empty_workspace_still_renders(call):
    body = call(responses=[], schedules=[], kudos=[], program=None, members=[]).get_json()
    assert body["counts"] == {"expected": 0, "answered": 0, "awaiting": 0, "blocked": 0}
    assert body["responses"] == [] and body["awaiting"] == [] and body["kudos"] == []


def test_a_roster_outage_does_not_take_the_page_down(call):
    """eligible_members touches the database, so it can fail on its own."""
    import src.modules.insights.db as idb
    from flask import Flask
    from src.modules.insights import MODULE

    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = "test-secret"
    with patch("src.core.roster.db") as roster_db:
        roster_db.get_all_members.side_effect = RuntimeError("pool exhausted")
        MODULE.register_routes(flask_app)
        client = flask_app.test_client()
        with client.session_transaction() as sess:
            sess["team_id"] = "T1"
        with (
            patch.object(idb, "todays_standups", return_value=list(RESPONSES)),
            patch.object(idb, "active_schedules", return_value=list(SCHEDULES)),
            patch.object(idb, "recent_kudos", return_value=[]),
            patch.object(idb, "connect_program_timing", return_value=None),
        ):
            body = client.get("/dashboard/api/today").get_json()
    assert body["counts"]["expected"] == 0
    assert body["responses"][0]["user_id"] == "U1"
