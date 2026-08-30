"""Participants selected in the dashboard must actually receive the standup.

Delivery started from `get_active_members` and intersected with the schedule's
participant list, so anyone picked in the dashboard who had never interacted
with the bot was dropped without a word: listed on the standup, counted in its
total, never DMed. On the live workspace one schedule listed 15 participants and
could reach exactly 1 of them.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

for _name in ("pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

_had = "scheduler" in sys.modules
import scheduler as sched_mod  # noqa: E402

if _had:
    sched_mod = importlib.reload(sched_mod)

import slack_users  # noqa: E402


def _slack_user(uid, name=None, **over):
    u = {"id": uid, "deleted": False, "is_bot": False, "tz": "Europe/London", "profile": {"real_name": name or uid}}
    u.update(over)
    return u


def _client(users):
    c = MagicMock()
    c.users_list.return_value = {"members": users, "response_metadata": {}}
    return c


class TestResolveParticipants:
    def test_known_members_are_returned_unchanged(self):
        db = MagicMock()
        members = [{"user_id": "U1", "real_name": "Ada"}]
        with patch.dict(sys.modules, {"db": db}):
            out = sched_mod.resolve_participants(_client([]), "T1", ["U1"], members)
        assert [m["user_id"] for m in out] == ["U1"]
        db.upsert_member.assert_not_called()

    def test_unknown_participant_is_registered_and_included(self):
        """The bug: U2 was silently dropped instead of being registered."""
        db = MagicMock()
        db.get_all_members.return_value = []
        client = _client([_slack_user("U2", "Grace")])
        with patch.dict(sys.modules, {"db": db}):
            out = sched_mod.resolve_participants(client, "T1", ["U1", "U2"], [{"user_id": "U1", "real_name": "Ada"}])
        assert set(m["user_id"] for m in out) == {"U1", "U2"}
        db.upsert_member.assert_called_once()
        assert db.upsert_member.call_args.args[1] == "U2"
        assert db.upsert_member.call_args.kwargs["real_name"] == "Grace"

    def test_a_bot_in_the_participant_list_is_not_registered(self):
        db = MagicMock()
        db.get_all_members.return_value = []
        client = _client([_slack_user("BOT1", "Helper", is_bot=True)])
        with patch.dict(sys.modules, {"db": db}):
            out = sched_mod.resolve_participants(client, "T1", ["BOT1"], [])
        assert out == []
        db.upsert_member.assert_not_called()

    def test_opted_out_member_is_not_resurrected(self):
        """A stored but inactive member chose to leave; do not re-add them."""
        db = MagicMock()
        db.get_all_members.return_value = [{"user_id": "U9"}]
        client = _client([_slack_user("U9", "Quit")])
        with patch.dict(sys.modules, {"db": db}):
            out = sched_mod.resolve_participants(client, "T1", ["U9"], [])
        assert out == []
        db.upsert_member.assert_not_called()

    def test_slack_failure_still_delivers_but_writes_no_blank_profile(self):
        """Keep-everyone on API failure, per #60. But do not store a nameless row.

        Writing a member with no real_name is what left raw Slack ids showing in
        the dashboard (#68), so the upsert waits until a profile is actually
        available. Delivery does not need the row.
        """
        db = MagicMock()
        db.get_all_members.return_value = []
        client = MagicMock()
        client.users_list.side_effect = Exception("slack down")
        client.users_info.side_effect = Exception("slack down")
        with patch.dict(sys.modules, {"db": db}):
            out = sched_mod.resolve_participants(client, "T1", ["U1", "U2"], [{"user_id": "U1"}])
        assert set(m["user_id"] for m in out) == {"U1", "U2"}
        db.upsert_member.assert_not_called()

    def test_empty_participants_returns_the_members_untouched(self):
        members = [{"user_id": "U1"}]
        with patch.dict(sys.modules, {"db": MagicMock()}):
            assert sched_mod.resolve_participants(_client([]), "T1", [], members) is members


class TestPaginationIsBounded:
    def test_a_never_ending_cursor_does_not_loop_forever(self):
        """A malformed response used to spin users.list until the process died."""
        client = MagicMock()
        client.users_list.return_value = {
            "members": [_slack_user("U1")],
            "response_metadata": {"next_cursor": "always-more"},
        }
        out = slack_users.fetch_human_users(client, ["U1"])
        assert "U1" in out
        assert client.users_list.call_count == slack_users.MAX_USER_PAGES

    def test_a_non_string_cursor_ends_the_walk(self):
        client = MagicMock()
        client.users_list.return_value = {"members": [_slack_user("U1")], "response_metadata": MagicMock()}
        slack_users.fetch_human_users(client, ["U1"])
        assert client.users_list.call_count == 1
