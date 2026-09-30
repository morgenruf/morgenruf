"""A signed-in member reads what Slack would show them: standups they are in
or whose channel they can see, and nobody's email address. Admins, and people
who administer standups, still see everything."""

from __future__ import annotations

import pytest
import slack_sdk
import src.core.dashboard as dashboard

from tests.browser_fixtures import create_test_app

SECRET = "C_SECRET"


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setattr(dashboard, "_CHANNEL_PUBLIC_CACHE", {})
    app = create_test_app(monkeypatch)
    state = app.extensions["browser_test_data"]
    state.channels.append({"id": SECRET, "name": "leadership", "is_private": True})
    private = {
        **state.schedules[0],
        "id": 2,
        "name": "Leadership sync",
        "channel_id": SECRET,
        "report_channel": SECRET,
        "participants": ["U_ADMIN"],
    }
    state.schedules.append(private)
    state.responses.append(
        {
            **state.responses[0],
            "id": 2,
            "user_id": "U_ADMIN",
            "today": "Confidential reorg planning",
            "schedule_id": 2,
        }
    )
    # Only the admin is in the private channel.
    fake = slack_sdk.WebClient

    def conversations_members(self, channel, **kwargs):
        if channel == SECRET:
            return {"members": ["U_ADMIN"]}
        return {"members": [m["user_id"] for m in state.members]}

    monkeypatch.setattr(fake, "conversations_members", conversations_members)
    return app, app.test_client(), state


def _as(client, role):
    client.post(f"/__test__/session?role={role}")


def test_a_member_does_not_see_a_private_channel_standup(browser):
    _, client, _ = browser
    _as(client, "member")
    names = [s["name"] for s in client.get("/dashboard/api/standups").json]
    assert names == ["Engineering standup"]
    report = client.get("/dashboard/api/reports").json
    assert all(s.get("schedule_id") != 2 for s in report["standups"])
    assert "Confidential reorg" not in client.get("/dashboard/api/export/csv").get_data(as_text=True)


def test_a_participant_sees_it(browser):
    _, client, state = browser
    state.schedules[1]["participants"].append("U_MEMBER")
    _as(client, "member")
    assert "Leadership sync" in [s["name"] for s in client.get("/dashboard/api/standups").json]
    assert "Confidential reorg" in client.get("/dashboard/api/export/csv").get_data(as_text=True)


def test_a_member_of_the_private_channel_sees_it(browser, monkeypatch):
    _, client, state = browser
    monkeypatch.setattr(slack_sdk.WebClient, "conversations_members", lambda self, **kw: {"members": ["U_MEMBER"]})
    _as(client, "member")
    assert "Leadership sync" in [s["name"] for s in client.get("/dashboard/api/standups").json]


@pytest.mark.parametrize("role", ["admin", "standup-admin"])
def test_admins_see_everything(browser, role):
    _, client, _ = browser
    _as(client, role)
    assert len(client.get("/dashboard/api/standups").json) == 2
    assert "Confidential reorg" in client.get("/dashboard/api/export/csv").get_data(as_text=True)
    assert any(s.get("schedule_id") == 2 for s in client.get("/dashboard/api/reports").json["standups"])


def test_member_emails_are_for_admins(browser):
    _, client, _ = browser
    _as(client, "member")
    assert all(m["email"] == "" for m in client.get("/dashboard/api/members").json)
    _as(client, "admin")
    assert all(m["email"] for m in client.get("/dashboard/api/members").json)


def test_a_member_cannot_list_a_private_channel_they_are_not_in(browser):
    _, client, _ = browser
    _as(client, "member")
    assert client.get(f"/dashboard/api/members?channel_id={SECRET}").json == []
    assert len(client.get("/dashboard/api/members?channel_id=C_ENGINEERING").json) == 3
    _as(client, "admin")
    assert [m["id"] for m in client.get(f"/dashboard/api/members?channel_id={SECRET}").json] == ["U_ADMIN"]
