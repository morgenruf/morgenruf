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
    assert wn.current(DAY, (item,)) is item
    assert wn.current(date(2026, 12, 11), (item,)) is item
    assert wn.current(date(2026, 12, 12), (item,)) is None
    assert wn.current(date(2026, 11, 11), (item,)) is None


def test_the_card_shows_until_got_it(store):
    blocks = wn.home_blocks("T1", "U1", today=DAY)
    assert "kudos:give" in json.dumps(blocks) and wn.DISMISS_ACTION in json.dumps(blocks)
    store[0].add(("T1", "U1", wn.ITEMS[0].id))
    assert wn.home_blocks("T1", "U1", today=DAY) == []
    assert wn.home_blocks("T1", "U2", today=DAY) != []


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
