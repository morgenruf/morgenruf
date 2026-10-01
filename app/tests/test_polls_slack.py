"""Polls in Slack, through the app's real listeners.

Builds a Bolt app the way create_app does and sends it the requests Slack
sends: `/morgenruf poll`, the form, the vote and close buttons. Storage is an
in-memory stand-in that keeps the rules polls.db enforces in SQL (one row per
person per option, one choice moves, the same choice again removes).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlencode

import pytest
from flask import Flask
from slack_bolt import App, BoltRequest
from slack_bolt.authorization import AuthorizeResult
from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient
from slack_sdk.webhook import WebhookClient

TEAM = "T1"
CREATOR = "U0CREATOR"
VOTER = "U0VOTER"
OTHER = "U0OTHER"
IN = "C0IN"
OUT = "C0OUT"


class Store:
    """polls.db, in memory."""

    def __init__(self):
        self.polls: dict[int, dict] = {}
        self.votes: set[tuple[int, int, str]] = set()
        self.next_id = 1
        self.set_message_failures = 0

    def create_poll(
        self, team_id, created_by, channel_id, question, options, anonymous, multiple, hide_results, closes_at
    ):
        pid = self.next_id
        self.next_id += 1
        self.polls[pid] = {
            "id": pid,
            "team_id": team_id,
            "created_by": created_by,
            "channel_id": channel_id,
            "message_ts": None,
            "question": question,
            "options": list(options),
            "anonymous": anonymous,
            "multiple": multiple,
            "hide_results": hide_results,
            "salt": b"s" * 32 if anonymous else None,
            "closes_at": closes_at,
            "closed_at": None,
            "created_at": None,
        }
        return pid

    def get_poll(self, pid):
        poll = self.polls.get(pid)
        return dict(poll) if poll else None

    def set_message(self, pid, ts):
        if self.set_message_failures:
            self.set_message_failures -= 1
            raise RuntimeError("db blip")
        self.polls[pid]["message_ts"] = ts

    def redraw(self, pid, draw):
        poll = self.get_poll(pid)
        if not poll:
            return False
        names = None if poll["anonymous"] else self.voters(pid)
        draw(poll, self.tally(pid), names)
        return True

    def open_poll_ids(self, team_id):
        return [p["id"] for p in self.polls.values() if p["team_id"] == team_id and not p["closed_at"]]

    def delete_poll(self, pid):
        self.polls.pop(pid, None)

    def toggle_vote(self, pid, idx, key, multiple):
        if self.polls[pid]["closed_at"]:
            return False
        if (pid, idx, key) in self.votes:
            self.votes.discard((pid, idx, key))
            return True
        if not multiple:
            self.votes = {v for v in self.votes if not (v[0] == pid and v[2] == key)}
        self.votes.add((pid, idx, key))
        return True

    def tally(self, pid):
        counts = [0] * len(self.polls[pid]["options"])
        for p, idx, _ in self.votes:
            if p == pid:
                counts[idx] += 1
        return counts

    def voters(self, pid):
        if self.polls[pid]["anonymous"]:
            raise ValueError("anonymous")
        out: dict[int, list[str]] = {}
        for p, idx, key in sorted(self.votes):
            if p == pid:
                out.setdefault(idx, []).append(key)
        return out

    def my_choices(self, pid, key):
        return sorted(idx for p, idx, k in self.votes if p == pid and k == key)

    def close_poll(self, pid):
        poll = self.polls.get(pid)
        if not poll or poll["closed_at"]:
            return False
        poll["closed_at"] = "now"
        poll["salt"] = None
        return True

    def open_polls_by(self, team_id, user_id, limit=3):
        return [
            {"id": p["id"], "channel_id": p["channel_id"], "question": p["question"]}
            for p in self.polls.values()
            if p["created_by"] == user_id and not p["closed_at"]
        ][:limit]


@pytest.fixture
def world(monkeypatch):
    import src.core.analytics as analytics
    import src.core.db as core_db
    import src.modules.polls.db as pdb

    store = Store()
    state = SimpleNamespace(
        store=store,
        posts=[],
        updates=[],
        ephemerals=[],
        responds=[],
        views=[],
        captures=[],
        channels={IN},
        settings={},
        admins=set(),
        membership_error=None,
        post_error=None,
        deletes=[],
        delete_error=None,
    )
    for name in (
        "create_poll",
        "get_poll",
        "set_message",
        "delete_poll",
        "toggle_vote",
        "tally",
        "voters",
        "my_choices",
        "close_poll",
        "open_polls_by",
        "redraw",
        "open_poll_ids",
    ):
        monkeypatch.setattr(pdb, name, getattr(store, name))
    monkeypatch.setattr(core_db, "granted_scopes", lambda team_id: set())
    monkeypatch.setattr(core_db, "module_settings", lambda team_id: dict(state.settings))
    monkeypatch.setattr(core_db, "can_administer", lambda team_id, user_id, module=None: user_id in state.admins)
    monkeypatch.setattr(core_db, "get_all_members", lambda team_id: [])
    monkeypatch.setattr(analytics, "capture", lambda event, team_id, **props: state.captures.append((event, props)))

    def users_conversations(self, **kwargs):
        if state.membership_error:
            raise state.membership_error
        return {"ok": True, "channels": [{"id": c} for c in state.channels]}

    def chat_postMessage(self, **kwargs):  # noqa: N802
        if state.post_error and kwargs.get("channel") in (IN, OUT):
            raise state.post_error
        state.posts.append(kwargs)
        return {"ok": True, "ts": f"{len(state.posts)}.000", "channel": kwargs.get("channel")}

    def chat_update(self, **kwargs):
        state.updates.append(kwargs)
        return {"ok": True}

    def chat_postEphemeral(self, **kwargs):  # noqa: N802
        state.ephemerals.append(kwargs)
        return {"ok": True}

    def views_open(self, **kwargs):
        state.views.append(kwargs)
        return {"ok": True}

    def users_info(self, **kwargs):
        return {"ok": True, "user": {"id": kwargs.get("user"), "tz": "UTC"}}

    def chat_delete(self, **kwargs):
        if state.delete_error:
            raise state.delete_error
        state.deletes.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(WebClient, "chat_delete", chat_delete)
    monkeypatch.setattr(WebClient, "users_conversations", users_conversations)
    monkeypatch.setattr(WebClient, "chat_postMessage", chat_postMessage)
    monkeypatch.setattr(WebClient, "chat_update", chat_update)
    monkeypatch.setattr(WebClient, "chat_postEphemeral", chat_postEphemeral)
    monkeypatch.setattr(WebClient, "views_open", views_open)
    monkeypatch.setattr(WebClient, "users_info", users_info)
    monkeypatch.setattr(WebhookClient, "send_dict", lambda self, body: state.responds.append(body))

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


def slash(world, text, user=CREATOR, channel=IN):
    body = urlencode(
        {
            "command": "/morgenruf",
            "text": text,
            "user_id": user,
            "team_id": TEAM,
            "channel_id": channel,
            "trigger_id": "1.2.3",
            "response_url": "https://hooks.slack.com/commands/T1/1/x",
        }
    )
    return world.app.dispatch(BoltRequest(body=body, headers={"content-type": ["application/x-www-form-urlencoded"]}))


def click(world, action_id, user=VOTER, ts="1.000"):
    payload = {
        "type": "block_actions",
        "team": {"id": TEAM},
        "user": {"id": user, "team_id": TEAM},
        "channel": {"id": IN},
        "container": {"type": "message", "message_ts": ts, "channel_id": IN},
        "message": {"ts": ts},
        "trigger_id": "1.2.3",
        "actions": [{"action_id": action_id, "block_id": "b", "type": "button", "value": "x"}],
    }
    body = urlencode({"payload": json.dumps(payload)})
    return world.app.dispatch(BoltRequest(body=body, headers={"content-type": ["application/x-www-form-urlencoded"]}))


def submit(world, question="Lunch?", options="Pizza\nSushi", channel=IN, checks=(), close="never", user=CREATOR):
    values = {
        "question": {"polls:question": {"type": "plain_text_input", "value": question}},
        "options": {"polls:options": {"type": "plain_text_input", "value": options}},
        "channel": {"polls:channel": {"type": "conversations_select", "selected_conversation": channel}},
        "settings": {"polls:settings": {"type": "checkboxes", "selected_options": [{"value": c} for c in checks]}},
        "close": {"polls:close_after": {"type": "static_select", "selected_option": {"value": close}}},
    }
    payload = {
        "type": "view_submission",
        "team": {"id": TEAM},
        "user": {"id": user, "team_id": TEAM},
        "view": {
            "id": "V1",
            "type": "modal",
            "callback_id": "polls:create",
            "state": {"values": values},
            "private_metadata": "",
        },
    }
    body = urlencode({"payload": json.dumps(payload)})
    return world.app.dispatch(BoltRequest(body=body, headers={"content-type": ["application/x-www-form-urlencoded"]}))


def vote_ids(blocks) -> list[str]:
    return [
        b["accessory"]["action_id"]
        for b in blocks
        if b.get("type") == "section" and b.get("accessory", {}).get("action_id", "").startswith("polls:vote:")
    ]


def last_blocks(world):
    return (world.updates or world.posts)[-1]["blocks"]


def quick_poll(world, text='"Lunch?" "Pizza" "Sushi"'):
    slash(world, f"poll {text}")
    return world.store.polls[max(world.store.polls)]


class TestQuickSyntax:
    def test_in_a_channel_the_bot_is_in_it_creates_and_posts(self, world):
        slash(world, 'poll "Lunch?" "Pizza" "Sushi" "Tacos"')
        assert len(world.store.polls) == 1
        poll = world.store.polls[1]
        assert poll["channel_id"] == IN and poll["created_by"] == CREATOR
        assert poll["message_ts"] == "1.000"
        post = world.posts[0]
        assert post["channel"] == IN
        assert vote_ids(post["blocks"]) == ["polls:vote:1:0", "polls:vote:1:1", "polls:vote:1:2"]
        assert ("poll_created", {"options": 3, "anonymous": False, "multiple": False, "hide_results": False}) in [
            (e, p) for e, p in world.captures
        ]

    def test_bot_not_in_channel_creates_nothing_and_explains_the_invite(self, world):
        slash(world, 'poll "Lunch?" "Pizza" "Sushi"', channel=OUT)
        assert world.store.polls == {}
        assert world.posts == []
        text = json.dumps(world.responds)
        assert "/invite @Morgenruf" in text and "Add agents and apps" in text
        assert f"<#{OUT}>" in text

    def test_a_membership_check_that_fails_creates_nothing(self, world):
        world.membership_error = SlackApiError("boom", {"ok": False, "error": "ratelimited"})
        slash(world, 'poll "Lunch?" "Pizza" "Sushi"')
        assert world.store.polls == {}
        assert world.responds

    def test_a_failed_post_leaves_no_poll_behind(self, world):
        world.post_error = SlackApiError("boom", {"ok": False, "error": "not_in_channel"})
        slash(world, 'poll "Lunch?" "Pizza" "Sushi"')
        assert world.store.polls == {}
        assert world.responds

    def test_bad_syntax_shows_how(self, world):
        slash(world, "poll Lunch? Pizza")
        assert world.store.polls == {}
        assert "/morgenruf poll" in json.dumps(world.responds)

    def test_duplicate_options_are_refused(self, world):
        slash(world, 'poll "Lunch?" "Pizza" "pizza"')
        assert world.store.polls == {}
        assert world.responds

    def test_bare_command_opens_the_form_on_this_channel(self, world):
        slash(world, "poll")
        view = world.views[0]["view"]
        assert view["callback_id"] == "polls:create"
        channel = next(b for b in view["blocks"] if b.get("block_id") == "channel")
        assert channel["element"]["initial_conversation"] == IN

    def test_bare_command_in_a_dm_opens_the_form_without_a_channel(self, world):
        slash(world, "poll", channel="D0DM")
        channel = next(b for b in world.views[0]["view"]["blocks"] if b.get("block_id") == "channel")
        assert "initial_conversation" not in channel["element"]

    def test_turned_off_it_is_help(self, world):
        world.settings = {"polls": False}
        slash(world, 'poll "Lunch?" "Pizza" "Sushi"')
        assert world.store.polls == {}
        assert "know `poll`" in json.dumps(world.posts)


class TestSavingTheMessage:
    def test_a_failed_save_is_retried_once_and_the_poll_kept(self, world):
        world.store.set_message_failures = 1
        slash(world, 'poll "Lunch?" "Pizza" "Sushi"')
        assert world.store.polls[1]["message_ts"] == "1.000"
        assert world.deletes == []

    def test_two_failed_saves_take_the_message_down_and_the_row(self, world):
        world.store.set_message_failures = 2
        slash(world, 'poll "Lunch?" "Pizza" "Sushi"')
        assert world.deletes == [{"channel": IN, "ts": "1.000"}]
        assert world.store.polls == {}
        assert "try again" in json.dumps(world.responds).lower()

    def test_if_the_message_cannot_be_taken_down_the_row_stays(self, world):
        """Never a live message with no row behind it: votes on it would go nowhere."""
        world.store.set_message_failures = 2
        world.delete_error = RuntimeError("message_not_found")
        slash(world, 'poll "Lunch?" "Pizza" "Sushi"')
        assert 1 in world.store.polls


class TestTheForm:
    def errors(self, response):
        return json.loads(response.body)["errors"]

    def test_missing_question(self, world):
        assert "question" in self.errors(submit(world, question=""))

    def test_too_few_options(self, world):
        assert "options" in self.errors(submit(world, options="Pizza\n\n"))

    def test_too_many_options(self, world):
        assert "options" in self.errors(submit(world, options="\n".join(str(i) for i in range(11))))

    def test_duplicate_options(self, world):
        assert "options" in self.errors(submit(world, options="Pizza\nPizza"))

    def test_option_too_long(self, world):
        assert "options" in self.errors(submit(world, options="Pizza\n" + "x" * 76))

    def test_not_a_channel(self, world):
        assert "channel" in self.errors(submit(world, channel="D0DM"))

    def test_nothing_is_created_on_an_error(self, world):
        submit(world, question="")
        assert world.store.polls == {}

    def test_a_good_form_posts_the_poll_with_its_settings(self, world):
        response = submit(world, checks=("anonymous", "multiple", "hide_results"), close="1h")
        assert response.status == 200 and not response.body
        poll = world.store.polls[1]
        assert poll["anonymous"] and poll["multiple"] and poll["hide_results"]
        assert poll["closes_at"] is not None
        assert len(vote_ids(world.posts[0]["blocks"])) == 2

    def test_bot_not_in_channel_dms_the_creator_and_creates_nothing(self, world):
        submit(world, channel=OUT)
        assert world.store.polls == {}
        dm = world.posts[-1]
        assert dm["channel"] == CREATOR
        assert "/invite @Morgenruf" in dm["text"] and "Add agents and apps" in dm["text"]


class TestVoting:
    def test_one_choice_moves_and_the_same_choice_removes(self, world):
        quick_poll(world)
        click(world, "polls:vote:1:0")
        assert world.store.tally(1) == [1, 0]
        click(world, "polls:vote:1:1")
        assert world.store.tally(1) == [0, 1]
        click(world, "polls:vote:1:1")
        assert world.store.tally(1) == [0, 0]

    def test_multiple_choice_keeps_both(self, world):
        submit(world, checks=("multiple",))
        click(world, "polls:vote:1:0")
        click(world, "polls:vote:1:1")
        assert world.store.tally(1) == [1, 1]

    def test_the_message_is_updated_in_place(self, world):
        quick_poll(world)
        click(world, "polls:vote:1:0")
        update = world.updates[-1]
        assert update["channel"] == IN and update["ts"] == "1.000"
        assert "1 (100%)" in json.dumps(update["blocks"])

    def test_named_poll_shows_who_voted(self, world):
        quick_poll(world)
        click(world, "polls:vote:1:0", user=VOTER)
        assert f"<@{VOTER}>" in json.dumps(last_blocks(world))

    def test_anonymous_poll_names_no_one_but_the_creator(self, world):
        submit(world, checks=("anonymous",))
        click(world, "polls:vote:1:0", user=VOTER)
        click(world, "polls:vote:1:1", user=OTHER)
        text = json.dumps(last_blocks(world))
        assert VOTER not in text and OTHER not in text
        mentions = [m for m in text.split("<@")[1:]]
        assert all(m.startswith(CREATOR) for m in mentions)
        assert world.store.votes and all(VOTER not in key and OTHER not in key for _, _, key in world.store.votes)

    def test_anonymous_vote_is_confirmed_only_to_the_voter(self, world):
        submit(world, checks=("anonymous",))
        click(world, "polls:vote:1:1", user=VOTER)
        eph = world.ephemerals[-1]
        assert eph["user"] == VOTER and eph["channel"] == IN
        assert "Sushi" in eph["text"] and "Only you can see this" in eph["text"]

    def test_hidden_results_show_no_count_per_option_until_close(self, world):
        submit(world, checks=("hide_results",))
        click(world, "polls:vote:1:0", user=VOTER)
        click(world, "polls:vote:1:0", user=OTHER)
        before = json.dumps(world.updates[-1]["blocks"], ensure_ascii=False)
        assert "2 votes so far" in before
        assert "▓" not in before and "(100%)" not in before and "░" not in before
        click(world, "polls:close:1", user=CREATOR)
        after = json.dumps(world.updates[-1]["blocks"], ensure_ascii=False)
        assert "▓" in after and "2 (100%)" in after

    def test_a_vote_racing_a_close_never_reopens_the_message(self, world, monkeypatch):
        import src.modules.polls.db as pdb

        quick_poll(world)
        real_toggle = world.store.toggle_vote

        def toggle_then_close(*args):
            result = real_toggle(*args)
            world.store.close_poll(1)  # the Close lands between the vote and the redraw
            return result

        monkeypatch.setattr(pdb, "toggle_vote", toggle_then_close)
        click(world, "polls:vote:1:0")
        blocks = world.updates[-1]["blocks"]
        assert vote_ids(blocks) == []
        assert "Closed" in json.dumps(blocks)

    def test_a_closed_poll_takes_no_vote(self, world, monkeypatch):
        import src.modules.polls.db as pdb

        quick_poll(world)
        world.store.close_poll(1)
        called = []
        monkeypatch.setattr(pdb, "toggle_vote", lambda *a, **k: called.append(a))
        click(world, "polls:vote:1:0")
        assert called == []
        assert "This poll is closed." in world.ephemerals[-1]["text"]

    def test_a_vote_after_polls_is_turned_off_is_refused_politely(self, world):
        quick_poll(world)
        world.settings = {"polls": False}
        click(world, "polls:vote:1:0")
        assert world.store.tally(1) == [0, 0]
        assert "turned off" in world.ephemerals[-1]["text"]

    def test_an_open_anonymous_poll_without_its_salt_takes_no_vote(self, world):
        """Only after a restore: backups leave poll_salts empty on purpose."""
        submit(world, checks=("anonymous",))
        world.store.polls[1]["salt"] = None
        click(world, "polls:vote:1:0")
        assert world.store.votes == set()
        assert world.ephemerals[-1]["text"] == "This poll can't take votes any more."

    def test_a_vote_for_a_missing_poll(self, world):
        click(world, "polls:vote:99:0")
        assert "This poll is closed." in world.ephemerals[-1]["text"]


class TestClosing:
    def test_someone_else_cannot_close_it(self, world):
        quick_poll(world)
        click(world, "polls:close:1", user=OTHER)
        assert world.store.polls[1]["closed_at"] is None
        assert world.ephemerals[-1]["user"] == OTHER

    def test_the_creator_closes_it(self, world):
        quick_poll(world)
        click(world, "polls:vote:1:0")
        click(world, "polls:close:1", user=CREATOR)
        assert world.store.polls[1]["closed_at"]
        blocks = world.updates[-1]["blocks"]
        assert vote_ids(blocks) == []
        assert "Closed" in json.dumps(blocks)
        assert ("poll_closed", {"options": 2, "votes": 1}) in world.captures

    def test_an_admin_closes_it(self, world):
        quick_poll(world)
        world.admins = {OTHER}
        click(world, "polls:close:1", user=OTHER)
        assert world.store.polls[1]["closed_at"]

    def test_closing_twice_updates_once(self, world):
        quick_poll(world)
        click(world, "polls:close:1", user=CREATOR)
        updates = len(world.updates)
        click(world, "polls:close:1", user=CREATOR)
        assert len(world.updates) == updates

    def test_the_close_button_asks_first(self, world):
        quick_poll(world)
        buttons = [e for b in world.posts[0]["blocks"] if b.get("type") == "actions" for e in b["elements"]]
        close = next(e for e in buttons if e["action_id"] == "polls:close:1")
        assert close["style"] == "danger" and "confirm" in close


class TestEscaping:
    def test_broadcasts_and_links_in_options_are_shown_as_text(self, world):
        slash(world, 'poll "Who? <!here>" "<!channel>" "<https://evil.example|safe>"')
        text = json.dumps(world.posts[0]["blocks"])
        assert "<!channel>" not in text and "<!here>" not in text
        assert "<https://evil.example" not in text
        assert "&lt;!channel&gt;" in text

    def test_mentions_and_channels_stay_real_mentions(self, world):
        slash(world, 'poll "Who leads, <@U0LEAD|sam>?" "<@U0LEAD|sam>" "<#C0TEAM|team>" "<https://example.com|docs>"')
        text = json.dumps(world.posts[0]["blocks"])
        assert "<@U0LEAD>" in text and "<#C0TEAM>" in text
        assert "|sam" not in text and "<https://" not in text and "https://example.com" in text

    def test_slack_encoded_broadcasts_stay_text_too(self, world):
        slash(world, 'poll "Q" "&lt;!channel&gt;" "b"')
        text = json.dumps(world.posts[0]["blocks"])
        assert "<!channel>" not in text


class TestTurningPollsOff:
    def test_every_open_poll_is_closed_and_redrawn(self, world, monkeypatch):
        import src.modules.polls.jobs as jobs
        from src.modules.polls import MODULE

        monkeypatch.setattr(jobs, "bot_client", lambda team_id: WebClient(token="xoxb-1"))
        quick_poll(world)
        submit(world, checks=("anonymous",))
        MODULE.on_disable(TEAM)
        assert all(p["closed_at"] for p in world.store.polls.values())
        assert world.store.polls[2]["salt"] is None
        assert all(vote_ids(u["blocks"]) == [] for u in world.updates[-2:])

    def test_a_slack_error_still_closes_the_rest(self, world, monkeypatch):
        import src.modules.polls.jobs as jobs
        from src.modules.polls import MODULE

        client = MagicMock()
        client.chat_update.side_effect = RuntimeError("channel_not_found")
        monkeypatch.setattr(jobs, "bot_client", lambda team_id: client)
        quick_poll(world)
        quick_poll(world)
        MODULE.on_disable(TEAM)
        assert all(p["closed_at"] for p in world.store.polls.values())


class TestAppHome:
    def test_create_button_and_my_open_polls(self, world):
        from src.modules.polls.handlers import home_blocks

        quick_poll(world)
        text = json.dumps(home_blocks(TEAM, CREATOR))
        assert "polls:open" in text and "Lunch?" in text and f"<#{IN}>" in text

    def test_the_create_button_opens_the_form(self, world):
        click(world, "polls:open", user=CREATOR)
        assert world.views[0]["view"]["callback_id"] == "polls:create"


class TestModule:
    def test_spec(self):
        from src.modules import REGISTRY
        from src.modules.polls import MODULE

        assert MODULE.name == "polls" and MODULE.required_scopes == ()
        assert MODULE.default_enabled and MODULE.delegable
        assert "poll" in MODULE.slash_subcommands
        names = [s.name for s in REGISTRY]
        assert names.index("polls") == names.index("kudos") + 1


class TestMessageBlocks:
    POLL = {
        "id": 3,
        "question": "Q",
        "options": ["a", "b"],
        "anonymous": False,
        "multiple": False,
        "hide_results": False,
        "created_by": CREATOR,
        "closes_at": None,
    }

    def test_more_than_ten_voters_are_summarised(self):
        from src.modules.polls.blocks import poll_message

        voters = [f"U{i:03d}" for i in range(13)]
        text = json.dumps(poll_message(self.POLL, [13, 0], {0: voters}, closed=False))
        assert "<@U009>" in text and "<@U010>" not in text and "+3" in text

    def test_an_anonymous_poll_drops_names_even_if_given_some(self):
        from src.modules.polls.blocks import poll_message

        text = json.dumps(poll_message({**self.POLL, "anonymous": True}, [1, 0], {0: [VOTER]}, closed=True))
        assert VOTER not in text

    def test_bars_have_ten_cells(self):
        from src.modules.polls.blocks import poll_message

        blocks = poll_message(self.POLL, [4, 6], {}, closed=False)
        lines = [b["elements"][0]["text"] for b in blocks if b["type"] == "context" and "%" in b["elements"][0]["text"]]
        assert lines[0].startswith("▓▓▓▓░░░░░░ 4 (40%)")
        assert lines[1].startswith("▓▓▓▓▓▓░░░░ 6 (60%)")

    def test_a_closing_time_is_shown_in_the_readers_timezone(self):
        from datetime import datetime, timezone

        from src.modules.polls.blocks import poll_message

        closes = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
        text = json.dumps(poll_message({**self.POLL, "closes_at": closes}, [0, 0], {}, closed=False))
        assert f"<!date^{int(closes.timestamp())}^" in text
