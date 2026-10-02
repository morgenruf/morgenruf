"""Per-standup managers: a team lead changes their own standup and nobody else's.

Roles (see docs/design/2026-10-02-standup-managers-design.md): a manager may
edit and pause the standups they were given. Creating, deleting, moving a
standup to another channel and naming managers stay with the admins.
"""

from __future__ import annotations

import copy
from unittest.mock import MagicMock, patch

import pytest

from tests.browser_fixtures import create_test_app
from tests.support import patch_modules
from tests.test_standup_answer_safety import _handlers, _modal_body, _real_pytz, blocks, handlers, schedule_validation

# ── Dashboard API ───────────────────────────────────────────────────────────


@pytest.fixture
def browser(monkeypatch):
    app = create_test_app(monkeypatch)
    state = app.extensions["browser_test_data"]
    # A second standup the member will not manage.
    other = copy.deepcopy(state.schedules[0])
    other.update(id=2, name="Design standup", channel_id="C_GENERAL")
    state.schedules.append(other)
    return app, app.test_client(), state


def _as(client, role):
    return {"X-CSRF-Token": client.post(f"/__test__/session?role={role}").json["csrf_token"]}


def _make_manager(client, user_id="U_MEMBER", standup_id=1):
    headers = _as(client, "admin")
    response = client.put(
        f"/dashboard/api/standups/{standup_id}/managers", json={"user_ids": [user_id]}, headers=headers
    )
    assert response.status_code == 200, response.data
    return response


class TestDashboard:
    def test_admin_names_managers(self, browser):
        _, client, state = browser
        response = _make_manager(client)
        assert response.json == {"user_ids": ["U_MEMBER"]}
        assert state.standup_managers == {1: ["U_MEMBER"]}

    def test_a_manager_edits_their_standup(self, browser):
        _, client, state = browser
        _make_manager(client)
        headers = _as(client, "member")
        response = client.put("/dashboard/api/standups/1", json={"name": "Platform daily"}, headers=headers)
        assert response.status_code == 200, response.data
        assert response.json["can_manage"] is True
        assert state.schedules[0]["name"] == "Platform daily"

    def test_a_manager_cannot_edit_another_standup(self, browser):
        _, client, state = browser
        _make_manager(client)
        headers = _as(client, "member")
        response = client.put("/dashboard/api/standups/2", json={"name": "Taken over"}, headers=headers)
        assert response.status_code == 403
        assert state.schedules[1]["name"] == "Design standup"

    @pytest.mark.parametrize(
        ("field", "value"),
        [("channel_id", "C_GENERAL"), ("report_channel", "C_GENERAL"), ("digest_email", "me@elsewhere.test")],
    )
    def test_a_manager_cannot_redirect_where_it_posts(self, browser, field, value):
        _, client, state = browser
        _make_manager(client)
        headers = _as(client, "member")
        response = client.put("/dashboard/api/standups/1", json={field: value}, headers=headers)
        assert response.status_code == 403
        assert state.schedules[0].get(field) != value

    def test_sending_the_same_channel_back_is_fine(self, browser):
        _, client, _ = browser
        _make_manager(client)
        headers = _as(client, "member")
        response = client.put(
            "/dashboard/api/standups/1", json={"channel_id": "C_ENGINEERING", "name": "Same place"}, headers=headers
        )
        assert response.status_code == 200, response.data

    def test_a_manager_cannot_change_workspace_settings_through_the_form(self, browser):
        _, client, state = browser
        _make_manager(client)
        before = copy.deepcopy(state.workspace)
        headers = _as(client, "member")
        client.put("/dashboard/api/standups/1", json={"name": "x", "edit_window": "never"}, headers=headers)
        assert state.workspace == before

    def test_a_manager_cannot_delete_or_name_managers(self, browser):
        _, client, state = browser
        _make_manager(client)
        headers = _as(client, "member")
        assert client.delete("/dashboard/api/standups/1", headers=headers).status_code == 403
        response = client.put("/dashboard/api/standups/1/managers", json={"user_ids": ["U_LEAD"]}, headers=headers)
        assert response.status_code == 403
        assert len(state.schedules) == 2
        assert state.standup_managers == {1: ["U_MEMBER"]}

    def test_a_member_who_manages_nothing_is_refused(self, browser):
        _, client, _ = browser
        headers = _as(client, "member")
        assert client.put("/dashboard/api/standups/1", json={"name": "x"}, headers=headers).status_code == 403

    def test_the_list_says_what_each_viewer_can_change(self, browser):
        _, client, _ = browser
        _make_manager(client)
        _as(client, "member")
        rows = {r["id"]: r for r in client.get("/dashboard/api/standups").json}
        assert rows[1]["can_manage"] is True
        assert rows[1]["managers"] == ["U_MEMBER"]
        if 2 in rows:
            assert rows[2]["can_manage"] is False
            assert rows[2]["managers"] == []

    def test_admins_see_everyone_can_manage(self, browser):
        _, client, _ = browser
        _make_manager(client)
        _as(client, "admin")
        assert all(r["can_manage"] for r in client.get("/dashboard/api/standups").json)

    def test_managers_limit_and_unknown_standup(self, browser):
        _, client, _ = browser
        headers = _as(client, "admin")
        many = [f"U{i}" for i in range(11)]
        assert (
            client.put("/dashboard/api/standups/1/managers", json={"user_ids": many}, headers=headers).status_code
            == 400
        )
        response = client.put("/dashboard/api/standups/99/managers", json={"user_ids": ["U1"]}, headers=headers)
        assert response.status_code == 404

    def test_only_new_managers_are_told(self, browser, monkeypatch):
        import src.core.dashboard as dashboard

        told = []
        monkeypatch.setattr(dashboard, "_tell_new_managers", lambda team, sid, users: told.append(list(users)))
        _, client, _ = browser
        headers = _as(client, "admin")
        client.put("/dashboard/api/standups/1/managers", json={"user_ids": ["U_MEMBER"]}, headers=headers)
        client.put("/dashboard/api/standups/1/managers", json={"user_ids": ["U_MEMBER", "U_LEAD"]}, headers=headers)
        assert told == [["U_MEMBER"], ["U_LEAD"]]


# ── Slack ───────────────────────────────────────────────────────────────────


def _db(admin=False, managed=()):
    db = MagicMock()
    db.can_administer.return_value = admin
    db.managed_schedule_ids.return_value = set(managed)
    db.get_standup_schedule.return_value = {
        "id": 7,
        "name": "Platform daily",
        "channel_id": "C_TEAM",
        "questions": ["Q1"],
        "schedule_days": "mon",
        "participants": [],
    }
    db.update_standup_schedule.return_value = None
    return db


def _action(action_id, actions):
    return {"user": {"id": "U_MEMBER", "team_id": "T1"}, "team": {"id": "T1"}, "trigger_id": "x", "actions": actions}


class TestSlack:
    def setup_method(self):
        self.handlers = _handlers()
        self.client = MagicMock()
        # A bare MagicMock pages forever: its next_cursor is always truthy.
        self.client.users_conversations.return_value = {"channels": [], "response_metadata": {"next_cursor": ""}}
        self.client.users_info.return_value = {"user": {"id": "U2", "is_bot": False, "profile": {}}}

    def _run(self, db, kind, name, *args):
        with patch_modules({"src.core.db": db}), patch.object(schedule_validation, "pytz", _real_pytz):
            self.handlers[(kind, name)](*args)

    def test_rule_matches_the_spec(self):
        with patch_modules({"src.core.db": _db(managed={7})}):
            assert handlers.may_manage_standup("T1", "U_MEMBER", "7") is True
            assert handlers.may_manage_standup("T1", "U_MEMBER", "8") is False
            assert handlers.may_manage_standup("T1", "U_MEMBER", "not-a-number") is False
        with patch_modules({"src.core.db": _db(admin=True)}):
            assert handlers.may_manage_standup("T1", "U_ADMIN", "8") is True

    def test_a_failed_lookup_refuses(self):
        db = _db()
        db.managed_schedule_ids.side_effect = RuntimeError("db down")
        with patch_modules({"src.core.db": db}):
            assert handlers.may_manage_standup("T1", "U_MEMBER", "7") is False

    def test_a_manager_opens_configure_with_the_channel_locked(self):
        db = _db(managed={7})
        self._run(db, "action", "edit_standup", MagicMock(), _action("edit_standup", [{"value": "7"}]), self.client)
        view = self.client.views_open.call_args.kwargs["view"]
        ids = [b.get("block_id") for b in view["blocks"]]
        assert "standup_channel_locked" in ids and "standup_channel" not in ids

    def test_a_manager_of_another_standup_is_refused(self):
        db = _db(managed={8})
        self._run(db, "action", "edit_standup", MagicMock(), _action("edit_standup", [{"value": "7"}]), self.client)
        self.client.views_open.assert_not_called()
        assert handlers._NOT_A_STANDUP_ADMIN in self.client.chat_postMessage.call_args.kwargs["text"]

    def test_a_manager_pauses_but_cannot_delete(self):
        db = _db(managed={7})
        self._run(db, "action", "standup_overflow", MagicMock(), _action("o", [{"value": "pause_7"}]), self.client)
        db.update_standup_schedule.assert_called_once_with("T1", 7, active=False)
        self._run(db, "action", "standup_overflow", MagicMock(), _action("o", [{"value": "delete_7"}]), self.client)
        db.delete_standup_schedule.assert_not_called()

    def _edit_body(self, channel):
        body = _modal_body()
        body["view"]["private_metadata"] = "7"
        values = body["view"]["state"]["values"]
        if channel is None:
            values.pop("standup_channel")
        else:
            values["standup_channel"] = {"standup_channel": {"selected_channel": channel}}
        return body

    def test_a_manager_saves_without_the_channel_block(self):
        db = _db(managed={7})
        ack = MagicMock()
        self._run(db, "view", "create_standup_modal", ack, self._edit_body(None), self.client)
        assert ack.call_args.kwargs.get("response_action") != "errors"
        assert db.update_standup_schedule.call_args.kwargs["channel_id"] == "C_TEAM"

    def test_a_manager_cannot_move_the_channel_by_crafting_the_submission(self):
        db = _db(managed={7})
        ack = MagicMock()
        self._run(db, "view", "create_standup_modal", ack, self._edit_body("C_GENERAL"), self.client)
        assert ack.call_args.kwargs["response_action"] == "errors"
        db.update_standup_schedule.assert_not_called()

    def test_a_manager_cannot_create(self):
        db = _db(managed={7})
        ack = MagicMock()
        self._run(db, "view", "create_standup_modal", ack, _modal_body(), self.client)
        assert ack.call_args.kwargs["response_action"] == "errors"
        db.create_standup_schedule.assert_not_called()


class TestAppHome:
    def _standup(self, sid, can_manage):
        return {
            "standup_id": str(sid),
            "standup_name": f"S{sid}",
            "channel_id": "C1",
            "active": True,
            "members": [],
            "can_manage": can_manage,
        }

    def _ids(self, view, action_id):
        return [
            el.get("value")
            for b in view["blocks"]
            for el in (b.get("elements") or []) + ([b["accessory"]] if b.get("accessory") else [])
            if isinstance(el, dict) and el.get("action_id") == action_id
        ]

    def test_configure_only_on_the_standups_you_manage(self):
        view = blocks.app_home_view(standups=[self._standup(1, True), self._standup(2, False)], user_id="U1")
        assert self._ids(view, "edit_standup") == ["1"]

    def test_standups_you_manage_but_do_not_answer(self):
        view = blocks.app_home_view(standups=[], user_id="U1", other_standups=[self._standup(5, True)])
        text = str(view["blocks"])
        assert "Standups you manage" in text and "Other standups (admin)" not in text
        assert self._ids(view, "edit_standup") == ["5"]

    def test_a_member_who_manages_nothing_is_told_who_to_ask(self):
        view = blocks.app_home_view(standups=[self._standup(1, False)], user_id="U1", admin_contact="U_BOSS")
        assert "Ask <@U_BOSS> to make you its manager" in str(view["blocks"])

    def test_no_hint_for_admins(self):
        view = blocks.app_home_view(standups=[self._standup(1, True)], user_id="U1", is_admin=True)
        assert "make you its manager" not in str(view["blocks"])
