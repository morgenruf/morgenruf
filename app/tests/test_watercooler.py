"""Watercooler: the bank, rotation, posting, setup in Slack and the dashboard routes.

Design: docs/design/2026-10-02-watercooler-design.md. 25 September 2026 is a
Friday; 26 and 27 are the weekend.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
import src.core.modules as core_modules
import src.core.workspace_calendar as wc
from src.core.workspace_calendar import Calendar
from src.modules.watercooler import bank, handlers, jobs, messages, rotation

from tests.browser_fixtures import create_test_app

FRIDAY_10_UTC = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
SATURDAY_10_UTC = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
FRI = date(2026, 9, 25)

# ── The bank ────────────────────────────────────────────────────────────────


class TestBank:
    def test_keys_are_unique_and_stable_in_shape(self):
        keys = [q.key for q in bank.QUESTIONS]
        assert len(keys) == len(set(keys))
        assert all(k.split("-")[0] in {"light", "work", "remote", "tot"} for k in keys)

    def test_about_a_hundred_and_fifty_questions_in_every_category(self):
        assert 140 <= len(bank.QUESTIONS) <= 170
        for category in bank.CATEGORIES:
            assert len(bank.in_categories({category})) >= 30, category

    def test_texts_fit_and_read_as_questions(self):
        for q in bank.QUESTIONS:
            assert 5 <= len(q.text) <= 300, q.key
            assert q.text.endswith("?"), q.key

    @pytest.mark.parametrize(
        "word", ["religio", "politic", "church", "vote", "beer", "wine", "drunk", "salary", "weight", "married"]
    )
    def test_steers_clear_of_sensitive_topics(self, word):
        assert not [q.key for q in bank.QUESTIONS if word in q.text.lower()]


# ── Rotation ────────────────────────────────────────────────────────────────


def _first(options):
    return options[0]


class TestRotation:
    def test_no_repeat_inside_a_cycle(self):
        refs = ["b:a", "b:b", "b:c"]
        history: list[str] = []
        seen = []
        for _ in range(3):
            ref = rotation.pick(refs, history)
            seen.append(ref)
            history.insert(0, ref)
        assert sorted(seen) == sorted(refs)

    def test_a_new_cycle_never_opens_with_the_last_question(self):
        refs = ["b:a", "b:b"]
        for _ in range(20):
            assert rotation.pick(refs, ["b:b", "b:a"]) == "b:a"

    def test_editing_the_pool_needs_no_reset(self):
        # c:9 was archived; it no longer counts toward the cycle.
        assert rotation.pick(["b:a", "b:b"], ["c:9", "b:a"], choose=_first) == "b:b"

    def test_empty_pool(self):
        assert rotation.pick([], ["b:a"]) is None

    def test_hidden_and_sources(self):
        light = [q.key for q in bank.in_categories({bank.LIGHT})]
        built = rotation.pool("builtin", [bank.LIGHT], {light[0]}, [7])
        assert f"b:{light[0]}" not in built and "c:7" not in built
        assert rotation.pool("custom", [bank.LIGHT], set(), [7]) == ["c:7"]
        both = rotation.pool("both", [bank.LIGHT], set(), [7])
        assert "c:7" in both and len(both) == len(light) + 1


# ── Posting ─────────────────────────────────────────────────────────────────


class Store:
    """watercooler_* tables in memory, with the posts primary key."""

    def __init__(self):
        self.channels = {
            "C1": {
                "channel_id": "C1",
                "days": "mon,wed,fri",
                "post_time": "10:00",
                "timezone": "UTC",
                "source": "both",
                "categories": "light,work,remote,this_or_that",
                "active": True,
                "paused_reason": None,
                "created_by": "U_LEAD",
            }
        }
        self.posts: dict = {}
        self.questions: list[dict] = []
        self.hidden: set[str] = set()

    def claim(self, team, channel, day, ref):
        if (channel, day) in self.posts:
            return False
        self.posts[(channel, day)] = {"ref": ref, "ts": None}
        return True

    def record(self, team, channel, day, ts):
        self.posts[(channel, day)]["ts"] = ts

    def release(self, team, channel, day):
        if self.posts.get((channel, day), {}).get("ts") is None:
            self.posts.pop((channel, day), None)

    def history(self, team, channel, limit=1000):
        return [
            v["ref"] for (c, d), v in sorted(self.posts.items(), key=lambda kv: kv[0][1], reverse=True) if c == channel
        ]

    def set_active(self, team, channel, active, reason=None):
        ch = self.channels.get(channel)
        if not ch or ch["active"] == active:
            return False
        ch.update(active=active, paused_reason=None if active else reason)
        return True


class Slack:
    def __init__(self):
        self.posts: list[dict] = []
        self.dms: list[dict] = []
        self.reactions: list[dict] = []
        self.fail_with: str | None = None

    def chat_postMessage(self, **kw):
        if kw["channel"].startswith("U"):
            self.dms.append(kw)
            return {"ts": "dm"}
        if self.fail_with:
            exc = RuntimeError(self.fail_with)
            exc.response = {"ok": False, "error": self.fail_with}
            raise exc
        self.posts.append(kw)
        return {"ts": f"{len(self.posts)}.0"}

    def reactions_add(self, **kw):
        self.reactions.append(kw)


@pytest.fixture
def world(monkeypatch):
    store, slack = Store(), Slack()
    state = {"active": True, "calendar": Calendar(), "scopes": {"chat:write"}}
    monkeypatch.setattr(core_modules, "is_active_for", lambda team, name: state["active"])
    monkeypatch.setattr(wc, "load_calendar", lambda team: state["calendar"])
    monkeypatch.setattr(jobs, "bot_client", lambda team: slack)
    monkeypatch.setattr("src.core.db.granted_scopes", lambda team: set(state["scopes"]))
    w = "src.modules.watercooler.db."
    monkeypatch.setattr(w + "get_channel", lambda team, ch: store.channels.get(ch))
    monkeypatch.setattr(w + "list_channels", lambda team: list(store.channels.values()))
    monkeypatch.setattr(w + "list_questions", lambda team, include_archived=True: list(store.questions))
    monkeypatch.setattr(w + "hidden_keys", lambda team: set(store.hidden))
    monkeypatch.setattr(w + "history", store.history)
    monkeypatch.setattr(w + "claim_post", store.claim)
    monkeypatch.setattr(w + "record_post", store.record)
    monkeypatch.setattr(w + "release_post", store.release)
    monkeypatch.setattr(w + "set_channel_active", store.set_active)
    monkeypatch.setattr(w + "purge_old_posts", lambda team: 0)
    return state, store, slack


class TestPosting:
    def test_posts_a_question_from_the_bank(self, world):
        state, store, slack = world
        ts = jobs.run_post("T1", "C1", now=FRIDAY_10_UTC)
        assert ts == "1.0"
        post = slack.posts[0]
        assert post["channel"] == "C1" and post["blocks"][0]["text"]["text"] == "☕ Watercooler"
        ref = store.posts[("C1", FRI)]["ref"]
        assert ref.startswith("b:") and ref[2:] in bank.BY_KEY

    def test_one_post_a_day_whatever_fires(self, world):
        state, store, slack = world
        jobs.run_post("T1", "C1", now=FRIDAY_10_UTC)
        jobs.run_post("T1", "C1", now=FRIDAY_10_UTC.replace(hour=11))
        jobs.run_post("T1", "C1", now=FRIDAY_10_UTC, force=True)
        assert len(slack.posts) == 1

    def test_post_one_now_then_the_schedule_skips_the_day(self, world):
        state, store, slack = world
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC, force=True)
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC.replace(hour=11)) is None
        assert len(slack.posts) == 1

    def test_skips_holidays_and_days_not_chosen(self, world):
        state, store, slack = world
        state["calendar"] = Calendar(holidays={FRI: "Company day"})
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC) is None
        state["calendar"] = Calendar()
        assert jobs.run_post("T1", "C1", now=SATURDAY_10_UTC) is None
        assert slack.posts == []

    def test_post_one_now_ignores_the_calendar(self, world):
        state, store, slack = world
        assert jobs.run_post("T1", "C1", now=SATURDAY_10_UTC, force=True)

    def test_reacts_only_with_the_scope(self, world):
        state, store, slack = world
        jobs.run_post("T1", "C1", now=FRIDAY_10_UTC)
        assert slack.reactions == []
        state["scopes"] = {"chat:write", "reactions:write"}
        store.posts.clear()
        jobs.run_post("T1", "C1", now=FRIDAY_10_UTC)
        assert slack.reactions[0]["name"] == messages.REACTION

    def test_not_in_channel_pauses_and_tells_the_creator_once(self, world):
        state, store, slack = world
        slack.fail_with = "not_in_channel"
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC) is None
        assert store.channels["C1"]["active"] is False
        assert store.channels["C1"]["paused_reason"] == "not_in_channel"
        assert store.posts == {}
        assert [d["channel"] for d in slack.dms] == ["U_LEAD"]
        # Paused: the next firing does nothing and says nothing.
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC.replace(hour=11)) is None
        assert len(slack.dms) == 1

    def test_other_slack_errors_release_without_pausing(self, world):
        state, store, slack = world
        slack.fail_with = "ratelimited"
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC) is None
        assert store.channels["C1"]["active"] is True
        assert store.posts == {}

    def test_custom_only_with_no_questions_pauses_once(self, world):
        state, store, slack = world
        store.channels["C1"]["source"] = "custom"
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC) is None
        assert store.channels["C1"]["paused_reason"] == "empty_pool"
        assert len(slack.dms) == 1

    def test_custom_questions_are_escaped(self, world):
        state, store, slack = world
        store.channels["C1"]["source"] = "custom"
        store.questions = [{"id": 3, "text": "<!channel> what is up?", "archived": False}]
        jobs.run_post("T1", "C1", now=FRIDAY_10_UTC)
        assert "&lt;!channel&gt;" in slack.posts[0]["blocks"][1]["text"]["text"]

    def test_nothing_when_the_module_is_off(self, world):
        state, store, slack = world
        state["active"] = False
        assert jobs.run_post("T1", "C1", now=FRIDAY_10_UTC) is None


class TestPlanJobs:
    def test_one_job_per_active_channel(self, world, monkeypatch):
        state, store, slack = world
        store.channels["C2"] = {**store.channels["C1"], "channel_id": "C2", "active": False}
        store.channels["C3"] = {**store.channels["C1"], "channel_id": "C3", "timezone": "Not/AZone"}
        specs = jobs.plan_jobs({"team_id": "T1"})
        assert [s.args for s in specs] == [("T1", "C1")]
        assert specs[0].key == "post:C1:1000:UTC:mon,wed,fri"


# ── Slack setup ─────────────────────────────────────────────────────────────


def _submit_body(channel="C1", days=("mon",), time="09:00"):
    return {
        "user": {"id": "U_LEAD", "team_id": "T1"},
        "team": {"id": "T1"},
    }, {
        "private_metadata": "Europe/Berlin",
        "state": {
            "values": {
                "channel": {messages.CHANNEL_ACTION: {"selected_conversation": channel}},
                "days": {messages.DAYS_ACTION: {"selected_options": [{"value": d} for d in days]}},
                "time": {messages.TIME_ACTION: {"selected_time": time}},
            }
        },
    }


class TestSlackSetup:
    def test_a_member_cannot_open_setup(self, monkeypatch):
        monkeypatch.setattr("src.core.db.can_administer", lambda team, user, module=None: False)
        client = MagicMock()
        handlers.handle_command({"team_id": "T1", "user_id": "U1", "trigger_id": "x"}, client, None, "")
        client.views_open.assert_not_called()
        assert "in charge of Watercooler" in client.chat_postMessage.call_args.kwargs["text"]

    def test_a_mocked_truthy_permission_is_not_trusted(self, monkeypatch):
        monkeypatch.setattr("src.core.db.can_administer", lambda team, user, module=None: MagicMock())
        assert handlers.may_manage("T1", "U1") is False

    @pytest.mark.parametrize(
        ("kwargs", "field"),
        [({"channel": "D123"}, "channel"), ({"days": ()}, "days"), ({"time": "25:00"}, "time")],
    )
    def test_the_modal_validates(self, monkeypatch, kwargs, field):
        monkeypatch.setattr("src.core.db.can_administer", lambda team, user, module=None: True)
        ack = MagicMock()
        body, view = _submit_body(**kwargs)
        handlers.handle_submit(ack, body, view, MagicMock())
        assert field in ack.call_args.kwargs["errors"]

    def test_submit_saves_the_channel(self, monkeypatch):
        saved = {}
        monkeypatch.setattr("src.core.db.can_administer", lambda team, user, module=None: True)
        monkeypatch.setattr("src.modules.watercooler.db.get_channel", lambda team, ch: None)
        monkeypatch.setattr("src.modules.watercooler.db.count_channels", lambda team: 0)
        monkeypatch.setattr(
            "src.modules.watercooler.db.save_channel",
            lambda team, ch, fields, created_by: saved.update(ch=ch, **fields, by=created_by) or {},
        )
        monkeypatch.setattr("src.core.standup_invites.bot_channel_ids", lambda client: {"C1"})
        ack = MagicMock()
        client = MagicMock()
        body, view = _submit_body(days=("fri", "mon"))
        handlers.handle_submit(ack, body, view, client)
        ack.assert_called_once_with()
        assert saved == {
            "ch": "C1",
            "days": "mon,fri",
            "post_time": "09:00",
            "timezone": "Europe/Berlin",
            "active": True,
            "paused_reason": None,
            "by": "U_LEAD",
        }
        assert "Watercooler is set for <#C1>" in client.chat_postMessage.call_args.kwargs["text"]

    def test_quick_start_extra_switches_the_module_on(self, monkeypatch):
        calls = []
        monkeypatch.setattr("src.core.db.set_module_enabled", lambda team, name, on: calls.append((name, on)))
        monkeypatch.setattr("src.modules.watercooler.db.get_channel", lambda team, ch: None)
        monkeypatch.setattr(
            "src.modules.watercooler.db.save_channel",
            lambda team, ch, fields, created_by: calls.append((ch, fields["days"], fields["timezone"])),
        )
        handlers.start_default("T1", "C1", "U1", "Asia/Kolkata")
        assert calls == [("watercooler", True), ("C1", "mon,wed,fri", "Asia/Kolkata")]


class TestQuickStartModal:
    def test_the_extra_is_offered_ticked(self, monkeypatch):
        from src.modules.standup import quickstart

        offers = [("watercooler", "Also post a watercooler question here Mon, Wed, Fri", lambda *a: None)]
        view = quickstart.modal("UTC", offers)
        extras = next(b for b in view["blocks"] if b.get("block_id") == "extras")
        assert extras["element"]["initial_options"] == extras["element"]["options"]
        assert extras["element"]["options"][0]["value"] == "watercooler"

    def test_no_extras_block_without_offers(self):
        from src.modules.standup import quickstart

        assert all(b.get("block_id") != "extras" for b in quickstart.modal("UTC")["blocks"])


# ── Dashboard ───────────────────────────────────────────────────────────────


@pytest.fixture
def browser(monkeypatch):
    app = create_test_app(monkeypatch)
    return app.test_client(), app.extensions["browser_test_data"]


def _as(client, role):
    return {"X-CSRF-Token": client.post(f"/__test__/session?role={role}").json["csrf_token"]}


class TestDashboard:
    def test_overview_lists_channels_bank_and_own_questions(self, browser):
        client, state = browser
        _as(client, "member")
        body = client.get("/dashboard/api/watercooler").json
        assert body["channels"][0]["channel_id"] == "C_GENERAL"
        assert len(body["bank"]) == len(bank.QUESTIONS)
        assert body["questions"][0]["text"] == "What did you build this week?"
        assert body["can_manage"] is False

    def test_members_cannot_change_anything(self, browser):
        client, state = browser
        headers = _as(client, "member")
        assert (
            client.put("/dashboard/api/watercooler/bank/light-001", json={"hidden": True}, headers=headers).status_code
            == 403
        )
        assert (
            client.post(
                "/dashboard/api/watercooler/questions", json={"text": "Hello there?"}, headers=headers
            ).status_code
            == 403
        )
        assert state.watercooler_hidden == set()

    def test_hiding_is_for_this_workspace_only(self, browser):
        client, state = browser
        headers = _as(client, "admin")
        response = client.put("/dashboard/api/watercooler/bank/light-001", json={"hidden": True}, headers=headers)
        assert response.status_code == 200 and response.json["hidden"] is True
        assert state.watercooler_hidden == {"light-001"}
        # The shared bank itself is untouched.
        assert "light-001" in bank.BY_KEY
        assert (
            client.put("/dashboard/api/watercooler/bank/nope", json={"hidden": True}, headers=headers).status_code
            == 404
        )

    def test_channel_validation_and_limit(self, browser, monkeypatch):
        client, state = browser
        headers = _as(client, "admin")
        bad_tz = {"days": ["mon"], "post_time": "10:00", "timezone": "Not/AZone"}
        assert client.put("/dashboard/api/watercooler/channels/C_X", json=bad_tz, headers=headers).status_code == 400
        good = {"days": ["mon"], "post_time": "10:00", "timezone": "UTC"}
        assert client.put("/dashboard/api/watercooler/channels/D_X", json=good, headers=headers).status_code == 400
        import src.modules.watercooler.db as wdb

        monkeypatch.setattr(wdb, "MAX_CHANNELS", 1)
        assert client.put("/dashboard/api/watercooler/channels/C_NEW", json=good, headers=headers).status_code == 400

    def test_saving_resumes_a_paused_channel(self, browser):
        client, state = browser
        state.watercooler_channels["C_GENERAL"].update(active=False, paused_reason="not_in_channel")
        headers = _as(client, "admin")
        body = {"days": ["mon", "fri"], "post_time": "09:15", "timezone": "UTC", "active": True}
        response = client.put("/dashboard/api/watercooler/channels/C_GENERAL", json=body, headers=headers)
        assert response.status_code == 200
        assert response.json["active"] is True and response.json["paused_reason"] is None

    def test_question_limit(self, browser, monkeypatch):
        client, state = browser
        headers = _as(client, "admin")
        import src.modules.watercooler.db as wdb

        monkeypatch.setattr(wdb, "MAX_QUESTIONS", 1)
        response = client.post("/dashboard/api/watercooler/questions", json={"text": "One more?"}, headers=headers)
        assert response.status_code == 400

    def test_a_watercooler_admin_who_is_not_a_workspace_admin(self, browser):
        client, state = browser
        state.grants["U_MEMBER"] = {"watercooler"}
        headers = _as(client, "member")
        response = client.post(
            "/dashboard/api/watercooler/questions", json={"text": "Favourite tool?"}, headers=headers
        )
        assert response.status_code == 201
