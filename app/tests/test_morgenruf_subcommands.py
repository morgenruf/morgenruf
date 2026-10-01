"""Modules can claim `/morgenruf <word>` without core importing them."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.core import profile_slack
from src.core.modules import ModuleSpec


def _spec(name, words):
    spec = MagicMock()
    spec.name = name
    spec.slash_subcommands = words
    return spec


def _body(text):
    return {"text": text, "team_id": "T1", "user_id": "U1"}


def test_active_module_word_is_routed_with_the_rest_of_the_text():
    handler = MagicMock()
    spec = _spec("polls", {"poll": handler})
    with patch.object(profile_slack, "_active_specs", return_value=[spec]):
        routed = profile_slack.dispatch_subcommand(_body('poll "Lunch?" "Pizza" "Sushi"'), MagicMock(), MagicMock())
    assert routed is True
    handler.assert_called_once()
    assert handler.call_args.args[3] == '"Lunch?" "Pizza" "Sushi"'


def test_the_word_is_matched_without_case():
    handler = MagicMock()
    with patch.object(profile_slack, "_active_specs", return_value=[_spec("polls", {"poll": handler})]):
        assert profile_slack.dispatch_subcommand(_body("  POLL  "), MagicMock(), MagicMock()) is True
    assert handler.call_args.args[3] == ""


def test_a_newline_or_tab_after_the_word_still_routes():
    handler = MagicMock()
    with patch.object(profile_slack, "_active_specs", return_value=[_spec("polls", {"poll": handler})]):
        assert profile_slack.dispatch_subcommand(_body('poll\n"Lunch?" "A" "B"'), MagicMock(), MagicMock()) is True
        assert profile_slack.dispatch_subcommand(_body('poll\t"Q" "A" "B"'), MagicMock(), MagicMock()) is True
    assert [c.args[3] for c in handler.call_args_list] == ['"Lunch?" "A" "B"', '"Q" "A" "B"']


def test_inactive_module_word_falls_back_to_help():
    with patch.object(profile_slack, "_active_specs", return_value=[]):
        routed = profile_slack.dispatch_subcommand(_body("poll x"), MagicMock(), MagicMock())
    assert routed is False


def test_profile_and_help_are_not_claimable():
    handler = MagicMock()
    spec = _spec("evil", {"profile": handler, "help": handler})
    with patch.object(profile_slack, "_active_specs", return_value=[spec]):
        assert profile_slack.dispatch_subcommand(_body("profile"), MagicMock(), MagicMock()) is False
        assert profile_slack.dispatch_subcommand(_body("help"), MagicMock(), MagicMock()) is False
        assert profile_slack.dispatch_subcommand(_body(""), MagicMock(), MagicMock()) is False
    handler.assert_not_called()


def test_a_module_without_subcommands_is_skipped():
    handler = MagicMock()
    specs = [_spec("kudos", None), _spec("polls", {"poll": handler})]
    with patch.object(profile_slack, "_active_specs", return_value=specs):
        assert profile_slack.dispatch_subcommand(_body("poll"), MagicMock(), MagicMock()) is True
    handler.assert_called_once()


def test_a_failing_lookup_falls_back_to_help():
    with patch.object(profile_slack, "_active_specs", side_effect=RuntimeError("db down")):
        assert profile_slack.dispatch_subcommand(_body("poll"), MagicMock(), MagicMock()) is False


def test_the_spec_field_defaults_to_none():
    spec = ModuleSpec(
        name="demo",
        required_scopes=(),
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=(),
        default_enabled=True,
    )
    assert spec.slash_subcommands is None


class _Bolt:
    def __init__(self):
        self.commands = {}

    def command(self, name):
        return lambda fn: self.commands.setdefault(name, fn)

    def action(self, name):
        return lambda fn: fn

    def view(self, name):
        return lambda fn: fn


def test_the_command_routes_a_claimed_word_before_help():
    bolt = _Bolt()
    profile_slack.register_slack(bolt)
    handler = MagicMock()
    client, respond, ack = MagicMock(), MagicMock(), MagicMock()
    with patch.object(profile_slack, "_active_specs", return_value=[_spec("polls", {"poll": handler})]):
        bolt.commands["/morgenruf"](ack=ack, body=_body("poll a b"), client=client, respond=respond)
    ack.assert_called_once()
    assert handler.call_args.args == (_body("poll a b"), client, respond, "a b")
    client.chat_postMessage.assert_not_called()


def test_the_command_still_helps_for_an_unclaimed_word():
    bolt = _Bolt()
    profile_slack.register_slack(bolt)
    client = MagicMock()
    with (
        patch.object(profile_slack, "_active_specs", return_value=[]),
        patch.object(profile_slack, "help_blocks", return_value=[]),
    ):
        bolt.commands["/morgenruf"](ack=MagicMock(), body=_body("poll a b"), client=client, respond=MagicMock())
    client.chat_postMessage.assert_called_once()
