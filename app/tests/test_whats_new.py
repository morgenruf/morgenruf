"""The What's new card on App Home: shown until dismissed, gone after a month,
hidden where its feature is off."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock
from urllib.parse import urlencode

import pytest
import src.core.whats_new as wn
from slack_bolt import App, BoltRequest
from slack_bolt.authorization import AuthorizeResult

DAY = date(2026, 11, 12)


@pytest.fixture
def store(monkeypatch):
    seen: set[tuple[str, str, str]] = set()
    active = {"kudos": True}
    monkeypatch.setattr(wn, "_dismissed", lambda t, u, i: (t, u, i) in seen)
    monkeypatch.setattr(wn, "dismiss", lambda t, u, i: seen.add((t, u, i)))
    import src.core.modules as modules

    monkeypatch.setattr(modules, "is_active_for", lambda t, name: active.get(name, False))
    return seen, active


def test_ids_are_unique_and_newest_first():
    assert len({i.id for i in wn.ITEMS}) == len(wn.ITEMS)
    assert list(wn.ITEMS) == sorted(wn.ITEMS, key=lambda i: i.published, reverse=True)


def test_an_item_shows_for_a_month_then_drops():
    item = wn.Item(id="x", published=DAY, text="x")
    assert wn.current(DAY, (item,)) == [item]
    assert wn.current(date(2026, 12, 11), (item,)) == [item]
    assert wn.current(date(2026, 12, 12), (item,)) == []
    assert wn.current(date(2026, 11, 11), (item,)) == []


def test_got_it_moves_to_the_next_item_then_empties(store, monkeypatch):
    first = wn.Item(id="a", published=DAY, text="first")
    second = wn.Item(id="b", published=DAY, text="second", button_text="Try", button_action="kudos:give")
    monkeypatch.setattr(wn, "ITEMS", (first, second))
    assert "first" in json.dumps(wn.home_blocks("T1", "U1", today=DAY))
    store[0].add(("T1", "U1", "a"))
    blocks = json.dumps(wn.home_blocks("T1", "U1", today=DAY))
    assert "second" in blocks and "kudos:give" in blocks and wn.DISMISS_ACTION in blocks
    store[0].add(("T1", "U1", "b"))
    assert wn.home_blocks("T1", "U1", today=DAY) == []
    assert "first" in json.dumps(wn.home_blocks("T1", "U2", today=DAY))


def test_no_card_where_the_feature_is_off(store):
    store[1]["kudos"] = False
    assert wn.home_blocks("T1", "U1", today=DAY) == []


def test_a_failed_lookup_hides_the_card(monkeypatch, store):
    monkeypatch.setattr(wn, "_dismissed", MagicMock(side_effect=RuntimeError("db down")))
    assert wn.home_blocks("T1", "U1", today=DAY) == []


def test_got_it_saves_and_refreshes(store, monkeypatch):
    import src.core.home as home

    refreshed = []
    monkeypatch.setattr(home, "refresh_home", lambda t, u, c: refreshed.append(u))
    app = App(
        signing_secret="x",
        authorize=lambda **kw: AuthorizeResult(enterprise_id=None, team_id="T1", bot_token="xoxb-1", bot_user_id="UB"),
        request_verification_enabled=False,
        process_before_response=True,
    )
    wn.register_slack(app)
    body = {
        "type": "block_actions",
        "team": {"id": "T1"},
        "user": {"id": "U1"},
        "actions": [{"action_id": wn.DISMISS_ACTION, "type": "button", "value": "some-item"}],
    }
    app.dispatch(
        BoltRequest(
            body=urlencode({"payload": json.dumps(body)}),
            headers={"content-type": ["application/x-www-form-urlencoded"]},
        )
    )
    assert ("T1", "U1", "some-item") in store[0]
    assert refreshed == ["U1"]


def _reaction_item():
    return next(i for i in wn.ITEMS if i.scope == "reactions:read")


def test_a_scoped_item_offers_admins_a_reinstall(store, monkeypatch):
    import src.core.db as db

    monkeypatch.setattr(db, "granted_scopes", lambda t: ["chat:write"])
    monkeypatch.setattr(db, "can_administer", lambda t, u: True)
    monkeypatch.setattr(wn, "ITEMS", (_reaction_item(),))
    text = json.dumps(wn.home_blocks("T1", "U1", today=DAY))
    assert wn.REINSTALL_ACTION in text and "/install" in text


def test_a_scoped_item_tells_members_to_ask_an_admin(store, monkeypatch):
    import src.core.db as db

    monkeypatch.setattr(db, "granted_scopes", lambda t: ["chat:write"])
    monkeypatch.setattr(db, "can_administer", lambda t, u: False)
    monkeypatch.setattr(wn, "ITEMS", (_reaction_item(),))
    text = json.dumps(wn.home_blocks("T1", "U1", today=DAY))
    assert wn.REINSTALL_ACTION not in text and "Ask a workspace admin" in text


def test_a_scoped_item_needs_no_reinstall_once_granted(store, monkeypatch):
    import src.core.db as db

    monkeypatch.setattr(db, "granted_scopes", lambda t: ["reactions:read"])
    monkeypatch.setattr(wn, "ITEMS", (_reaction_item(),))
    text = json.dumps(wn.home_blocks("T1", "U1", today=DAY))
    assert wn.REINSTALL_ACTION not in text and "reinstall" not in text.lower()
