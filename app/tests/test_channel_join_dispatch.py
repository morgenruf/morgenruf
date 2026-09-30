"""One member_joined_channel listener, offered to every module.

Bolt runs only the first listener matching an event. Standup and Connect each
registered one, so Connect's welcome never ran, and Celebrations' channel join
prompt would not have either. Core now owns the listener.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

from slack_bolt import App, BoltRequest
from slack_bolt.authorization import AuthorizeResult
from src.core.modules import ModuleSpec

# src.main is imported inside each test, not here: importing it at collection
# time loads core's dashboard before test_dashboard installs its stubs.
SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def spec(name, hook=None):
    return ModuleSpec(
        name=name,
        required_scopes=(),
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=(),
        default_enabled=True,
        on_channel_join=hook,
    )


def test_bolt_runs_only_the_first_matching_listener():
    """The reason this dispatcher exists, pinned against the installed Bolt."""
    app = App(
        signing_secret="x",
        authorize=lambda **kw: AuthorizeResult(
            enterprise_id=None, team_id="T1", bot_token="xoxb-1", bot_user_id="UB", bot_id="B1"
        ),
        request_verification_enabled=False,
        process_before_response=True,
    )
    hits = []
    app.event("member_joined_channel")(lambda event: hits.append("first"))
    app.event("member_joined_channel")(lambda event: hits.append("second"))
    body = {"type": "event_callback", "team_id": "T1", "event": {"type": "member_joined_channel", "user": "U1"}}
    app.dispatch(BoltRequest(body=json.dumps(body), headers={"content-type": ["application/json"]}))
    assert hits == ["first"]


def test_every_hook_is_called_in_order():
    from src.main import dispatch_channel_join

    calls = []
    modules = [
        spec("a", lambda e, c: calls.append("a")),
        spec("none"),
        spec("b", lambda e, c: calls.append("b")),
    ]
    assert dispatch_channel_join(modules, {"user": "U1"}, MagicMock()) == ["a", "b"]
    assert calls == ["a", "b"]


def test_a_failing_hook_does_not_stop_the_next():
    from src.main import dispatch_channel_join

    def boom(event, client):
        raise RuntimeError("module bug")

    calls = []
    modules = [spec("broken", boom), spec("ok", lambda e, c: calls.append("ok"))]
    assert dispatch_channel_join(modules, {}, MagicMock()) == ["ok"]
    assert calls == ["ok"]


def test_core_registers_exactly_one_listener():
    from src.main import register_channel_join_listener

    bolt = MagicMock()
    register_channel_join_listener(bolt)
    bolt.event.assert_called_once_with("member_joined_channel")


def test_no_module_registers_its_own():
    offenders = [
        str(p.relative_to(SRC))
        for p in (SRC / "modules").rglob("*.py")
        if '@app.event("member_joined_channel")' in p.read_text()
    ]
    assert not offenders, f"modules registering their own member_joined_channel listener: {offenders}"


def test_standup_connect_and_celebrations_all_have_a_hook():
    from src.modules import REGISTRY

    hooked = [s.name for s in REGISTRY if s.on_channel_join is not None]
    assert hooked == ["standup", "connect", "celebrations"]


STANDUP_CHANNEL = "C_STANDUP"
CELEBRATIONS_CHANNEL = "C_CELEBRATE"
COFFEE_CHANNEL = "C_COFFEE"
UNRELATED_CHANNEL = "C_RANDOM"


def _standup_join(monkeypatch, channel):
    """Run standup's hook for a join to `channel` in a workspace whose only
    active standup is in STANDUP_CHANNEL. Celebrations and coffee chats have
    their own channels, which are not standup channels."""
    import src.core.db as db
    from src.modules.standup.handlers import on_channel_join

    registered = []
    lookups = []
    monkeypatch.setattr(db, "upsert_member", lambda **kw: registered.append(kw["user_id"]))

    def schedule_for_channel(team_id, channel_id):
        lookups.append((team_id, channel_id))
        if team_id == "T1" and channel_id == STANDUP_CHANNEL:
            return {"id": 1, "team_id": "T1", "channel_id": STANDUP_CHANNEL, "active": True}
        return None

    monkeypatch.setattr(db, "get_standup_schedule_for_channel", schedule_for_channel)
    client = MagicMock()
    client.users_info.return_value = {"user": {"id": "U1", "tz": "UTC", "profile": {"real_name": "Priya"}}}
    on_channel_join({"user": "U1", "team": "T1", "channel": channel}, client)
    return client, registered, lookups


def test_standup_welcomes_a_join_to_a_standup_channel(monkeypatch):
    client, registered, lookups = _standup_join(monkeypatch, STANDUP_CHANNEL)
    assert registered == ["U1"]
    assert lookups == [("T1", STANDUP_CHANNEL)]
    client.chat_postMessage.assert_called_once()
    assert client.chat_postMessage.call_args.kwargs["channel"] == "U1"
    assert client.chat_postMessage.call_args.kwargs["text"] == (
        f"👋 Welcome! I'm Morgenruf. <#{STANDUP_CHANNEL}> has a standup: when it runs, "
        "I'll DM you a few quick questions and share your answers with the team.\n\n"
        "Use `/standup` to try one now, or `/morgenruf help` to see everything I do."
    )


def test_standup_does_not_welcome_a_join_to_the_celebrations_channel(monkeypatch):
    client, registered, _ = _standup_join(monkeypatch, CELEBRATIONS_CHANNEL)
    assert registered == ["U1"]
    client.chat_postMessage.assert_not_called()


def test_standup_does_not_welcome_a_join_to_a_coffee_chat_channel(monkeypatch):
    client, registered, _ = _standup_join(monkeypatch, COFFEE_CHANNEL)
    assert registered == ["U1"]
    client.chat_postMessage.assert_not_called()


def test_standup_does_not_welcome_a_join_to_an_unrelated_channel(monkeypatch):
    client, registered, _ = _standup_join(monkeypatch, UNRELATED_CHANNEL)
    assert registered == ["U1"]
    client.chat_postMessage.assert_not_called()


def test_standup_does_not_welcome_a_join_without_a_channel(monkeypatch):
    client, _, lookups = _standup_join(monkeypatch, "")
    assert lookups == []
    client.chat_postMessage.assert_not_called()


def test_the_standup_channel_lookup_counts_only_active_schedules_in_that_workspace(monkeypatch):
    """A paused standup, or one in another workspace, does not make a channel
    a standup channel."""
    from contextlib import contextmanager

    import src.core.db as db

    calls = []
    cur = MagicMock()
    cur.__enter__.return_value = cur
    cur.execute.side_effect = lambda sql, params=(): calls.append((" ".join(sql.split()), tuple(params)))
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(db, "db_conn", fake_conn)
    assert db.get_standup_schedule_for_channel("T1", STANDUP_CHANNEL) is None
    sql, params = calls[0]
    assert "FROM standup_schedules WHERE team_id = %s AND channel_id = %s AND active = TRUE" in sql
    assert params == ("T1", STANDUP_CHANNEL)


def test_connect_stays_quiet_where_it_is_switched_off(monkeypatch):
    import src.core.modules as modules
    from src.modules.connect.handlers import on_channel_join

    monkeypatch.setattr(modules, "is_active_for", lambda team, name: False)
    client = MagicMock()
    on_channel_join({"user": "U1", "team": "T1", "channel": "C1"}, client)
    client.chat_postMessage.assert_not_called()
