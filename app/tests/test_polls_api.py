"""The Polls dashboard API: no more than the Slack message shows, to no one it should not.

Goes through the real routes and schemas with the in-memory browser fixtures.
"""

from __future__ import annotations

import json

import pytest

from tests.browser_fixtures import create_test_app


@pytest.fixture
def app(monkeypatch):
    return create_test_app(monkeypatch)


def signed_in(app, role):
    client = app.test_client()
    token = client.post(f"/__test__/session?role={role}").json["csrf_token"]
    return client, {"X-CSRF-Token": token}


def by_id(polls):
    return {p["id"]: p for p in polls}


class TestTheList:
    def test_an_open_hidden_poll_has_no_count_per_option(self, app):
        client, _ = signed_in(app, "admin")
        hidden = by_id(client.get("/dashboard/api/polls").json)[2]
        assert hidden["total_votes"] == 2
        assert all(o["votes"] is None for o in hidden["options"])
        assert all(o["voters"] is None for o in hidden["options"])

    def test_a_closed_hidden_poll_shows_its_results(self, app):
        client, _ = signed_in(app, "admin")
        closed = by_id(client.get("/dashboard/api/polls").json)[3]
        assert [o["votes"] for o in closed["options"]] == [0, 1]
        assert closed["options"][1]["voters"] == ["U_ADMIN"]

    def test_an_anonymous_poll_never_names_anyone(self, app):
        state = app.extensions["browser_test_data"]
        state.polls[1]["closed_at"] = state.now
        client, _ = signed_in(app, "admin")
        anonymous = by_id(client.get("/dashboard/api/polls").json)[2]
        assert [o["votes"] for o in anonymous["options"]] == [1, 1, 0]
        assert all(o["voters"] is None for o in anonymous["options"])
        body = json.dumps(anonymous)
        assert "a" * 64 not in body and "b" * 64 not in body

    def test_a_named_poll_shows_who_voted(self, app):
        client, _ = signed_in(app, "member")
        named = by_id(client.get("/dashboard/api/polls").json)[1]
        assert named["options"][0] == {"text": "Lisbon", "votes": 2, "voters": ["U_ADMIN", "U_LEAD"]}

    def test_a_member_does_not_see_a_private_channel_they_are_not_in(self, app, monkeypatch):
        state = app.extensions["browser_test_data"]
        state.channels.append({"id": "C_SECRET", "name": "secret", "is_private": True})
        state.polls[0]["channel_id"] = "C_SECRET"
        state.polls[0]["created_by"] = "U_ADMIN"
        import slack_sdk

        monkeypatch.setattr(slack_sdk.WebClient, "conversations_members", lambda self, **kw: {"members": ["U_ADMIN"]})
        client, _ = signed_in(app, "member")
        assert 1 not in by_id(client.get("/dashboard/api/polls").json)
        admin, _ = signed_in(app, "admin")
        assert 1 in by_id(admin.get("/dashboard/api/polls").json)

    def test_can_close_is_the_creator_or_an_admin(self, app):
        client, _ = signed_in(app, "member")
        polls = by_id(client.get("/dashboard/api/polls").json)
        assert polls[1]["can_close"] is True  # theirs
        assert polls[2]["can_close"] is False  # someone else's
        assert polls[3]["can_close"] is False  # already closed
        admin, _ = signed_in(app, "admin")
        assert by_id(admin.get("/dashboard/api/polls").json)[1]["can_close"] is True


class TestClosing:
    def test_the_creator_may(self, app):
        client, headers = signed_in(app, "member")
        body = client.post("/dashboard/api/polls/1/close", headers=headers).json
        assert body["closed_at"] and body["can_close"] is False

    def test_someone_else_may_not(self, app):
        client, headers = signed_in(app, "member")
        assert client.post("/dashboard/api/polls/2/close", headers=headers).status_code == 403
        assert app.extensions["browser_test_data"].polls[1]["closed_at"] is None

    def test_a_polls_admin_may(self, app):
        app.extensions["browser_test_data"].grants["U_LEAD"].add("polls")
        client, headers = signed_in(app, "feature-admin")
        assert client.post("/dashboard/api/polls/2/close", headers=headers).status_code == 200

    def test_another_features_admin_may_not(self, app):
        client, headers = signed_in(app, "feature-admin")
        assert client.post("/dashboard/api/polls/2/close", headers=headers).status_code == 403

    def test_closing_reveals_hidden_results(self, app):
        client, headers = signed_in(app, "admin")
        body = client.post("/dashboard/api/polls/2/close", headers=headers).json
        assert [o["votes"] for o in body["options"]] == [1, 1, 0]
        assert all(o["voters"] is None for o in body["options"])

    def test_a_missing_poll(self, app):
        client, headers = signed_in(app, "admin")
        assert client.post("/dashboard/api/polls/99/close", headers=headers).status_code == 404

    def test_closing_needs_the_csrf_token(self, app):
        client, _ = signed_in(app, "admin")
        assert client.post("/dashboard/api/polls/2/close").status_code == 403

    def test_the_slack_message_is_redrawn(self, app, monkeypatch):
        import src.modules.polls.dashboard as dashboard

        calls = []
        monkeypatch.setattr("src.modules.polls.handlers.finish_poll", lambda client, poll_id: calls.append(poll_id))
        # finish_poll is bound at registration; build the app again to pick up the patch.
        app = create_test_app(monkeypatch)
        client, headers = signed_in(app, "admin")
        client.post("/dashboard/api/polls/2/close", headers=headers)
        assert calls == [2]
        assert dashboard.MODULE_NAME == "polls"


class TestPayload:
    def test_voters_are_never_built_for_an_anonymous_poll(self):
        from src.modules.polls.dashboard import poll_payload

        poll = {
            "id": 1,
            "question": "Q",
            "channel_id": "C1",
            "created_by": "U1",
            "options": ["a"],
            "anonymous": True,
            "hide_results": False,
            "closed_at": "x",
        }
        assert poll_payload(poll, [1], {0: ["U9"]}, False)["options"][0]["voters"] is None


class TestTurningPollsOff:
    def test_the_module_switch_closes_open_polls(self, app, monkeypatch):
        import src.modules.polls.handlers as handlers

        calls = []
        monkeypatch.setattr(handlers, "close_all", lambda team: calls.append(team))
        from dataclasses import replace

        import src.modules as modules

        monkeypatch.setattr(
            modules,
            "REGISTRY",
            tuple(replace(s, on_disable=handlers.close_all) if s.name == "polls" else s for s in modules.REGISTRY),
        )
        client, headers = signed_in(app, "admin")
        assert client.post("/dashboard/api/modules/polls", json={"enabled": False}, headers=headers).status_code == 200
        assert calls == ["T_BROWSER"]

    def test_turning_it_on_closes_nothing(self, app, monkeypatch):
        import src.modules.polls.db as pdb

        monkeypatch.setattr(pdb, "open_poll_ids", lambda team: (_ for _ in ()).throw(AssertionError("closed")))
        client, headers = signed_in(app, "admin")
        assert client.post("/dashboard/api/modules/polls", json={"enabled": True}, headers=headers).status_code == 200

    def test_a_failing_wind_down_still_switches_it_off(self, app, monkeypatch):
        import src.modules.polls.db as pdb

        def boom(team):
            raise RuntimeError("db down")

        monkeypatch.setattr(pdb, "open_poll_ids", boom)
        state = app.extensions["browser_test_data"]
        client, headers = signed_in(app, "admin")
        assert client.post("/dashboard/api/modules/polls", json={"enabled": False}, headers=headers).status_code == 200
        assert state.module_settings["polls"] is False
