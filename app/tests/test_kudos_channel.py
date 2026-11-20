"""Kudos typed in a channel, Donut style: `@sam :heart_eyes: great lesson`.

Asked for by a school (2026-11-20) whose kudos emoji is a unicode emoji
the reaction path could not recognise. These go through the real core
message listener, the way Slack delivers message.channels events.
"""

from __future__ import annotations

import json

import pytest
from slack_bolt import BoltRequest
from slack_sdk.web import WebClient
from src.modules.kudos.handlers import channel_kudos, reaction_triggers

from tests.test_kudos_delivery import ANMOL, GIVER, TEAM, world  # noqa: F401

SAM = "U0SAM1"


@pytest.fixture
def slack(world, monkeypatch):  # noqa: F811
    world.kudos_config["emoji"] = "\N{SMILING FACE WITH HEART-SHAPED EYES}"
    world.reactions = []

    def users_info(self, user):
        return {"ok": True, "user": {"id": user, "is_bot": user == "UOTHERBOT"}}

    def reactions_add(self, **kwargs):
        world.reactions.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(WebClient, "users_info", users_info)
    monkeypatch.setattr(WebClient, "reactions_add", reactions_add)
    monkeypatch.setattr(
        WebClient, "chat_getPermalink", lambda self, **k: {"ok": True, "permalink": "https://x.slack.com/p1"}
    )
    return world


def _say(app, text: str, channel_type: str = "channel", **extra) -> None:
    event = {
        "type": "message",
        "channel_type": channel_type,
        "channel": "C0CLASS",
        "user": GIVER,
        "team": TEAM,
        "text": text,
        "ts": "1700000000.000200",
        **extra,
    }
    body = {"type": "event_callback", "team_id": TEAM, "event": event}
    app.dispatch(BoltRequest(body=json.dumps(body), headers={"content-type": ["application/json"]}))


def test_unicode_tokens_have_their_slack_names():
    assert "heart_eyes" in reaction_triggers("\N{SMILING FACE WITH HEART-SHAPED EYES}")
    assert "maple_leaf" in reaction_triggers("\N{MAPLE LEAF}")
    assert "heart" in reaction_triggers("\N{HEAVY BLACK HEART}️")
    assert "tada" in reaction_triggers(":tada:")
    assert "morgenruf" in reaction_triggers("")


def test_parse_takes_out_mentions_and_the_emoji():
    found = channel_kudos(f"<@{ANMOL}> :heart_eyes: great lesson today", {"heart_eyes"})
    assert found == ([ANMOL], "great lesson today")
    assert channel_kudos(f"<@{ANMOL}> great lesson today", {"heart_eyes"}) is None
    assert channel_kudos(":heart_eyes: lovely day", {"heart_eyes"}) is None
    assert channel_kudos(f"<@{ANMOL}> \N{SMILING FACE WITH HEART-SHAPED EYES} thanks", {"heart_eyes"}) == (
        [ANMOL],
        "thanks",
    )


def test_a_channel_kudos_is_saved_and_checked_off(slack):
    _say(slack.app, f"<@{ANMOL}> :heart_eyes: great lesson today")
    assert [(k["from_user"], k["to_user"], k["message"]) for k in slack.saved] == [(GIVER, ANMOL, "great lesson today")]
    assert [r["name"] for r in slack.reactions] == ["white_check_mark"]
    # The recipient hears about it; the giver gets no "sent" DM, the check mark is enough.
    assert [p["channel"] for p in slack.posts] == [ANMOL]


def test_every_person_mentioned_gets_one(slack):
    _say(slack.app, f":heart_eyes::skin-tone-2: <@{ANMOL}> and <@{SAM}> for the assembly <@{ANMOL}>")
    assert sorted(k["to_user"] for k in slack.saved) == sorted([ANMOL, SAM])
    assert {k["message"] for k in slack.saved} == {"and for the assembly"}


def test_private_channels_count_too(slack):
    _say(slack.app, f"<@{ANMOL}> :heart_eyes: thanks", channel_type="group")
    assert [k["to_user"] for k in slack.saved] == [ANMOL]


def test_no_reason_links_the_message(slack):
    _say(slack.app, f"<@{ANMOL}> :heart_eyes:")
    assert [k["message"] for k in slack.saved] == ["for this message: https://x.slack.com/p1"]


@pytest.mark.parametrize(
    "text,extra",
    [
        (f"<@{ANMOL}> great lesson", {}),  # no kudos emoji
        (f"<@{ANMOL}> :tada: great lesson", {}),  # someone else's emoji
        (f"<@{ANMOL}> :heart_eyes: great lesson", {"subtype": "message_changed"}),  # an edit
        (f"<@{ANMOL}> :heart_eyes: great lesson", {"bot_id": "B9"}),  # a bot
        (f"<@{GIVER}> :heart_eyes: me", {}),  # yourself
        (":heart_eyes: <@UOTHERBOT> thanks", {}),  # a bot account
    ],
)
def test_ordinary_messages_are_left_alone(slack, text, extra):
    _say(slack.app, text, **extra)
    assert slack.saved == []
    assert slack.posts == []
    assert slack.reactions == []


def test_kudos_switched_off_stays_silent(slack):
    slack.settings["kudos"] = False
    _say(slack.app, f"<@{ANMOL}> :heart_eyes: great lesson")
    assert slack.saved == [] and slack.reactions == []


def test_out_of_kudos_is_told_by_dm_and_not_checked(slack):
    slack.allowance.update(can_give=False, remaining=0)
    _say(slack.app, f"<@{ANMOL}> :heart_eyes: great lesson")
    assert slack.saved == [] and slack.reactions == []
    assert [p["channel"] for p in slack.posts] == [GIVER]


def test_the_card_is_not_repeated_in_the_kudos_channel(slack):
    slack.kudos_config["channel_id"] = "C0CLASS"
    _say(slack.app, f"<@{ANMOL}> :heart_eyes: great lesson")
    assert "C0CLASS" not in [p["channel"] for p in slack.posts]


def test_the_card_still_goes_to_another_kudos_channel(slack):
    slack.kudos_config["channel_id"] = "C0KUDOS"
    _say(slack.app, f"<@{ANMOL}> :heart_eyes: great lesson")
    assert "C0KUDOS" in [p["channel"] for p in slack.posts]


def test_a_unicode_token_reaction_now_counts(slack, monkeypatch):
    from src.modules.kudos import handlers

    monkeypatch.setattr("src.core.modules.is_active_for", lambda team_id, name: True)
    import src.modules.kudos.db as kdb

    monkeypatch.setattr(kdb, "already_given", lambda *a: False)
    event = {
        "reaction": "heart_eyes",
        "user": GIVER,
        "item_user": ANMOL,
        "item": {"type": "message", "channel": "C0CLASS", "ts": "1.2"},
    }
    assert handlers.handle_reaction(WebClient(token="x"), TEAM, "UBOT", event) is True
