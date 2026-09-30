"""Standup's DM keywords reach their handlers, through the app's real listeners.

`help`, `standup`, `skip`, the vacation phrases and `timezone <tz>` were
@app.message listeners registered after core's catch-all DM listener. Bolt
runs only the first listener that matches, so none of them ever ran in
production, while the welcome DM said "Type `help`" and App Home advertised
`standup`, `skip` and `I'm away`.

These tests register listeners the way create_app does
(register_slack_listeners, with the real REGISTRY) and send the message events
Slack sends. DB calls and chat.postMessage are stubbed; standup sessions use
the real state store on its in-memory backend.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from flask import Flask
from slack_bolt import App, BoltRequest
from slack_bolt.authorization import AuthorizeResult
from slack_sdk.web import WebClient

USER = "U0PERSON"
ANMOL = "U0ANMOL"
TEAM = "T1"
KEY = f"{TEAM}:{USER}"
QUESTIONS = ["What did you do yesterday?", "What will you do today?", "Anything blocking you?"]


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
    import src.core.analytics as analytics
    import src.core.db as core_db
    import src.core.session_store as session_store
    import src.modules.kudos.db as kdb

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(session_store, "_redis", None)
    monkeypatch.setattr(session_store, "_memory", {})

    state = SimpleNamespace(posts=[], skips=[], vacation=[], tz=[], saved_standups=[], kudos=[], settings={})

    def save_standup(**kwargs):
        state.saved_standups.append(kwargs)
        return 1

    def save_kudos(team_id, from_user, to_user, message, channel_id="", emoji=None):
        state.kudos.append((from_user, to_user, message))
        return {}

    monkeypatch.setattr(core_db, "granted_scopes", lambda team_id: set())
    monkeypatch.setattr(core_db, "module_settings", lambda team_id: dict(state.settings))
    monkeypatch.setattr(core_db, "skip_today", lambda team_id, user_id, for_date=None: state.skips.append(user_id))
    monkeypatch.setattr(core_db, "set_vacation", lambda team_id, user_id, on: state.vacation.append(on))
    monkeypatch.setattr(core_db, "upsert_member", lambda team_id, user_id, **kw: state.tz.append(kw.get("tz")))
    monkeypatch.setattr(
        core_db,
        "get_schedule_for_user",
        lambda team_id, user_id: {"id": 7, "channel_id": "C0STANDUP", "questions": QUESTIONS, "name": "Daily"},
    )
    monkeypatch.setattr(core_db, "get_workspace_config", lambda team_id: {"channel_id": ""})
    monkeypatch.setattr(core_db, "save_standup", save_standup)
    monkeypatch.setattr(core_db, "get_all_members", lambda team_id: [])
    monkeypatch.setattr(kdb, "save_kudos", save_kudos)
    monkeypatch.setattr(
        kdb,
        "allowance_state",
        lambda *a, **k: {"emoji": "x", "allowance": 5, "used": 0, "remaining": 5, "can_give": True},
    )
    monkeypatch.setattr(kdb, "get_config", lambda team_id: {"emoji": "x", "daily_allowance": 5})
    monkeypatch.setattr(analytics, "capture", lambda *a, **k: True)

    def chat_postMessage(self, **kwargs):  # noqa: N802
        state.posts.append(kwargs)
        return {"ok": True, "ts": "1.1", "channel": kwargs.get("channel")}

    monkeypatch.setattr(WebClient, "chat_postMessage", chat_postMessage)
    monkeypatch.setattr(WebClient, "views_publish", lambda self, **kw: {"ok": True})

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
        "channel": "D0PERSON",
        "user": USER,
        "team": TEAM,
        "text": text,
        "ts": "1700000000.000100",
        **extra,
    }
    body = {"type": "event_callback", "team_id": TEAM, "event": event}
    app.dispatch(BoltRequest(body=json.dumps(body), headers={"content-type": ["application/json"]}))


def _texts(world) -> list[str]:
    return [p.get("text", "") for p in world.posts]


def _session():
    from src.core.state import state_store

    return state_store.get(KEY)


def _open_session(step: int = 0):
    from src.core.state import state_store

    state_store.start(KEY, "C0STANDUP", team_id=TEAM, questions=QUESTIONS, standup_name="Daily", schedule_id=7)
    for i in range(step):
        state_store.record_answer(KEY, f"answer {i}")
    return state_store.get(KEY)


# Each keyword reaches its handler.


@pytest.mark.parametrize("text", ["help", "Help", "  HELP  ", "help!", "help?", "help."])
def test_help_is_answered(world, text):
    _dm(world.app, text)
    assert len(world.posts) == 1
    assert "`standup`" in world.posts[0]["text"]
    assert world.posts[0]["channel"] == "D0PERSON"


def test_help_lists_every_keyword_it_advertises_and_each_one_works(world):
    """Each backticked DM command in standup's help is a working keyword."""
    import re

    from src.modules.standup import MODULE
    from src.modules.standup.handlers import match_dm_command

    words = set(re.findall(r"`([^`]+)`", " ".join(MODULE.help_lines)))
    for word in words - {"pass", "/standup", "/skip", "timezone America/New_York"}:
        assert match_dm_command(word) is not None, word
    assert match_dm_command("timezone America/New_York") == ("timezone", "America/New_York")


@pytest.mark.parametrize("text", ["standup", "Standup!", " STANDUP "])
def test_standup_starts_a_standup(world, text):
    _dm(world.app, text)
    session = _session()
    assert session is not None and session.questions == QUESTIONS and session.step == 0
    assert any("Time for your standup" in t for t in _texts(world))


@pytest.mark.parametrize("text", ["skip", "Skip.", "SKIP!"])
def test_skip_skips_today(world, text):
    _dm(world.app, text)
    assert world.skips == [USER]
    assert "skipped today's standup" in _texts(world)[0]


@pytest.mark.parametrize(
    "text",
    [
        "I'm away",
        "i’m away",
        "im away",
        "I'm on vacation",
        "on vacation",
        "Going on vacation!",
        "I'm going on vacation.",
    ],
)
def test_vacation_phrases_mark_the_person_away(world, text):
    _dm(world.app, text)
    assert world.vacation == [True]
    assert "Enjoy your vacation" in _texts(world)[0]


@pytest.mark.parametrize("text", ["I'm back", "im back!", "back from vacation", "I'm back from vacation."])
def test_back_phrases_end_vacation(world, text):
    _dm(world.app, text)
    assert world.vacation == [False]
    assert "Welcome back" in _texts(world)[0]


@pytest.mark.parametrize(
    ("text", "saved"),
    [
        ("timezone Europe/London", "Europe/London"),
        ("Timezone America/New_York.", "America/New_York"),
        ("timezone europe/london", "Europe/London"),
    ],
)
def test_timezone_is_saved(world, text, saved):
    _dm(world.app, text)
    assert world.tz == [saved]
    assert saved in _texts(world)[0]


def test_an_unknown_timezone_is_refused(world):
    _dm(world.app, "timezone Mars/Olympus")
    assert world.tz == []
    assert "Unknown timezone" in _texts(world)[0]


# Only a whole message is a keyword.


@pytest.mark.parametrize(
    "text",
    [
        "I need help with the deploy",
        "can you help",
        "please skip me",
        "skip today please",
        "our standup was late",
        "I'm away tomorrow afternoon",
        "set my timezone Europe/London",
        "timezone",
        "timezone Europe/London please",
    ],
)
def test_a_message_containing_a_keyword_is_not_a_command(world, text):
    _dm(world.app, text)
    assert world.posts == []
    assert world.skips == [] and world.vacation == [] and world.tz == []
    assert _session() is None


def test_edits_and_bot_messages_are_not_commands(world):
    _dm(world.app, "help", subtype="message_changed")
    _dm(world.app, "skip", bot_id="B9")
    assert world.posts == [] and world.skips == []


def test_keywords_are_ignored_when_the_workspace_turned_standup_off(world):
    world.settings = {"standup": False}
    _dm(world.app, "help")
    _dm(world.app, "skip")
    assert world.posts == [] and world.skips == []


# Answers that contain keywords are answers.


@pytest.mark.parametrize(
    "text",
    [
        "Helped Sam with the release",
        "need help with the deploy",
        "skip the retro, finish the migration",
        "standup notes and the migration",
        "on vacation from Friday, handing over today",
        "timezone bug in the scheduler",
    ],
)
def test_an_answer_containing_a_keyword_is_stored_as_an_answer(world, text):
    _open_session()
    _dm(world.app, text)
    session = _session()
    assert session.answers == [text]
    assert session.step == 1
    assert world.skips == [] and world.vacation == [] and world.tz == []


def test_a_full_standup_with_keyword_words_is_saved_as_typed(world):
    _open_session()
    for text in ["helped with the standup bot", "skip nothing, ship it", "need help from ops"]:
        _dm(world.app, text)
    _dm(world.app, "great")
    assert len(world.saved_standups) == 1
    row = world.saved_standups[0]
    assert (row["yesterday"], row["today"], row["blockers"]) == (
        "helped with the standup bot",
        "skip nothing, ship it",
        "need help from ops",
    )


# Mid-session rule.


def test_mid_session_skip_is_an_answer(world):
    _open_session()
    _dm(world.app, "skip")
    session = _session()
    assert session.answers == ["skip"] and session.step == 1
    assert world.skips == []


@pytest.mark.parametrize("text", ["pass", "Pass", "pass."])
def test_mid_session_pass_leaves_the_question_blank(world, text):
    _open_session(step=1)
    _dm(world.app, text)
    session = _session()
    assert session.answers == ["answer 0", ""] and session.step == 2
    assert world.posts[-1]["text"] == QUESTIONS[2]


def test_pass_outside_a_session_does_nothing(world):
    _dm(world.app, "pass")
    assert world.posts == [] and _session() is None


def test_mid_session_help_shows_help_and_keeps_the_question_open(world):
    _open_session(step=1)
    _dm(world.app, "help")
    session = _session()
    assert session.answers == ["answer 0"] and session.step == 1
    assert len(world.posts) == 1
    assert "`standup`" in world.posts[0]["text"]
    assert "still open" in world.posts[0]["text"]
    # The next message is still the answer to question 2.
    _dm(world.app, "finish the migration")
    assert _session().answers == ["answer 0", "finish the migration"]


def test_mid_session_standup_says_one_is_in_progress(world):
    _open_session(step=2)
    _dm(world.app, "standup")
    session = _session()
    assert session.answers == ["answer 0", "answer 1"] and session.step == 2
    assert len(world.posts) == 1
    assert "already have a standup in progress" in world.posts[0]["text"]


def test_mid_session_timezone_is_saved_and_the_question_stays_open(world):
    _open_session(step=1)
    _dm(world.app, "timezone Europe/Berlin")
    assert world.tz == ["Europe/Berlin"]
    assert _session().answers == ["answer 0"]
    assert "still open" in world.posts[0]["text"]


def test_mid_session_back_keeps_the_question_open(world):
    _open_session(step=1)
    _dm(world.app, "I'm back")
    assert world.vacation == [False]
    assert _session().answers == ["answer 0"]


def test_mid_session_away_closes_the_standup_like_the_button(world):
    _open_session(step=1)
    _dm(world.app, "I'm away")
    assert world.vacation == [True]
    assert _session() is None
    assert world.saved_standups == []


def test_mid_session_at_the_mood_step_help_does_not_become_the_mood(world):
    _open_session(step=3)
    _dm(world.app, "help")
    assert _session().answers == ["answer 0", "answer 1", "answer 2"]
    assert world.saved_standups == []


# Kudos from #194 still route to kudos.


def test_a_dm_kudos_still_reaches_kudos(world):
    _dm(world.app, f"kudos <@{ANMOL}> for the help with the standup")
    assert world.kudos == [(USER, ANMOL, "for the help with the standup")]


def test_a_dm_kudos_mid_standup_still_reaches_kudos(world):
    _open_session(step=1)
    _dm(world.app, f"kudos <@{ANMOL}> for the skip logic")
    assert world.kudos == [(USER, ANMOL, "for the skip logic")]
    assert _session().answers == ["answer 0"]


# The dead listeners are gone.


def test_standup_registers_no_message_listener():
    """Core's catch-all would shadow it, as it shadowed the old keyword listeners."""
    from unittest.mock import MagicMock

    from src.modules.standup import MODULE

    bolt_app = MagicMock()
    MODULE.register_slack(bolt_app)
    assert not bolt_app.message.called
    assert MODULE.claim_dm_command is not None
