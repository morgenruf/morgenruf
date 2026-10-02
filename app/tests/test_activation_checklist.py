"""The activation checklist: five steps from install to a team that uses Morgenruf.

Each step is computed from stored data. The card is for workspace admins only,
goes away when everything is done or an admin hides it, and every button
re-checks who pressed it. Day 3 and day 7 DMs go to the installer once each,
only when their condition holds.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from src.core import activation, home, usage_report
from src.core.quickstart_button import OPEN_ACTION

from tests.support import patch_modules

FRESH = {
    "installer": "U_INSTALLER",
    "has_standup": False,
    "awaiting_invite": False,
    "responders": 0,
    "shared": False,
    "hidden_at": None,
    "sent_now_on": None,
}
ALL_DONE = {**FRESH, "has_standup": True, "responders": 3, "shared": True}


def _done(state, rituals=False):
    return {s.key: s.done for s in activation.steps(state, rituals)}


class TestSteps:
    def test_a_fresh_install_has_nothing_done(self):
        assert _done(FRESH) == dict.fromkeys(("standup", "invite", "answers", "ritual", "share"), False)

    def test_a_standup_waiting_for_its_invite_is_started_but_not_invited(self):
        done = _done({**FRESH, "has_standup": True, "awaiting_invite": True})
        assert done["standup"] and not done["invite"]

    def test_the_invite_is_done_once_nothing_waits(self):
        assert _done({**FRESH, "has_standup": True})["invite"]

    def test_first_answers_need_two_people(self):
        assert not _done({**FRESH, "responders": 1})["answers"]
        assert _done({**FRESH, "responders": 2})["answers"]

    def test_ritual_and_share(self):
        assert _done(FRESH, rituals=True)["ritual"]
        assert _done({**FRESH, "shared": True})["share"]

    def test_every_open_step_has_its_button(self):
        actions = {s.key: s.action for s in activation.steps(FRESH, False)}
        assert actions == {
            "standup": OPEN_ACTION,
            "invite": activation.INVITE_HELP_ACTION,
            "answers": activation.SEND_NOW_ACTION,
            "ritual": activation.PICK_ACTION,
            "share": activation.MEMBERS_ACTION,
        }


def _db(admin=True, state=None, standup_admin=None):
    db = MagicMock()
    db.can_administer.side_effect = lambda t, u, module=None: (
        admin if module is None else (admin if standup_admin is None else standup_admin)
    )
    db.checklist_state.return_value = dict(FRESH if state is None else state)
    return db


def _blocks(db, rituals=False):
    with patch_modules({"src.core.db": db}), patch.object(activation, "_rituals_on", return_value=rituals):
        return activation.checklist_blocks("T1", "U1")


class TestCard:
    def test_admins_see_progress_and_buttons(self):
        blocks = _blocks(_db(state={**FRESH, "has_standup": True, "awaiting_invite": True}))
        assert "1 of 5 done" in blocks[0]["text"]["text"]
        assert blocks[0]["accessory"]["action_id"] == activation.HIDE_ACTION
        rows = [b["text"]["text"] for b in blocks[1:-1]]
        assert rows[0].startswith("✅") and rows[1].startswith("⬜")
        assert blocks[2]["accessory"]["action_id"] == activation.INVITE_HELP_ACTION

    def test_members_never_see_it(self):
        assert _blocks(_db(admin=False)) == []

    def test_a_truthy_mock_is_not_an_admin(self):
        db = _db()
        db.can_administer.side_effect = None
        db.can_administer.return_value = MagicMock()
        assert _blocks(db) == []

    def test_gone_when_everything_is_done(self):
        assert _blocks(_db(state=ALL_DONE), rituals=True) == []

    def test_gone_when_hidden(self):
        assert _blocks(_db(state={**FRESH, "hidden_at": "2026-10-02"})) == []

    def test_core_puts_it_on_top_and_survives_a_failure(self):
        with patch.object(activation, "checklist_blocks", side_effect=RuntimeError("db down")):
            assert home.top_home_blocks("T1", "U1") == []


class TestSendNow:
    SCHEDULES = [
        {"id": 9, "active": False, "name": "Paused", "channel_id": "C9", "schedule_tz": "UTC"},
        {"id": 4, "active": True, "name": "Platform daily", "channel_id": "C4", "schedule_tz": "UTC"},
    ]

    def _run(self, db, send=None):
        send = send or MagicMock()
        with (
            patch_modules({"src.core.db": db}),
            patch("src.core.scheduler._send_standup_to_workspace", send),
        ):
            return activation.send_now("T1", "U1"), send

    def test_refuses_someone_who_cannot_run_standups(self):
        db = _db(admin=False, standup_admin=False)
        text, send = self._run(db)
        assert "Only" in text
        send.assert_not_called()
        db.claim_send_now.assert_not_called()

    def test_sends_the_first_active_standup_once_a_day(self):
        db = _db()
        db.get_standup_schedules.return_value = self.SCHEDULES
        db.claim_send_now.return_value = True
        db.get_installation.return_value = {"bot_token": "xoxb"}
        text, send = self._run(db)
        send.assert_called_once_with("T1", "xoxb", "C4", 4)
        assert "Platform daily" in text

    def test_a_second_press_the_same_day_sends_nothing(self):
        db = _db()
        db.get_standup_schedules.return_value = self.SCHEDULES
        db.claim_send_now.return_value = False
        text, send = self._run(db)
        send.assert_not_called()
        assert "already" in text

    def test_no_active_standup(self):
        db = _db()
        db.get_standup_schedules.return_value = [self.SCHEDULES[0]]
        text, send = self._run(db)
        send.assert_not_called()
        assert "no active standup" in text

    def test_a_failed_send_gives_the_day_back(self):
        db = _db()
        db.get_standup_schedules.return_value = self.SCHEDULES
        db.claim_send_now.return_value = True
        db.get_installation.return_value = {"bot_token": "xoxb"}
        text, _ = self._run(db, send=MagicMock(side_effect=RuntimeError("slack down")))
        db.release_send_now.assert_called_once()
        assert isinstance(db.release_send_now.call_args.args[1], date)
        assert "could not" in text


class TestRituals:
    def test_only_workspace_admins_turn_things_on(self):
        db = _db(admin=False)
        with (
            patch_modules({"src.core.db": db}),
            patch.object(activation, "available_rituals", return_value=[("kudos", "Kudos")]),
        ):
            assert activation.enable_rituals("T1", "U1", ["kudos"]) == []
        db.set_module_enabled.assert_not_called()

    def test_turns_on_only_what_is_offered(self):
        db = _db()
        with (
            patch_modules({"src.core.db": db}),
            patch.object(activation, "available_rituals", return_value=[("kudos", "Kudos")]),
        ):
            assert activation.enable_rituals("T1", "U1", ["kudos", "standup"]) == ["kudos"]
        db.set_module_enabled.assert_called_once_with("T1", "kudos", True)

    def test_the_picker_says_when_everything_is_on(self):
        with patch.object(activation, "available_rituals", return_value=[]):
            view = activation.rituals_modal("T1")
        assert "submit" not in view

    def test_the_picker_lists_choices(self):
        with patch.object(activation, "available_rituals", return_value=[("kudos", "Kudos"), ("polls", "Polls")]):
            view = activation.rituals_modal("T1")
        options = view["blocks"][0]["element"]["options"]
        assert [o["value"] for o in options] == ["kudos", "polls"]


def _handlers():
    captured: dict = {}

    def register(kind):
        def factory(name):
            def decorator(fn):
                captured[(kind, name)] = fn
                return fn

            return decorator

        return factory

    app = MagicMock()
    app.action.side_effect = register("action")
    app.view.side_effect = register("view")
    activation.register_slack(app)
    return captured


BODY = {"user": {"id": "U1", "team_id": "T1"}, "team": {"id": "T1"}, "trigger_id": "trig"}


class TestButtons:
    def test_hide_is_stored_and_redraws(self):
        db = _db()
        refreshed = []
        home.set_refresher(lambda t, u, c: refreshed.append((t, u)))
        try:
            with patch_modules({"src.core.db": db}):
                _handlers()[("action", activation.HIDE_ACTION)](ack=MagicMock(), body=BODY, client=MagicMock())
        finally:
            home.set_refresher(None)
        db.hide_checklist.assert_called_once_with("T1", "U1")
        assert refreshed == [("T1", "U1")]

    def test_a_member_cannot_hide_it(self):
        db = _db(admin=False)
        with patch_modules({"src.core.db": db}):
            _handlers()[("action", activation.HIDE_ACTION)](ack=MagicMock(), body=BODY, client=MagicMock())
        db.hide_checklist.assert_not_called()

    def test_invite_help_does_not_suggest_slash_invite(self):
        client = MagicMock()
        _handlers()[("action", activation.INVITE_HELP_ACTION)](ack=MagicMock(), body=BODY, client=client)
        text = str(client.views_open.call_args.kwargs["view"])
        assert "Add apps" in text and "/invite" not in text

    def test_send_now_tells_the_person(self):
        client = MagicMock()
        with patch.object(activation, "send_now", return_value="Sent."):
            _handlers()[("action", activation.SEND_NOW_ACTION)](ack=MagicMock(), body=BODY, client=client)
        assert client.chat_postMessage.call_args.kwargs == {"channel": "U1", "text": "Sent."}

    def test_members_button_opens_a_sign_in_not_a_url(self):
        client = MagicMock()
        with patch("src.core.dashboard_signin.signin_modal", return_value={"type": "modal"}) as modal:
            _handlers()[("action", activation.MEMBERS_ACTION)](ack=MagicMock(), body=BODY, client=client)
        modal.assert_called_once_with("T1", "U1")
        client.views_open.assert_called_once()

    def test_picking_nothing_keeps_the_modal_open(self):
        ack = MagicMock()
        view = {"state": {"values": {"rituals": {"rituals": {"selected_options": []}}}}}
        with patch.object(activation, "enable_rituals", return_value=[]):
            _handlers()[("view", activation.PICK_CALLBACK)](ack=ack, body=BODY, view=view, client=MagicMock())
        assert ack.call_args.kwargs["response_action"] == "errors"


# ── Nudges ──────────────────────────────────────────────────────────────────

ROW = {"team_id": "T1", "bot_token": "xoxb-1", "installed_by_user_id": "U1"}


@pytest.fixture
def slack(monkeypatch):
    monkeypatch.setattr(activation, "_bot_token", lambda team_id, stored: stored)
    client = MagicMock()
    client.conversations_open.return_value = {"channel": {"id": "D1"}}
    monkeypatch.setattr(activation, "WebClient", MagicMock(return_value=client))
    return client


def _nudge(fn, state, rows=(ROW,), recorded=True, rituals=False):
    db = MagicMock()
    db.workspaces_for_activation_nudge.return_value = list(rows)
    db.checklist_state.return_value = dict(state)
    db.record_install_email.return_value = recorded
    with patch_modules({"src.core.db": db}), patch.object(activation, "_rituals_on", return_value=rituals):
        return fn(), db


class TestDay3:
    def test_a_standup_with_no_answers_gets_send_it_now(self, slack):
        (sent, _), db = _nudge(activation.send_day3_nudges, {**FRESH, "has_standup": True})
        assert sent == 1
        db.record_install_email.assert_called_once_with("T1", activation.KIND_DAY3)
        blocks = slack.chat_postMessage.call_args.kwargs["blocks"]
        assert blocks[0]["accessory"]["action_id"] == activation.SEND_NOW_ACTION

    def test_not_sent_without_a_standup_or_with_answers(self, slack):
        for state in (FRESH, {**FRESH, "has_standup": True, "responders": 1}):
            (sent, _), db = _nudge(activation.send_day3_nudges, state)
            assert sent == 0
            db.record_install_email.assert_not_called()

    def test_never_twice(self, slack):
        (sent, _), _ = _nudge(activation.send_day3_nudges, {**FRESH, "has_standup": True}, recorded=False)
        assert sent == 0
        slack.chat_postMessage.assert_not_called()

    def test_internal_workspaces_are_skipped(self, slack, monkeypatch):
        monkeypatch.setenv("MORGENRUF_INTERNAL_TEAMS", "T1")
        (sent, skipped), db = _nudge(activation.send_day3_nudges, {**FRESH, "has_standup": True})
        assert (sent, skipped) == (0, 1)
        db.record_install_email.assert_not_called()


class TestDay7:
    def test_fewer_than_three_names_the_next_step(self, slack):
        (sent, _), db = _nudge(activation.send_day7_nudges, {**FRESH, "has_standup": True})
        assert sent == 1
        db.record_install_email.assert_called_once_with("T1", activation.KIND_DAY7)
        kwargs = slack.chat_postMessage.call_args.kwargs
        assert "2 of 5" in kwargs["text"]
        assert kwargs["blocks"][1]["accessory"]["action_id"] == activation.SEND_NOW_ACTION

    def test_three_or_more_done_is_left_alone(self, slack):
        (sent, _), db = _nudge(activation.send_day7_nudges, {**FRESH, "has_standup": True, "responders": 2})
        assert sent == 0
        db.record_install_email.assert_not_called()


def test_one_failing_nudge_does_not_stop_the_others():
    calls = []
    with (
        patch.object(activation, "send_day2_nudges", side_effect=RuntimeError("boom")),
        patch.object(activation, "send_day3_nudges", side_effect=lambda: calls.append(3)),
        patch.object(activation, "send_day7_nudges", side_effect=lambda: calls.append(7)),
    ):
        activation.send_activation_nudges()
    assert calls == [3, 7]


# ── Monday report ───────────────────────────────────────────────────────────


def test_the_report_lists_checklist_progress_for_live_outside_teams():
    rows = [
        {"team_id": "T1", "team_name": "Acme", "active": True},
        {"team_id": "T2", "team_name": "Beta", "active": True},
        {"team_id": "T3", "team_name": "Gone", "active": False},
    ]
    text = usage_report.build(rows, internal=set(), checklist={"T1": 2, "T2": 5, "T3": 1})
    assert "Checklist steps done: Beta 5/5, Acme 2/5" in text
    assert "Gone" not in text.split("Checklist steps done:")[1]


def test_checklist_counts_skip_internal_and_removed():
    rows = [
        {"team_id": "T1", "active": True},
        {"team_id": "T_OWN", "active": True},
        {"team_id": "T3", "active": False},
    ]
    with patch.object(activation, "done_count", return_value=4):
        assert usage_report.checklist_counts(rows, {"T_OWN"}) == {"T1": 4}


# ── Database ────────────────────────────────────────────────────────────────


def test_checklist_state_reads_counts_only(fake_cursor_db):
    from src.core import db

    db.checklist_state("T1")
    sql, params = fake_cursor_db.calls[0]
    assert "COUNT(DISTINCT st.user_id)" in sql and "awaiting_invite_by IS NOT NULL" in sql
    assert "standup_managers" in sql and "module_admins" in sql
    assert params == ("T1",)


def test_send_now_claim_is_once_per_day(fake_cursor_db):
    from src.core import db

    db.claim_send_now("T1", date(2026, 10, 2))
    sql, params = fake_cursor_db.calls[0]
    assert "IS DISTINCT FROM EXCLUDED.sent_now_on" in sql and "RETURNING 1" in sql
    assert params == ("T1", date(2026, 10, 2))


def test_nudge_candidates_are_young_live_installs_not_yet_sent(fake_cursor_db):
    from src.core import db

    db.workspaces_for_activation_nudge("nudge:day3", 72)
    sql, params = fake_cursor_db.calls[0]
    assert "i.active" in sql and "INTERVAL '14 days'" in sql and "e.kind = %s" in sql
    assert params == (72, "nudge:day3")
