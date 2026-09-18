"""The roster is the one place that says who a person is.

The coffee chat member table asked each Member for `real_name` and `avatar`.
Member has neither: it has `name`, and had no avatar at all. getattr with a
default turns that into an empty string, so the table fell back to the raw
Slack id for every row and showed no faces, on every workspace, for as long as
the table had existed. Nothing failed and nothing logged.
"""

from __future__ import annotations

import pathlib
import re
import sys
from unittest.mock import MagicMock

import pytest

for mod in ("psycopg2", "psycopg2.extras", "psycopg2.pool", "slack_sdk", "slack_bolt"):
    sys.modules.setdefault(mod, MagicMock())

from src.core.roster import Member, eligible_members  # noqa: E402

APP = pathlib.Path(__file__).resolve().parent.parent

ROW = {
    "user_id": "U1",
    "real_name": "Ankit Kumar",
    "display_name": "ankit",
    "tz": "Asia/Kolkata",
    "avatar_url": "https://example.test/a.png",
    "active": True,
    "on_vacation": False,
}


@pytest.fixture()
def roster(monkeypatch):
    def rows(_team_id, data=None):
        return list(data if data is not None else [ROW])

    import src.core.roster as roster_mod

    def use(data):
        monkeypatch.setattr(roster_mod.db, "get_all_members", lambda t: list(data))
        return eligible_members("T1")

    return use


class TestAPersonCarriesTheirName:
    def test_the_name_comes_through(self, roster):
        assert roster([ROW])[0].name == "Ankit Kumar"

    def test_so_does_the_face(self, roster):
        assert roster([ROW])[0].avatar == "https://example.test/a.png"

    def test_a_handle_is_better_than_an_id(self, roster):
        row = dict(ROW, real_name="")
        assert roster([row])[0].name == "ankit"

    def test_a_row_with_neither_is_empty_not_an_error(self, roster):
        row = dict(ROW, real_name="", display_name=None)
        person = roster([row])[0]
        assert person.name == "" and person.user_id == "U1"

    def test_a_missing_avatar_is_an_empty_string(self, roster):
        assert roster([dict(ROW, avatar_url=None)])[0].avatar == ""


class TestNobodyAsksForAFieldThatIsNotThere:
    """getattr with a default is how the last one went unnoticed for weeks."""

    FIELDS = set(Member.__dataclass_fields__)

    def test_the_member_table_reads_fields_that_exist(self):
        src = (APP / "src/modules/connect/dashboard.py").read_text()
        block = src[src.index("def list_program_members") :]
        block = block[: block.index("@bp.route", 10)] if "@bp.route" in block[10:] else block
        asked = set(re.findall(r'getattr\(\s*member\s*,\s*"([^"]+)"', block))
        missing = sorted(f for f in asked if f not in self.FIELDS)
        assert not missing, f"the table asks Member for fields it does not have: {missing}"

    def test_no_module_reaches_for_a_field_member_lacks(self):
        bad = []
        for path in sorted((APP / "src").rglob("*.py")):
            text = path.read_text()
            if "eligible_members" not in text:
                continue
            for name in re.findall(r'getattr\(\s*m(?:ember)?\s*,\s*"([^"]+)"', text):
                if name not in self.FIELDS:
                    bad.append(f"{path.relative_to(APP)}: {name}")
        assert not bad, "code asking a Member for a field it does not have:\n  " + "\n  ".join(bad)

    def test_the_guard_knows_the_real_fields(self):
        assert {"user_id", "name", "tz", "avatar"} <= self.FIELDS
