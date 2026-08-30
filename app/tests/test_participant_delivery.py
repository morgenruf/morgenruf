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


class TestMemberSync:
    """People who left Slack must stop appearing (nothing ever deactivated them)."""

    @staticmethod
    def _run(db, client):
        with patch.dict(sys.modules, {"db": db}), patch.object(sched_mod, "WebClient", return_value=client):
            sched_mod.sync_members_from_slack()

    def _db(self, stored):
        db = MagicMock()
        db.get_all_installations.return_value = [{"team_id": "T1", "bot_token": "xoxb"}]
        db.get_all_members.return_value = stored
        db.set_members_active.return_value = 1
        return db

    def test_a_member_who_left_is_deactivated(self):
        db = self._db(
            [
                {"user_id": "U_gone", "active": True, "real_name": "Left"},
                {"user_id": "U_here", "active": True, "real_name": "Still here"},
            ]
        )
        # Slack still reports a populated workspace, just without U_gone.
        self._run(db, _client([_slack_user("U_here", "Still here")]))
        db.set_members_active.assert_any_call("T1", ["U_gone"], False)

    def test_a_member_who_returned_is_restored(self):
        db = self._db([{"user_id": "U_back", "active": False, "real_name": "Back"}])
        self._run(db, _client([_slack_user("U_back", "Back")]))
        db.set_members_active.assert_any_call("T1", ["U_back"], True)

    def test_the_bot_is_deactivated(self):
        db = self._db([{"user_id": "BMORGENRUF", "active": True, "real_name": "Morgenruf"}])
        self._run(db, _client([_slack_user("BMORGENRUF", "Morgenruf", is_bot=True), _slack_user("U1")]))
        db.set_members_active.assert_any_call("T1", ["BMORGENRUF"], False)

    def test_a_nameless_row_gets_backfilled(self):
        db = self._db([{"user_id": "U9", "active": True, "real_name": ""}])
        self._run(db, _client([_slack_user("U9", "Real Name")]))
        db.upsert_member.assert_called_once()
        assert db.upsert_member.call_args.kwargs["real_name"] == "Real Name"

    def test_an_unreadable_workspace_is_skipped_entirely(self):
        """A failed lookup must never be read as "nobody works here"."""
        db = self._db([{"user_id": "U1", "active": True, "real_name": "Ada"}])
        client = MagicMock()
        client.users_list.side_effect = Exception("slack down")
        self._run(db, client)
        db.set_members_active.assert_not_called()

    def test_an_empty_user_list_is_refused(self):
        db = self._db([{"user_id": "U1", "active": True, "real_name": "Ada"}])
        self._run(db, _client([]))
        # Slack claims nobody exists while we hold members: far likelier a bad
        # response than an empty workspace, so change nothing.
        for call in db.set_members_active.call_args_list:
            assert call.args[1] != ["U1"] or call.args[2] is not False

    def test_a_leaver_is_also_pruned_from_schedules(self):
        """Deactivating the row alone left them in the participation denominator.

        compute_participation invents a member row for anyone named in a
        schedule's participants but missing from the members table, so a leaver
        kept being counted (and listed) until the schedule was edited by hand.
        """
        db = self._db(
            [
                {"user_id": "U_gone", "active": True, "real_name": "Left"},
                {"user_id": "U_here", "active": True, "real_name": "Still here"},
            ]
        )
        self._run(db, _client([_slack_user("U_here", "Still here")]))
        db.remove_participants_everywhere.assert_called_once_with("T1", ["U_gone"])

    def test_nobody_leaving_means_no_schedule_edits(self):
        db = self._db([{"user_id": "U1", "active": True, "real_name": "Ada"}])
        self._run(db, _client([_slack_user("U1", "Ada")]))
        db.remove_participants_everywhere.assert_not_called()


class TestMemberSyncPacing:
    """The first production run rate limited every workspace it touched.

    users.list is Tier 2. Walking every installation back to back tripped
    Slack's limit, and each 429 surfaced as a generic SlackApiError, so a
    healthy workspace was skipped and looked exactly like a revoked token.
    """

    def test_the_loop_pauses_between_workspaces(self):
        db = MagicMock()
        db.get_all_installations.return_value = [{"team_id": f"T{i}", "bot_token": "xoxb"} for i in range(4)]
        db.get_all_members.return_value = [{"user_id": "U1", "active": True, "real_name": "Ada"}]
        client = _client([_slack_user("U1", "Ada")])
        with (
            patch.dict(sys.modules, {"db": db}),
            patch.object(sched_mod, "_rate_limited_client", return_value=client),
            patch.object(sched_mod.time, "sleep") as slept,
        ):
            sched_mod.sync_members_from_slack()
        # Four workspaces means three gaps, not four: no pause before the first.
        assert slept.call_count == 3
        assert all(c.args[0] == sched_mod._MEMBER_SYNC_PAUSE_SECONDS for c in slept.call_args_list)

    def test_a_single_workspace_does_not_pause(self):
        db = MagicMock()
        db.get_all_installations.return_value = [{"team_id": "T1", "bot_token": "xoxb"}]
        db.get_all_members.return_value = [{"user_id": "U1", "active": True, "real_name": "Ada"}]
        with (
            patch.dict(sys.modules, {"db": db}),
            patch.object(sched_mod, "_rate_limited_client", return_value=_client([_slack_user("U1", "Ada")])),
            patch.object(sched_mod.time, "sleep") as slept,
        ):
            sched_mod.sync_members_from_slack()
        slept.assert_not_called()

    def test_the_client_carries_a_rate_limit_retry_handler(self):
        client = sched_mod._rate_limited_client("xoxb-test")
        names = [type(h).__name__ for h in client.retry_handlers]
        assert "RateLimitErrorRetryHandler" in names


class TestSlackErrorIsDiagnosable:
    def test_the_slack_error_code_is_logged_not_the_generic_message(self, caplog):
        """ "The request to the Slack API failed" does not say ratelimited."""
        import logging

        class FakeResponse(dict):
            pass

        err = Exception("The request to the Slack API failed.")
        err.response = FakeResponse({"error": "ratelimited"})
        client = MagicMock()
        client.users_list.side_effect = err

        with caplog.at_level(logging.WARNING):
            assert slack_users.fetch_workspace_humans(client) is None
        assert "ratelimited" in caplog.text
