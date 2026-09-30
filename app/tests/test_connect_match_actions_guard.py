"""Buttons on a Connect match act on the match id they carry, so the handler
has to check that the person tapping is in that match, and that the time they
accept can still happen."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.modules.connect import handlers

from tests.support import patch_modules


def _db(members=("U1", "U2"), team="T1"):
    db = MagicMock()
    db.match_by_id.return_value = {
        "id": 77,
        "team_id": team,
        "round_id": 5,
        "member_ids": list(members),
        "agreed_slot_utc": None,
    }
    db.slot_votes.return_value = {}
    db.agree_slot.return_value = True
    db.program_for_round.return_value = {"meeting_link": ""}
    return db


def _met(db, user="U1", team="T1"):
    body = {"user": {"id": user}, "team": {"id": team}, "channel": {"id": "D1"}, "actions": [{"value": "77"}]}
    client = MagicMock()
    with patch_modules({"src.modules.connect.db": db}):
        handlers._record_met(body, client, True, "ok")
    return client


def test_a_member_of_the_match_records_it():
    db = _db()
    _met(db)
    db.set_met.assert_called_once_with(77, True, "T1")


def test_someone_outside_the_match_changes_nothing():
    db = _db()
    client = _met(db, user="U_OTHER")
    db.set_met.assert_not_called()
    client.chat_postMessage.assert_not_called()


def test_a_match_from_another_workspace_changes_nothing():
    db = _db(team="T_OTHER")
    _met(db)
    db.set_met.assert_not_called()


def test_set_met_is_scoped_by_workspace(monkeypatch):
    from contextlib import contextmanager

    import src.modules.connect.db as cdb

    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def db_conn():
        yield conn

    monkeypatch.setattr(cdb, "db_conn", db_conn)
    cdb.set_met(77, True, "T1")
    sql, params = cur.execute.call_args.args
    assert "team_id = %s" in sql and params == (True, 77, "T1")


def _tap(db, slot, user="U1"):
    body = {
        "user": {"id": user},
        "channel": {"id": "D1"},
        "actions": [{"action_id": f"connect:accept_slot:77:{slot.isoformat()}", "value": slot.isoformat()}],
    }
    client = MagicMock()
    with patch_modules({"src.modules.connect.db": db}):
        handlers._accept_slot(body, client)
    return client


def test_a_slot_in_the_past_is_refused_and_books_nothing():
    """An old intro's button must not settle a meeting that already passed."""
    past = datetime.now(timezone.utc) - timedelta(days=2)
    db = _db()
    db.slot_votes.return_value = {past: ["U1", "U2"]}
    client = _tap(db, past, "U2")
    db.accept_slot.assert_not_called()
    db.agree_slot.assert_not_called()
    assert client.chat_postEphemeral.called


def test_a_slot_too_far_ahead_is_refused():
    far = datetime.now(timezone.utc) + timedelta(days=handlers.SUGGEST_MAX_DAYS + 1)
    db = _db()
    _tap(db, far)
    db.accept_slot.assert_not_called()


def test_a_slot_in_the_next_days_is_accepted():
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    db = _db()
    _tap(db, soon)
    db.accept_slot.assert_called_once()
