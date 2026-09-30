"""Kudos given in Slack reach the database, through the app's real listeners.

Production had no kudos rows at all, from either entry point:

* `/kudos @Anmol Nagpal for reviewing the fix`: the command was declared
  without should_escape, so Slack sent the mention as plain text. The handler
  only understood `<@U123>`, found nobody, saved nothing, and still showed a
  "wants to recognise someone" card as if it had worked.
* `kudos @Anmol ...` sent by DM: Bolt runs only the first listener matching an
  event, and core's catch-all DM listener is registered before every module,
  so kudos' own message listener never ran.

These tests build a Bolt app with the listeners registered the way create_app
registers them, and send it the requests Slack sends.
"""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlencode

import pytest
import yaml
from flask import Flask
from slack_bolt import App, BoltRequest
from slack_bolt.authorization import AuthorizeResult
from slack_sdk.web import WebClient

ROOT = pathlib.Path(__file__).resolve().parents[2]

GIVER = "U0GIVER"
ANMOL = "U0ANMOL"
TEAM = "T1"

MEMBERS = [
    {"user_id": GIVER, "real_name": "Giver Person", "display_name": "giver", "active": True, "tz": "UTC"},
    {"user_id": ANMOL, "real_name": "Anmol Nagpal", "display_name": "anmol", "active": True, "tz": "UTC"},
    {"user_id": "U0SAM1", "real_name": "Sam Lee", "display_name": "sam", "active": True, "tz": "UTC"},
    {"user_id": "U0SAM2", "real_name": "Sam Park", "display_name": "sam", "active": True, "tz": "UTC"},
]


def _bolt_app() -> App:
    return App(
        signing_secret="x",
        authorize=lambda **kw: AuthorizeResult(
            enterprise_id=None, team_id=TEAM, bot_token="xoxb-1", bot_user_id="UBOT", bot_id="B1"
        ),
        request_verification_enabled=False,
        process_before_response=True,
    )


@pytest.fixture
def world(monkeypatch):
    """A workspace with kudos on, a roster, and every Slack call recorded."""
    import src.core.analytics as analytics
    import src.core.db as core_db
    import src.modules.kudos.db as kdb

    state = SimpleNamespace(
        saved=[],
        posts=[],
        members=list(MEMBERS),
        workspace_config={"channel_id": ""},
        kudos_config={"emoji": "\N{MAPLE LEAF}", "daily_allowance": 5, "token_auto": True, "channel_id": ""},
        post_errors={},
        allowance={"emoji": "\N{MAPLE LEAF}", "allowance": 5, "used": 0, "remaining": 5, "can_give": True},
        settings={},
        save_error=None,
    )

    def save_kudos(team_id, from_user, to_user, message, channel_id="", emoji=None):
        if state.save_error:
            raise state.save_error
        row = {"team_id": team_id, "from_user": from_user, "to_user": to_user, "message": message, "emoji": emoji}
        state.saved.append(row)
        return row

    monkeypatch.setattr(kdb, "save_kudos", save_kudos)
    monkeypatch.setattr(kdb, "allowance_state", lambda *a, **k: dict(state.allowance))
    monkeypatch.setattr(kdb, "get_config", lambda team_id: dict(state.kudos_config))
    monkeypatch.setattr(core_db, "get_all_members", lambda team_id: list(state.members))
    monkeypatch.setattr(core_db, "get_workspace_config", lambda team_id: dict(state.workspace_config))
    monkeypatch.setattr(core_db, "granted_scopes", lambda team_id: set())
    monkeypatch.setattr(core_db, "module_settings", lambda team_id: dict(state.settings))
    monkeypatch.setattr(analytics, "capture", lambda *a, **k: True)

    def chat_postMessage(self, **kwargs):  # noqa: N802
        error = state.post_errors.get(kwargs.get("channel"))
        if error:
            raise error
        state.posts.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(WebClient, "chat_postMessage", chat_postMessage)

    from src.main import register_slack_listeners
    from src.modules import REGISTRY

    app = _bolt_app()
    register_slack_listeners(Flask(__name__), app, list(REGISTRY))
    state.app = app
    return state


def _dm(app: App, text: str, **extra) -> None:
    event = {
        "type": "message",
        "channel_type": "im",
        "channel": "D0GIVER",
        "user": GIVER,
        "team": TEAM,
        "text": text,
        "ts": "1700000000.000100",
        **extra,
    }
    body = {"type": "event_callback", "team_id": TEAM, "event": event}
    app.dispatch(BoltRequest(body=json.dumps(body), headers={"content-type": ["application/json"]}))


def _slash(app: App, text: str, command: str = "/kudos") -> None:
    body = urlencode(
        {
            "command": command,
            "text": text,
            "user_id": GIVER,
            "team_id": TEAM,
            "channel_id": "C0GENERAL",
            "trigger_id": "1.2.3",
        }
    )
    app.dispatch(BoltRequest(body=body, headers={"content-type": ["application/x-www-form-urlencoded"]}))


def _all_text(posts) -> str:
    return json.dumps(posts)


# The mechanism behind the DM failure, pinned against the installed Bolt.


def test_bolt_runs_only_the_first_matching_listener():
    app = _bolt_app()
    hits = []
    app.event("message")(lambda event: hits.append("catch-all"))
    app.message("kudos")(lambda message: hits.append("kudos"))
    body = {
        "type": "event_callback",
        "team_id": TEAM,
        "event": {"type": "message", "channel_type": "im", "user": GIVER, "text": "kudos", "channel": "D1"},
    }
    app.dispatch(BoltRequest(body=json.dumps(body), headers={"content-type": ["application/json"]}))
    assert hits == ["catch-all"]


# Kudos sent by DM.


def test_a_dm_kudos_with_a_real_mention_is_saved(world):
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    assert [(k["from_user"], k["to_user"], k["message"]) for k in world.saved] == [
        (GIVER, ANMOL, "for reviewing the fix")
    ]


def test_a_dm_kudos_with_a_labelled_mention_is_saved(world):
    _dm(world.app, f"kudos <@{ANMOL}|anmol> for reviewing the fix")
    assert [(k["to_user"], k["message"]) for k in world.saved] == [(ANMOL, "for reviewing the fix")]


def test_a_dm_kudos_keeps_a_multi_line_reason(world):
    _dm(world.app, f"kudos <@{ANMOL}> for the review\nand the tests")
    assert [k["message"] for k in world.saved] == ["for the review\nand the tests"]


def test_a_dm_kudos_is_confirmed_to_the_giver(world):
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    assert world.posts, "the giver heard nothing back"
    assert f"<@{ANMOL}>" in _all_text(world.posts)


def test_a_dm_kudos_wins_over_an_open_standup(world, monkeypatch):
    """A kudos typed mid-standup is a kudos, not the answer to a question."""
    from src.core.state import state_store

    record = MagicMock()
    monkeypatch.setattr(state_store, "get", lambda key: object())
    monkeypatch.setattr(state_store, "record_answer", record)
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    assert [k["to_user"] for k in world.saved] == [ANMOL]
    record.assert_not_called()


def test_a_standup_answer_still_reaches_standup(world, monkeypatch):
    """Standup's answer collection is unchanged, even for text about kudos."""
    import src.modules.standup.handlers as standup
    from src.core.state import state_store

    session = SimpleNamespace(questions=["Yesterday?", "Today?"], step=1)
    record = MagicMock(return_value=session)
    sent = MagicMock()
    monkeypatch.setattr(state_store, "get", lambda key: object())
    monkeypatch.setattr(state_store, "record_answer", record)
    monkeypatch.setattr(standup, "_send_question_block", sent)

    _dm(world.app, "kudos to the team for shipping the fix")

    record.assert_called_once_with(f"{TEAM}:{GIVER}", "kudos to the team for shipping the fix")
    sent.assert_called_once()
    assert world.saved == []


def test_a_dm_kudos_for_yourself_is_refused(world):
    _dm(world.app, f"kudos <@{GIVER}> for being me")
    assert world.saved == []
    assert "other people" in _all_text(world.posts)


def test_a_dm_kudos_is_ignored_when_the_workspace_turned_kudos_off(world):
    world.settings = {"kudos": False}
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    assert world.saved == []


def test_an_edited_message_is_not_a_second_kudos(world):
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix", subtype="message_changed")
    assert world.saved == []


def test_a_dm_kudos_with_a_plain_name_resolves_from_the_roster(world):
    _dm(world.app, "kudos @Anmol Nagpal for reviewing the fix")
    assert [(k["to_user"], k["message"]) for k in world.saved] == [(ANMOL, "for reviewing the fix")]


# The slash command.


@pytest.mark.parametrize("command", ["/kudos", "/morgenruf-kudos"])
def test_the_command_saves_an_escaped_mention(world, command):
    _slash(world.app, f"<@{ANMOL}|anmol> for reviewing the fix", command)
    assert [(k["from_user"], k["to_user"], k["message"]) for k in world.saved] == [
        (GIVER, ANMOL, "for reviewing the fix")
    ]


def test_the_command_saves_a_bare_mention(world):
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert [k["to_user"] for k in world.saved] == [ANMOL]


def test_the_command_resolves_a_plain_real_name(world):
    """What production sent today, before the app config is updated."""
    _slash(world.app, "@Anmol Nagpal for reviewing the fix")
    assert [(k["to_user"], k["message"]) for k in world.saved] == [(ANMOL, "for reviewing the fix")]
    assert "wants to recognise someone" not in _all_text(world.posts)


def test_the_command_resolves_a_plain_display_name(world):
    _slash(world.app, "@anmol for reviewing the fix")
    assert [(k["to_user"], k["message"]) for k in world.saved] == [(ANMOL, "for reviewing the fix")]


@pytest.mark.parametrize(
    "text",
    [
        "@Anmol Nagpal for reviewing the fix",  # the exact production input, with no roster match
        "@sam for the review",  # two people answer to "sam"
        "@Nobody Here thanks",
        "thanks for the review",
        f"<@{ANMOL}>",  # nobody said why
    ],
)
def test_the_command_explains_itself_when_it_cannot_tell_who(world, text):
    if text.startswith("@Anmol"):
        world.members = [m for m in world.members if m["user_id"] != ANMOL]
    _slash(world.app, text)
    assert world.saved == []
    posted = _all_text(world.posts)
    assert "wants to recognise someone" not in posted
    assert len(world.posts) == 1
    assert world.posts[0]["channel"] == GIVER
    assert "/kudos @" in world.posts[0]["text"]


def test_the_command_for_yourself_is_refused(world):
    _slash(world.app, f"<@{GIVER}|giver> for being me")
    assert world.saved == []
    assert "other people" in _all_text(world.posts)


def test_the_command_respects_the_daily_allowance(world):
    world.allowance = {**world.allowance, "remaining": 0, "can_give": False}
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert world.saved == []
    assert "for today" in _all_text(world.posts)


def test_the_command_posts_the_card_to_the_configured_channel(world):
    world.workspace_config = {"channel_id": "C0KUDOS"}
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    channels = [p["channel"] for p in world.posts]
    assert channels == ["C0KUDOS", ANMOL, GIVER]
    assert f"*<@{ANMOL}>* got kudos" in _all_text(world.posts[:1])


def test_a_failed_save_does_not_pretend_it_worked(world):
    world.save_error = RuntimeError("database is down")
    world.workspace_config = {"channel_id": "C0KUDOS"}
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert [p["channel"] for p in world.posts] == [GIVER]
    assert "did not go through" in world.posts[0]["text"]


# The recipient is told, and the card goes where the kudos settings say.
#
# The card used to go only to workspace_config.channel_id, which nothing sets,
# so for current workspaces the giver was the only person who saw anything.


def _to(posts, channel):
    return [p for p in posts if p["channel"] == channel]


def test_a_dm_kudos_is_sent_to_the_recipient(world):
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    dms = _to(world.posts, ANMOL)
    assert len(dms) == 1
    card = _all_text(dms)
    assert f"<@{GIVER}>" in card
    assert "sent you kudos" in card
    assert "for reviewing the fix" in card


def test_the_command_is_sent_to_the_recipient(world):
    _slash(world.app, f"<@{ANMOL}|anmol> for reviewing the fix")
    assert len(_to(world.posts, ANMOL)) == 1


def test_the_recipient_does_not_see_the_givers_remaining_count(world):
    world.allowance = {**world.allowance, "remaining": 3}
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    card = _all_text(_to(world.posts, ANMOL))
    assert "left today" not in card
    assert "midnight" not in card
    assert "left today" in _all_text(_to(world.posts, "D0GIVER"))


def test_the_recipient_card_uses_no_gendered_pronouns(world):
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    words = set(_all_text(_to(world.posts, ANMOL)).lower().replace("*", " ").split())
    assert not words & {"he", "she", "him", "her", "his", "hers"}


def test_no_dm_to_the_recipient_when_the_save_fails(world):
    world.save_error = RuntimeError("database is down")
    _dm(world.app, f"kudos <@{ANMOL}> for reviewing the fix")
    assert _to(world.posts, ANMOL) == []


def test_no_dm_to_the_recipient_when_the_allowance_is_spent(world):
    world.allowance = {**world.allowance, "remaining": 0, "can_give": False}
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert _to(world.posts, ANMOL) == []


def test_no_dm_for_a_self_kudos(world):
    _dm(world.app, f"kudos <@{GIVER}> for being me")
    _slash(world.app, f"<@{GIVER}|giver> for being me")
    assert len(world.posts) == 2
    assert all("other people" in p["text"] for p in world.posts)
    assert "sent you kudos" not in _all_text(world.posts)


def test_the_card_goes_to_the_kudos_channel(world):
    world.kudos_config["channel_id"] = "C0KUDOS"
    world.workspace_config = {"channel_id": "C0LEGACY"}
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert [p["channel"] for p in world.posts] == ["C0KUDOS", ANMOL, GIVER]
    assert world.saved[0]["to_user"] == ANMOL


def test_the_card_falls_back_to_the_legacy_workspace_channel(world):
    world.workspace_config = {"channel_id": "C0LEGACY"}
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert [p["channel"] for p in world.posts] == ["C0LEGACY", ANMOL, GIVER]


def test_no_channel_post_when_neither_channel_is_set(world):
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert [p["channel"] for p in world.posts] == [ANMOL, GIVER]
    assert "got kudos" not in _all_text(world.posts)


def test_the_giver_hears_it_was_sent_to_the_recipient(world):
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    reply = _to(world.posts, GIVER)[0]["text"]
    assert reply == f"Sent to <@{ANMOL}>."


def test_the_giver_hears_it_was_sent_and_posted(world):
    world.kudos_config["channel_id"] = "C0KUDOS"
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    reply = _to(world.posts, GIVER)[0]["text"]
    assert reply == f"Sent to <@{ANMOL}> and posted in <#C0KUDOS>."


def test_a_channel_the_bot_cannot_post_in_still_reaches_the_recipient(world):
    world.kudos_config["channel_id"] = "C0KUDOS"
    world.post_errors["C0KUDOS"] = RuntimeError("not_in_channel")
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert [p["channel"] for p in world.posts] == [ANMOL, GIVER]
    reply = _to(world.posts, GIVER)[0]
    assert reply["text"] == f"Sent to <@{ANMOL}>."
    assert "Invite @Morgenruf" in _all_text([reply])


def test_a_recipient_dm_that_fails_is_not_reported_as_sent(world):
    world.kudos_config["channel_id"] = "C0KUDOS"
    world.post_errors[ANMOL] = RuntimeError("cannot_dm_bot")
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert len(world.saved) == 1
    reply = _to(world.posts, GIVER)[0]["text"]
    assert reply.startswith("Posted in <#C0KUDOS>.")
    assert "Sent to" not in reply


def test_an_unreadable_kudos_channel_does_not_lose_the_kudos(world, monkeypatch):
    import src.modules.kudos.db as kdb

    def broken(team_id):
        raise RuntimeError("database is down")

    monkeypatch.setattr(kdb, "get_config", broken)
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert len(world.saved) == 1
    assert [p["channel"] for p in world.posts] == [ANMOL, GIVER]


def test_the_saved_row_records_the_channel_it_was_posted_in(world, monkeypatch):
    import src.modules.kudos.db as kdb

    channels = []
    monkeypatch.setattr(
        kdb,
        "save_kudos",
        lambda team_id, from_user, to_user, message, channel_id="", emoji=None: channels.append(channel_id),
    )
    world.kudos_config["channel_id"] = "C0KUDOS"
    _slash(world.app, f"<@{ANMOL}> for reviewing the fix")
    assert channels == ["C0KUDOS"]


# The manifests.


def _commands(manifest: dict) -> dict:
    return {c["command"]: c for c in manifest["features"]["slash_commands"]}


@pytest.mark.parametrize("command", ["/kudos", "/morgenruf-kudos"])
def test_both_manifests_ask_slack_to_escape_kudos_mentions(command):
    as_yaml = _commands(yaml.safe_load((ROOT / "slack-manifest.yaml").read_text()))
    as_json = _commands(json.loads((ROOT / "slack-manifest.json").read_text()))
    assert as_yaml[command].get("should_escape") is True
    assert as_json[command].get("should_escape") is True
