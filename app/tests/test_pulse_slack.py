"""Pulse in Slack: the weekly DM, the answer buttons, the reminder.

Answers go through the app's real Bolt listeners. Storage is an in-memory
stand-in that keeps the rules pulse.db enforces in SQL: one round a day, one
answer per person per question, only for the invited and only while open.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from flask import Flask
from slack_bolt import App, BoltRequest
from slack_bolt.authorization import AuthorizeResult
from slack_sdk.web import WebClient
from slack_sdk.webhook import WebhookClient

TEAM = "T1"
NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)


class Store:
    """pulse.db, in memory."""

    def __init__(self):
        self.program = {
            "team_id": TEAM,
            "enabled": True,
            "day_of_week": 4,
            "hour": 14,
            "minute": 0,
            "timezone": "UTC",
            "audience_channel_id": None,
        }
        self.rounds: dict[int, dict] = {}
        self.invites: dict[int, list[str]] = {}
        self.respondents: set[tuple[int, str, str]] = set()
        self.answers: list[tuple[int, str, int]] = []

    def get_program(self, team_id):
        return dict(self.program)

    def create_round(self, team_id, sent_on, closes_at):
        if any(r["sent_on"] == sent_on for r in self.rounds.values()):
            return None
        rid = len(self.rounds) + 1
        self.rounds[rid] = {
            "id": rid,
            "team_id": team_id,
            "sent_on": sent_on,
            "includes_enps": (rid - 1) % 4 == 0,
            "closes_at": closes_at,
            "reminded_at": None,
            "invited": 0,
        }
        return dict(self.rounds[rid])

    def record_invites(self, round_id, user_ids):
        current = self.invites.setdefault(round_id, [])
        current.extend(u for u in user_ids if u not in current)
        self.rounds[round_id]["invited"] = len(current)
        return len(current)

    def close_open_rounds(self, team_id):
        for r in self.rounds.values():
            if r.get("scrubbed_at") is None and r["closes_at"] > NOW:
                r["closes_at"] = NOW
        return self.close_due_rounds(team_id)

    def get_round(self, round_id):
        r = self.rounds.get(round_id)
        return {**r, "closed": r["closes_at"] <= NOW} if r else None

    def record_answer(self, round_id, user_id, key, value):
        r = self.rounds[round_id]
        if r["closes_at"] <= NOW or user_id not in self.invites.get(round_id, []):
            return False
        if (round_id, user_id, key) in self.respondents:
            return False
        self.respondents.add((round_id, user_id, key))
        self.answers.append((round_id, key, value))
        return True

    def answered(self, round_id, user_id):
        return {k for r, u, k in self.respondents if r == round_id and u == user_id}

    def rounds_to_remind(self, team_id):
        return [
            {"id": r["id"], "includes_enps": r["includes_enps"]}
            for r in self.rounds.values()
            if r["reminded_at"] is None and NOW < r["closes_at"] <= NOW + timedelta(hours=48)
        ]

    def claim_reminder(self, round_id):
        if self.rounds[round_id]["reminded_at"]:
            return False
        self.rounds[round_id]["reminded_at"] = NOW
        return True

    def close_due_rounds(self, team_id):
        closed = []
        for r in self.rounds.values():
            if r.get("scrubbed_at") is None and r["closes_at"] <= NOW:
                r["scrubbed_at"] = NOW
                self.respondents = {x for x in self.respondents if x[0] != r["id"]}
                self.invites.pop(r["id"], None)
                closed.append(r["id"])
        return closed

    def non_respondents(self, round_id):
        answered = {u for r, u, _ in self.respondents if r == round_id}
        return [u for u in self.invites.get(round_id, []) if u not in answered]


@pytest.fixture
def world(monkeypatch):
    import src.core.analytics as analytics
    import src.core.db as core_db
    import src.modules.pulse.db as pdb
    import src.modules.pulse.jobs as jobs

    store = Store()
    state = SimpleNamespace(
        store=store,
        posts=[],
        updates=[],
        responds=[],
        captures=[],
        settings={"pulse": True},
        admins=set(),
        members=["U1", "U2", "U3"],
        channel_members=["U1", "UBOT", "U2"],
        humans={"U1", "U2", "U3"},
        dm_failures=set(),
    )
    for name in (
        "get_program",
        "create_round",
        "record_invites",
        "get_round",
        "record_answer",
        "answered",
        "rounds_to_remind",
        "claim_reminder",
        "non_respondents",
        "close_due_rounds",
        "close_open_rounds",
    ):
        monkeypatch.setattr(pdb, name, getattr(store, name))
    monkeypatch.setattr(core_db, "granted_scopes", lambda team_id: set())
    monkeypatch.setattr(core_db, "module_settings", lambda team_id: dict(state.settings))
    monkeypatch.setattr(core_db, "can_administer", lambda team_id, user_id, module=None: user_id in state.admins)
    monkeypatch.setattr(core_db, "get_active_members", lambda team_id: [{"user_id": u} for u in state.members])
    monkeypatch.setattr(analytics, "capture", lambda event, team_id, **props: state.captures.append((event, props)))
    monkeypatch.setattr(jobs, "_now", lambda: NOW)
    monkeypatch.setattr(jobs, "DM_PAUSE_SECONDS", 0)

    def chat_postMessage(self, **kwargs):  # noqa: N802
        if kwargs.get("channel") in state.dm_failures:
            raise RuntimeError("cannot_dm_bot")
        state.posts.append(kwargs)
        return {"ok": True, "ts": f"{len(state.posts)}.000", "channel": f"D{kwargs.get('channel')}"}

    def chat_update(self, **kwargs):
        state.updates.append(kwargs)
        return {"ok": True}

    def conversations_members(self, **kwargs):
        return {"ok": True, "members": list(state.channel_members)}

    monkeypatch.setattr(WebClient, "chat_postMessage", chat_postMessage)
    monkeypatch.setattr(WebClient, "chat_update", chat_update)
    monkeypatch.setattr(WebClient, "conversations_members", conversations_members)
    monkeypatch.setattr(
        "src.core.standup_invites.filter_human_ids", lambda client, ids: {i for i in ids if i in state.humans}
    )
    monkeypatch.setattr(WebhookClient, "send_dict", lambda self, body: state.responds.append(body))
    monkeypatch.setattr(jobs, "bot_client", lambda team_id: WebClient(token="xoxb-1"))

    from src.main import register_slack_listeners
    from src.modules import REGISTRY

    app = App(
        signing_secret="x",
        authorize=lambda **kw: AuthorizeResult(
            enterprise_id=None, team_id=TEAM, bot_token="xoxb-1", bot_user_id="UBOT", bot_id="B1"
        ),
        request_verification_enabled=False,
        process_before_response=True,
    )
    register_slack_listeners(Flask(__name__), app, list(REGISTRY))
    state.app = app
    return state


def click(world, action_id, user="U1", ts="1.000"):
    payload = {
        "type": "block_actions",
        "team": {"id": TEAM},
        "user": {"id": user, "team_id": TEAM},
        "channel": {"id": f"D{user}"},
        "container": {"type": "message", "message_ts": ts, "channel_id": f"D{user}"},
        "message": {"ts": ts},
        "trigger_id": "1.2.3",
        "actions": [{"action_id": action_id, "block_id": "b", "type": "button", "value": "x"}],
    }
    body = urlencode({"payload": json.dumps(payload)})
    world.app.dispatch(BoltRequest(body=body, headers={"content-type": ["application/x-www-form-urlencoded"]}))


def action_ids(blocks) -> list[str]:
    return [e["action_id"] for b in blocks if b.get("type") == "actions" for e in b["elements"]]


def send(world):
    from src.modules.pulse.jobs import send_round

    send_round(TEAM)


class TestSendingARound:
    def test_everyone_active_gets_the_mood_question_by_dm(self, world):
        send(world)
        assert [p["channel"] for p in world.posts] == ["U1", "U2", "U3"]
        ids = action_ids(world.posts[0]["blocks"])
        assert ids == [f"pulse:answer:1:mood:{v}" for v in range(1, 6)]
        text = json.dumps(world.posts[0])
        assert "anonymous" in text and "at least 5 people" in text
        assert ("pulse_round_sent", {"invited": 3}) in world.captures

    def test_only_people_whose_dm_arrived_are_invited(self, world):
        world.dm_failures = {"U2"}
        send(world)
        assert world.store.invites[1] == ["U1", "U3"]
        assert world.store.rounds[1]["invited"] == 2
        assert ("pulse_round_sent", {"invited": 2}) in world.captures

    def test_twice_on_the_same_day_sends_once(self, world):
        send(world)
        send(world)
        assert len(world.store.rounds) == 1
        assert len(world.posts) == 3

    def test_a_channel_audience_leaves_out_bots(self, world):
        world.store.program["audience_channel_id"] = "C1"
        send(world)
        assert world.store.invites[1] == ["U1", "U2"]
        assert [p["channel"] for p in world.posts] == ["U1", "U2"]

    def test_a_switched_off_programme_sends_nothing(self, world):
        world.store.program["enabled"] = False
        send(world)
        assert world.posts == [] and world.store.rounds == {}

    def test_a_switched_off_module_sends_nothing(self, world):
        world.settings = {"pulse": False}
        send(world)
        assert world.posts == [] and world.store.rounds == {}

    def test_the_round_closes_in_three_days(self, world):
        send(world)
        assert world.store.rounds[1]["closes_at"] == NOW + timedelta(hours=72)


class TestAnswering:
    def test_an_answer_is_counted_and_the_buttons_are_replaced_without_the_value(self, world):
        send(world)
        click(world, "pulse:answer:1:mood:4")
        assert world.store.answers == [(1, "mood", 4)]
        update = world.updates[-1]
        assert update["channel"] == "DU1" and update["ts"] == "1.000"
        text = json.dumps(update)
        assert "Thanks, noted." in text
        assert "Good" not in text and ":4" not in text and "pulse:answer" not in text

    def test_a_double_click_counts_once(self, world):
        send(world)
        click(world, "pulse:answer:1:mood:4")
        click(world, "pulse:answer:1:mood:2")
        assert world.store.answers == [(1, "mood", 4)]

    def test_enps_follows_mood_in_an_enps_round(self, world):
        send(world)
        before = len(world.posts)
        click(world, "pulse:answer:1:mood:4")
        nxt = world.posts[before:]
        assert len(nxt) == 1 and nxt[0]["channel"] == "U1"
        ids = action_ids(nxt[0]["blocks"])
        assert ids == [f"pulse:answer:1:enps:{v}" for v in range(11)]
        rows = [b for b in nxt[0]["blocks"] if b.get("type") == "actions"]
        assert len(rows) == 2

    def test_no_enps_in_a_plain_round(self, world):
        world.store.create_round(TEAM, date(2026, 9, 25), NOW - timedelta(days=4))
        send(world)
        rid = max(world.store.rounds)
        assert world.store.rounds[rid]["includes_enps"] is False
        before = len(world.posts)
        click(world, f"pulse:answer:{rid}:mood:3")
        assert world.posts[before:] == []

    def test_after_close_nothing_is_recorded(self, world):
        send(world)
        world.store.rounds[1]["closes_at"] = NOW - timedelta(minutes=1)
        click(world, "pulse:answer:1:mood:4")
        assert world.store.answers == []
        assert "This check-in has closed." in json.dumps(world.updates[-1])

    def test_turned_off_mid_round_nothing_is_recorded(self, world):
        send(world)
        world.settings = {"pulse": False}
        click(world, "pulse:answer:1:mood:4")
        assert world.store.answers == []

    def test_no_log_line_names_a_person_with_a_value(self, world, caplog):
        send(world)
        with caplog.at_level(logging.DEBUG):
            click(world, "pulse:answer:1:mood:4")
            click(world, "pulse:answer:1:enps:9")
        for record in caplog.records:
            message = record.getMessage()
            if "U1" in message:
                assert not re.search(r"\b(4|9)\b", message.replace("U1", "")), message


class TestReminder:
    def test_only_non_respondents_and_only_once(self, world):
        from src.modules.pulse.jobs import tick

        send(world)
        click(world, "pulse:answer:1:mood:4", user="U1")
        world.store.rounds[1]["closes_at"] = NOW + timedelta(hours=40)
        before = len(world.posts)
        tick(TEAM)
        reminded = [p["channel"] for p in world.posts[before:]]
        assert reminded == ["U2", "U3"]
        assert "closes tomorrow" in world.posts[-1]["text"]
        tick(TEAM)
        assert len(world.posts) == before + 2

    def test_not_before_a_day_has_passed(self, world):
        from src.modules.pulse.jobs import tick

        send(world)
        before = len(world.posts)
        tick(TEAM)
        assert len(world.posts) == before

    def test_a_closed_round_forgets_who_answered(self, world):
        from src.modules.pulse.jobs import tick

        send(world)
        click(world, "pulse:answer:1:mood:4", user="U1")
        world.store.rounds[1]["closes_at"] = NOW - timedelta(minutes=1)
        tick(TEAM)
        assert world.store.respondents == set() and 1 not in world.store.invites
        assert world.store.answers == [(1, "mood", 4)]


class TestTurningPulseOff:
    def test_open_rounds_close_now_and_forget_who_answered(self, world):
        from src.modules.pulse import MODULE

        send(world)
        click(world, "pulse:answer:1:mood:4", user="U1")
        MODULE.on_disable(TEAM)
        assert world.store.rounds[1]["closes_at"] == NOW and world.store.rounds[1]["scrubbed_at"] == NOW
        assert world.store.respondents == set() and 1 not in world.store.invites
        click(world, "pulse:answer:1:mood:2", user="U2")
        assert world.store.answers == [(1, "mood", 4)]


class TestTheCommand:
    def slash(self, world, user="U1"):
        body = urlencode(
            {
                "command": "/morgenruf",
                "text": "pulse",
                "user_id": user,
                "team_id": TEAM,
                "channel_id": "C1",
                "trigger_id": "1.2.3",
                "response_url": "https://hooks.slack.com/commands/T1/1/x",
            }
        )
        world.app.dispatch(BoltRequest(body=body, headers={"content-type": ["application/x-www-form-urlencoded"]}))
        return json.dumps(world.responds[-1])

    def test_it_explains_and_says_whether_it_is_on(self, world):
        text = self.slash(world)
        assert "anonymous" in text and "5 people" in text and "on" in text

    def test_admins_are_told_where_to_change_it(self, world):
        world.admins = {"U9"}
        assert "dashboard" in self.slash(world, user="U9").lower()


class TestAppHome:
    def test_members_get_one_line(self, world):
        from src.modules.pulse.handlers import home_blocks

        text = json.dumps(home_blocks(TEAM, "U1"))
        assert "Weekly check-in is on. Answers are anonymous." in text

    def test_admins_see_the_schedule(self, world):
        from src.modules.pulse.handlers import home_blocks

        world.admins = {"U9"}
        text = json.dumps(home_blocks(TEAM, "U9"))
        assert "Friday" in text and "14:00" in text


class TestModule:
    def test_spec(self):
        from src.modules import REGISTRY
        from src.modules.pulse import MODULE

        assert MODULE.name == "pulse" and MODULE.required_scopes == ()
        assert MODULE.default_enabled is False and MODULE.delegable
        assert "pulse" in MODULE.slash_subcommands
        names = [s.name for s in REGISTRY]
        assert names.index("pulse") == names.index("polls") + 1
