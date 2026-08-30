"""The six-hourly sync registers people a schedule lists but we have no row for.

Before this, registration only happened at delivery time. A weekly schedule
naming 15 people while the members table held 1 of them delivered to that 1,
logged no error, and could not correct itself until the next firing, which for
a Friday schedule discovered on a Sunday was five days away.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import scheduler  # noqa: E402


def _user(uid, name):
    return {"id": uid, "name": name, "real_name": name, "deleted": False, "is_bot": False, "tz": "UTC"}


@pytest.fixture
def db(monkeypatch):
    fake = MagicMock()
    fake.get_all_installations.return_value = [{"team_id": "T1", "bot_token": "xoxb-test"}]
    fake.get_all_active_schedules.return_value = []
    fake.get_all_members.return_value = []
    fake.set_members_active.return_value = 0
    fake.remove_participants_everywhere.return_value = 0
    monkeypatch.setitem(sys.modules, "db", fake)
    return fake


def _run(directory):
    with (
        patch.object(scheduler, "_rate_limited_client", return_value=MagicMock()),
        patch.object(scheduler, "fetch_workspace_directory", return_value=(directory, None)),
        patch.object(scheduler, "fetch_human_users", return_value={}),
        patch.object(scheduler.time, "sleep"),
    ):
        scheduler.sync_members_from_slack()


class TestRegistersListedParticipants:
    def test_the_one_of_fifteen_case(self, db):
        """The production shape: 15 listed, 1 known, 14 real humans in Slack."""
        listed = [f"U{i:02d}" for i in range(15)]
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": listed}]
        db.get_all_members.return_value = [{"user_id": "U00", "active": True, "real_name": "Known"}]

        _run({uid: _user(uid, uid.lower()) for uid in listed})

        got = {c.args[1] for c in db.upsert_member.call_args_list}
        assert got == set(listed) - {"U00"}
        assert len(got) == 14

    def test_a_workspace_with_no_members_at_all_still_registers(self, db):
        """The guard that used to `continue` on an empty members table."""
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1", "U2"]}]
        db.get_all_members.return_value = []

        _run({"U1": _user("U1", "one"), "U2": _user("U2", "two")})

        assert {c.args[1] for c in db.upsert_member.call_args_list} == {"U1", "U2"}

    def test_profiles_come_from_the_directory_without_extra_calls(self, db):
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1"]}]
        with (
            patch.object(scheduler, "_rate_limited_client", return_value=MagicMock()),
            patch.object(
                scheduler, "fetch_workspace_directory", return_value=({"U1": _user("U1", "Ada")}, None)
            ) as directory,
            patch.object(scheduler, "fetch_human_users") as extra,
            patch.object(scheduler.time, "sleep"),
        ):
            scheduler.sync_members_from_slack()

        assert directory.call_count == 1
        extra.assert_not_called()
        assert db.upsert_member.call_args.kwargs.get("real_name") == "Ada"

    def test_someone_already_on_the_roster_is_not_touched(self, db):
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1"]}]
        db.get_all_members.return_value = [{"user_id": "U1", "active": True, "real_name": "Known"}]

        _run({"U1": _user("U1", "one")})

        db.upsert_member.assert_not_called()

    def test_a_deactivated_member_is_restored_not_re_registered(self, db):
        """Restoring is `set_members_active`. Registration must not fight it."""
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1"]}]
        db.get_all_members.return_value = [{"user_id": "U1", "active": False, "real_name": "Back"}]

        _run({"U1": _user("U1", "one")})

        db.upsert_member.assert_not_called()
        db.set_members_active.assert_any_call("T1", ["U1"], True)


class TestItDoesNotRegisterTheWrongPeople:
    def test_a_listed_id_slack_does_not_report_is_skipped(self, db):
        """Bots and deactivated accounts are absent from the directory."""
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1", "UBOT"]}]

        _run({"U1": _user("U1", "one")})

        assert {c.args[1] for c in db.upsert_member.call_args_list} == {"U1"}

    def test_another_workspaces_participants_are_not_registered_here(self, db):
        db.get_all_active_schedules.return_value = [
            {"team_id": "T1", "participants": ["U1"]},
            {"team_id": "T2", "participants": ["U9"]},
        ]

        _run({"U1": _user("U1", "one"), "U9": _user("U9", "nine")})

        assert {c.args[1] for c in db.upsert_member.call_args_list} == {"U1"}

    def test_a_workspace_we_cannot_read_registers_nobody(self, db):
        """A failed users.list must not be read as an empty workspace."""
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1"]}]
        db.get_all_members.return_value = [{"user_id": "U0", "active": True, "real_name": "x"}]

        with (
            patch.object(scheduler, "_rate_limited_client", return_value=MagicMock()),
            patch.object(scheduler, "fetch_workspace_directory", return_value=(None, "ratelimited")),
            patch.object(scheduler.time, "sleep"),
        ):
            scheduler.sync_members_from_slack()

        db.upsert_member.assert_not_called()
        db.set_members_active.assert_not_called()

    def test_an_empty_directory_is_treated_as_a_bad_response(self, db):
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1"]}]
        db.get_all_members.return_value = [{"user_id": "U0", "active": True, "real_name": "x"}]

        _run({})

        db.upsert_member.assert_not_called()

    def test_schedules_failing_to_load_does_not_stop_the_rest_of_the_sync(self, db):
        db.get_all_active_schedules.side_effect = RuntimeError("no db")
        db.get_all_members.return_value = [{"user_id": "U0", "active": True, "real_name": "x"}]

        _run({"U0": _user("U0", "zero")})

        db.upsert_member.assert_not_called()
        db.get_all_members.assert_called()

    def test_one_failed_registration_does_not_abort_the_others(self, db):
        db.get_all_active_schedules.return_value = [{"team_id": "T1", "participants": ["U1", "U2", "U3"]}]
        db.upsert_member.side_effect = [RuntimeError("clash"), None, None]

        _run({uid: _user(uid, uid) for uid in ["U1", "U2", "U3"]})

        assert db.upsert_member.call_count == 3
