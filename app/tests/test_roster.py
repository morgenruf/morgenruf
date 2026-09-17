"""Shared eligibility: one answer to who can be contacted right now."""

from __future__ import annotations

from unittest.mock import patch

from src.core.roster import Member, eligible_members

ROWS = [
    {"user_id": "U1", "real_name": "Ada", "tz": "UTC", "active": True, "on_vacation": False},
    {"user_id": "U2", "real_name": "Left", "tz": "UTC", "active": False, "on_vacation": False},
    {"user_id": "U3", "real_name": "Away", "tz": "UTC", "active": True, "on_vacation": True},
    {"user_id": "U4", "real_name": "Bob", "tz": "Europe/Berlin", "active": True, "on_vacation": False},
]


def run(exclude=(), rows=None):
    with patch("src.core.roster.db") as db:
        db.get_all_members.return_value = ROWS if rows is None else rows
        return eligible_members("T1", exclude=exclude)


def test_deactivated_members_are_excluded():
    assert "U2" not in [m.user_id for m in run()]


def test_members_on_vacation_are_excluded():
    assert "U3" not in [m.user_id for m in run()]


def test_the_remaining_members_are_returned():
    assert [m.user_id for m in run()] == ["U1", "U4"]


def test_rows_are_mapped_to_members():
    assert run()[0] == Member(user_id="U1", name="Ada", tz="UTC")


def test_explicit_exclusions_are_honoured():
    assert [m.user_id for m in run(exclude=("U1",))] == ["U4"]


def test_a_missing_timezone_defaults_to_utc():
    rows = [{"user_id": "U9", "real_name": "N", "tz": None, "active": True, "on_vacation": False}]
    assert run(rows=rows)[0].tz == "UTC"


def test_a_missing_name_does_not_crash():
    rows = [{"user_id": "U9", "real_name": None, "tz": "UTC", "active": True, "on_vacation": False}]
    assert run(rows=rows)[0].name == ""


def test_columns_added_by_later_migrations_may_be_absent():
    """on_vacation and active arrived in later migrations, so treat a missing
    key as the permissive default rather than raising."""
    rows = [{"user_id": "U9", "real_name": "N", "tz": "UTC"}]
    assert [m.user_id for m in run(rows=rows)] == ["U9"]
