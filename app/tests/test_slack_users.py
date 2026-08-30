"""Tests for slack_users: keeping bots out of standup participant lists (#53)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from slack_users import filter_human_ids, is_human  # noqa: E402


def _user(uid, **overrides):
    user = {"id": uid, "deleted": False, "is_bot": False}
    user.update(overrides)
    return user


def _client(users, info_map=None):
    client = MagicMock()
    client.users_list.return_value = {"members": users, "response_metadata": {}}
    if info_map is not None:
        client.users_info.side_effect = lambda user: {"user": info_map[user]}
    return client


class TestIsHuman:
    def test_plain_user_is_human(self):
        assert is_human(_user("U1")) is True

    def test_bot_is_not_human(self):
        assert is_human(_user("B1", is_bot=True)) is False

    def test_slackbot_is_not_human(self):
        assert is_human(_user("USLACKBOT")) is False

    def test_deactivated_user_is_not_human(self):
        assert is_human(_user("U1", deleted=True)) is False

    def test_missing_user_is_not_human(self):
        assert is_human(None) is False
        assert is_human({}) is False


class TestFilterHumanIds:
    def test_drops_bots_and_slackbot(self):
        client = _client([_user("U1"), _user("B1", is_bot=True), _user("USLACKBOT")])
        assert filter_human_ids(client, ["U1", "B1", "USLACKBOT"]) == {"U1"}

    def test_reporter_scenario_one_human_two_bots(self):
        """#53: channel holds the reporter plus Morgenruf and one other app."""
        client = _client([_user("U1"), _user("BMORGENRUF", is_bot=True), _user("BOTHER", is_bot=True)])
        assert filter_human_ids(client, ["U1", "BMORGENRUF", "BOTHER"]) == {"U1"}

    def test_empty_input_makes_no_api_calls(self):
        client = _client([])
        assert filter_human_ids(client, []) == set()
        client.users_list.assert_not_called()

    def test_uses_one_bulk_call_not_per_user_lookups(self):
        client = _client([_user(f"U{i}") for i in range(50)])
        filter_human_ids(client, [f"U{i}" for i in range(50)])
        assert client.users_list.call_count == 1
        client.users_info.assert_not_called()

    def test_follows_pagination(self):
        client = MagicMock()
        client.users_list.side_effect = [
            {"members": [_user("U1")], "response_metadata": {"next_cursor": "c2"}},
            {"members": [_user("B1", is_bot=True)], "response_metadata": {}},
        ]
        assert filter_human_ids(client, ["U1", "B1"]) == {"U1"}
        assert client.users_list.call_count == 2

    def test_id_missing_from_users_list_falls_back_to_users_info(self):
        """Slack Connect guests don't show up in users.list."""
        client = _client([_user("U1")], info_map={"UGUEST": _user("UGUEST")})
        assert filter_human_ids(client, ["U1", "UGUEST"]) == {"U1", "UGUEST"}
        client.users_info.assert_called_once_with(user="UGUEST")

    def test_bot_found_only_via_users_info_is_dropped(self):
        client = _client([], info_map={"B1": _user("B1", is_bot=True)})
        assert filter_human_ids(client, ["B1"]) == set()

    def test_users_list_failure_keeps_everyone(self):
        """Never silently drop people from a standup because Slack hiccupped."""
        client = MagicMock()
        client.users_list.side_effect = Exception("ratelimited")
        assert filter_human_ids(client, ["U1", "U2"]) == {"U1", "U2"}

    def test_users_info_failure_keeps_that_user(self):
        client = _client([])
        client.users_info.side_effect = Exception("ratelimited")
        assert filter_human_ids(client, ["U1"]) == {"U1"}
