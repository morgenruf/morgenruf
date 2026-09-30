"""The profile in Slack: /morgenruf, the modal, and the App Home section."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import date
from unittest.mock import MagicMock

import pytest
import src.core.db as real_db
from src.core import profile_slack


class FakeBolt:
    """Captures listeners the way Bolt registers them."""

    def __init__(self):
        self.commands, self.actions, self.views = {}, {}, {}

    def command(self, name):
        return lambda fn: self.commands.setdefault(name, fn)

    def action(self, name):
        return lambda fn: self.actions.setdefault(name, fn)

    def view(self, name):
        return lambda fn: self.views.setdefault(name, fn)


@pytest.fixture
def db(monkeypatch):
    fake = MagicMock()
    fake.ProfileValidationError = real_db.ProfileValidationError
    fake.get_member_profile.return_value = None
    fake.granted_scopes.return_value = set()
    fake.module_settings.return_value = {}
    monkeypatch.setitem(sys.modules, "src.core.db", fake)
    monkeypatch.setattr(importlib.import_module("src.core"), "db", fake)
    return fake


@pytest.fixture
def bolt():
    app = FakeBolt()
    profile_slack.register_slack(app)
    return app


def submission(month=None, day=None, start=None, role=None, options=()):
    def select(value):
        return {"selected_option": {"value": str(value)}} if value is not None else {"selected_option": None}

    return {
        "birth_month": {"profile:birth_month": select(month)},
        "birth_day": {"profile:birth_day": select(day)},
        "start_date": {"profile:start_date": {"selected_date": start}},
        "role": {"profile:role": {"value": role}},
        "location": {"profile:location": {"value": None}},
        "ask_me_about": {"profile:ask_me_about": {"value": None}},
        "options": {"profile:options": {"selected_options": [{"value": o} for o in options]}},
    }


class TestTheCommand:
    def test_is_registered_by_core(self, bolt):
        assert "/morgenruf" in bolt.commands

    def test_standup_no_longer_claims_it(self):
        # Two listeners on one command would both run.
        src = importlib.import_module("src.modules.standup.handlers").__file__
        assert '@app.command("/morgenruf")' not in open(src).read()

    def test_profile_opens_the_modal(self, bolt, db):
        client, ack = MagicMock(), MagicMock()
        body = {"user_id": "U1", "team_id": "T1", "text": "profile", "trigger_id": "trig"}
        bolt.commands["/morgenruf"](ack=ack, body=body, client=client)
        ack.assert_called_once()
        view = client.views_open.call_args.kwargs["view"]
        assert client.views_open.call_args.kwargs["trigger_id"] == "trig"
        assert view["callback_id"] == "profile:modal"
        assert json.loads(view["private_metadata"]) == {"source": "command"}
        client.chat_postMessage.assert_not_called()

    @pytest.mark.parametrize("text", ["", "help", "  HELP  "])
    def test_bare_and_help_both_show_help(self, bolt, db, text):
        client = MagicMock()
        bolt.commands["/morgenruf"](
            ack=MagicMock(), body={"user_id": "U1", "team_id": "T1", "text": text}, client=client
        )
        client.views_open.assert_not_called()
        blocks = client.chat_postMessage.call_args.kwargs["blocks"]
        text_out = json.dumps(blocks)
        assert "/morgenruf profile" in text_out
        assert "know" not in text_out

    def test_an_unknown_subcommand_says_so_then_helps(self, bolt, db):
        client = MagicMock()
        bolt.commands["/morgenruf"](
            ack=MagicMock(), body={"user_id": "U1", "team_id": "T1", "text": "<!channel>"}, client=client
        )
        text_out = client.chat_postMessage.call_args.kwargs["blocks"][1]["text"]["text"]
        assert text_out.startswith("I don't know `&lt;!channel&gt;`")

    def test_help_lists_what_this_workspace_has_on(self, db):
        db.module_settings.return_value = {"kudos": False}
        text_out = json.dumps(profile_slack.help_blocks("T1"))
        assert "/standup" in text_out
        assert "/kudos" not in text_out  # switched off here
        assert "coffee chats" not in text_out.lower()  # needs scopes this workspace lacks


class TestTheModal:
    def test_opens_filled_in(self, db):
        row = {
            "birth_month": 2,
            "birth_day": 29,
            "start_date": date(2021, 4, 12),
            "role": "Eng",
            "celebrate": False,
        }
        view = profile_slack.profile_modal(row)
        blocks = {b.get("block_id"): b for b in view["blocks"]}
        assert blocks["birth_month"]["element"]["initial_option"]["value"] == "2"
        assert blocks["birth_day"]["element"]["initial_option"]["value"] == "29"
        assert blocks["start_date"]["element"]["initial_date"] == "2021-04-12"
        assert blocks["role"]["element"]["initial_value"] == "Eng"
        assert blocks["role"]["element"]["max_length"] == 80
        assert blocks["ask_me_about"]["element"]["max_length"] == 200
        values = [o["value"] for o in blocks["options"]["element"]["options"]]
        assert values == ["no_celebrate", "clear_start"]
        assert blocks["options"]["element"]["initial_options"][0]["value"] == "no_celebrate"

    def test_no_clear_option_without_a_start_date(self):
        blocks = {b.get("block_id"): b for b in profile_slack.profile_modal(None)["blocks"]}
        assert [o["value"] for o in blocks["options"]["element"]["options"]] == ["no_celebrate"]
        assert "initial_options" not in blocks["options"]["element"]

    def test_submission_to_fields(self):
        fields = profile_slack.fields_from_submission(
            submission(month=2, day=29, start="2021-04-12", role="Eng", options=["no_celebrate"])
        )
        assert fields == {
            "birth_month": 2,
            "birth_day": 29,
            "start_date": "2021-04-12",
            "celebrate": False,
            "role": "Eng",
            "location": None,
            "ask_me_about": None,
        }

    def test_not_set_clears_the_birthday_and_the_checkbox_clears_the_start(self):
        fields = profile_slack.fields_from_submission(
            submission(month=0, day=0, start="2021-04-12", options=["clear_start"])
        )
        assert fields["birth_month"] is None and fields["birth_day"] is None
        assert fields["start_date"] is None and fields["celebrate"] is True

    def test_saving_goes_through_the_one_write_path(self, bolt, db):
        db.upsert_member_profile.return_value = {"birth_month": 2, "birth_day": 29, "celebrate": True}
        ack = MagicMock()
        body = {"user": {"id": "U1", "team_id": "T1"}, "team": {"id": "T1"}}
        bolt.views["profile:modal"](ack=ack, body=body, view={"state": {"values": submission(month=2, day=29)}})
        args = db.upsert_member_profile.call_args
        assert args.args[:2] == ("T1", "U1") and args.kwargs["updated_by"] == "U1"
        assert ack.call_args.kwargs["response_action"] == "update"
        assert "29 February" in json.dumps(ack.call_args.kwargs["view"])

    def test_30_february_shows_on_the_day_field(self, bolt, db):
        db.upsert_member_profile.side_effect = lambda *a, **k: real_db.validate_member_profile(a[2])
        ack = MagicMock()
        body = {"user": {"id": "U1"}, "team": {"id": "T1"}}
        bolt.views["profile:modal"](ack=ack, body=body, view={"state": {"values": submission(month=2, day=30)}})
        assert ack.call_args.kwargs["response_action"] == "errors"
        assert "birth_day" in ack.call_args.kwargs["errors"]

    def test_the_edit_button_opens_the_same_modal(self, bolt, db):
        client = MagicMock()
        bolt.actions["profile:edit"](
            ack=MagicMock(), body={"user": {"id": "U1"}, "team": {"id": "T1"}, "trigger_id": "t"}, client=client
        )
        assert client.views_open.call_args.kwargs["view"]["callback_id"] == "profile:modal"


class TestTheAppHome:
    def test_empty_profile_invites_you_to_fill_it_in(self, db, monkeypatch):
        monkeypatch.setattr(profile_slack, "_celebrations_on", lambda team_id: True)
        blocks = profile_slack.home_blocks("T1", "U1")
        assert "Add your birthday and start date" in blocks[1]["text"]["text"]
        assert blocks[1]["accessory"]["action_id"] == "profile:edit"

    def test_without_celebrations_nothing_mentions_celebrating(self, db, monkeypatch):
        monkeypatch.setattr(profile_slack, "_celebrations_on", lambda team_id: False)
        blocks = profile_slack.home_blocks("T1", "U1")
        assert "celebrat" not in json.dumps(blocks).lower()
        modal = profile_slack.profile_modal({"celebrate": False}, celebrations=False)
        assert "celebrat" not in json.dumps(modal).lower()

    def test_a_filled_profile(self, db):
        db.get_member_profile.return_value = {
            "user_id": "U1",
            "birth_month": 3,
            "birth_day": 14,
            "start_date": date(2023, 3, 1),
            "location": "Berlin",
            "ask_me_about": "Rust, <!here> bouldering",
            "celebrate": True,
            "updated_by": "U_ADMIN",
        }
        text = json.dumps(profile_slack.home_blocks("T1", "U1"), ensure_ascii=False)
        assert "🎂 14 March" in text and "Joined Mar 2023" in text and "📍 Berlin" in text
        assert "&lt;!here&gt;" in text and "<!here>" not in text
        assert "changed by an admin" in text

    def test_a_database_error_leaves_the_section_out(self, db):
        db.get_member_profile.side_effect = RuntimeError("down")
        assert profile_slack.home_blocks("T1", "U1") == []

    def test_core_puts_the_profile_on_the_home_tab_first(self, db):
        from src.core.home import extra_home_blocks

        blocks = extra_home_blocks("T1", "U1", exclude="standup")
        assert blocks[1]["accessory"]["action_id"] == "profile:edit"


class TestOneHelp:
    """Every help surface renders the same text."""

    def test_modal_and_dm_share_the_command_help(self, db):
        text_out = profile_slack.help_text("T1")
        modal = json.dumps(profile_slack.help_modal("T1"))
        assert "/morgenruf help" in text_out
        assert json.dumps(text_out)[1:-1] in modal
        assert "—" not in text_out
        assert "/help`" not in text_out.replace("/morgenruf help`", "")
