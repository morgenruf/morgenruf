"""The overflow menu: another starter, a new match, unavailable, pause.

Donut puts these behind one "More options" control. Four equal-weight buttons
under an introduction read as a form to fill in, and the message the pair came
for is the introduction, not the admin.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.modules.connect import blocks as cb

from tests.support import patch_modules


def _overflow(blocks):
    for b in blocks:
        acc = b.get("accessory") or {}
        if acc.get("type") == "overflow":
            return acc
    return None


class TestTheMenuExists:
    def test_the_intro_carries_one_overflow_not_a_button_row(self):
        _, blocks = cb.intro_message(["U1", "U2"], seed=1, program_id=3, match_id=77)
        assert _overflow(blocks) is not None
        assert not [b for b in blocks if b["type"] == "actions"]

    def test_it_offers_the_four_actions(self):
        _, blocks = cb.intro_message(["U1", "U2"], seed=1, program_id=3, match_id=77)
        values = [o["value"] for o in _overflow(blocks)["options"]]
        assert values == ["starter", "rematch", "skip", "pause"]

    def test_slack_allows_at_most_five_options(self):
        _, blocks = cb.intro_message(["U1", "U2"], seed=1, program_id=3, match_id=77)
        assert len(_overflow(blocks)["options"]) <= 5

    def test_the_action_id_carries_the_programme_and_the_match(self):
        _, blocks = cb.intro_message(["U1", "U2"], seed=1, program_id=3, match_id=77)
        assert _overflow(blocks)["action_id"] == "connect:more:3:77"

    def test_every_option_is_handled(self):
        """An option that routes nowhere is a menu entry that does nothing."""
        import importlib.util
        import pathlib

        registered = []

        class FakeApp:
            def action(self, pattern):
                registered.append(pattern)
                return lambda f: f

            def __getattr__(self, _):
                return lambda *a, **k: lambda f: f

        path = pathlib.Path(__file__).resolve().parent.parent / "src/modules/connect/handlers.py"
        spec = importlib.util.spec_from_file_location("more_probe", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.register_handlers(FakeApp())

        _, blocks = cb.intro_message(["U1", "U2"], seed=1, program_id=3, match_id=77)
        action_id = _overflow(blocks)["action_id"]
        assert any(hasattr(p, "match") and p.match(action_id) for p in registered)

        # And the dispatcher must recognise every value the menu can send.
        import inspect

        source = inspect.getsource(mod._handle_more)
        for option in _overflow(blocks)["options"]:
            assert f'"{option["value"]}"' in source, f"{option['value']} routes nowhere"


class TestAnotherStarter:
    def _body(self, value="starter"):
        return {
            "user": {"id": "U1"},
            "channel": {"id": "D1"},
            "team": {"id": "T1"},
            "actions": [
                {
                    "action_id": "connect:more:3:77",
                    "selected_option": {"value": value},
                }
            ],
        }

    def test_a_new_prompt_goes_to_the_dm_so_both_can_see_it(self):
        from src.modules.connect.handlers import _handle_more

        db = MagicMock()
        db.match_by_id.return_value = {"id": 77, "round_id": 5, "team_id": "T1", "member_ids": ["U1", "U2"]}
        client = MagicMock()
        with patch_modules({"src.modules.connect.db": db}):
            _handle_more(self._body(), client)
        # Shared, not ephemeral: a starter only works if both read it.
        assert client.chat_postMessage.called
        assert not client.chat_postEphemeral.called

    def test_it_never_hands_back_the_prompt_already_on_screen(self):
        # Asking for another and getting the same sentence is worse than no button.
        for seed in range(40):
            current = cb.icebreaker(seed)
            assert cb.next_icebreaker(seed, exclude=current) != current

    def test_there_are_enough_prompts_for_repeated_asking(self):
        assert len(cb.ICEBREAKERS) >= 20
        assert len(set(cb.ICEBREAKERS)) == len(cb.ICEBREAKERS)


class TestNewMatchRequest:
    def _body(self):
        return {
            "user": {"id": "U1"},
            "channel": {"id": "D1"},
            "team": {"id": "T1"},
            "actions": [{"action_id": "connect:more:3:77", "selected_option": {"value": "rematch"}}],
        }

    def _db(self, partner=None):
        db = MagicMock()
        db.match_by_id.return_value = {
            "id": 77,
            "round_id": 5,
            "team_id": "T1",
            "program_id": 3,
            "member_ids": ["U1", "U2"],
        }
        db.claim_rematch_partner.return_value = partner
        return db

    def _run(self, db):
        from src.modules.connect.handlers import _handle_more

        client = MagicMock()
        api = MagicMock()
        api.open_group_dm.return_value = "D_NEW"
        with patch_modules({"src.modules.connect.db": db, "src.modules.connect.slack_api": api}):
            _handle_more(self._body(), client)
        return client, api

    def test_with_nobody_waiting_the_request_is_recorded_and_kept_private(self):
        db = self._db(partner=None)
        client, api = self._run(db)
        db.request_rematch.assert_called_once()
        api.open_group_dm.assert_not_called()
        # The other person must not learn they were rejected.
        assert client.chat_postEphemeral.called
        assert not client.chat_postMessage.called

    def test_two_requesters_are_introduced_to_each_other(self):
        db = self._db(partner="U9")
        client, api = self._run(db)
        api.open_group_dm.assert_called_once()
        assert sorted(api.open_group_dm.call_args[0][1]) == ["U1", "U9"]
        api.post.assert_called_once()

    def test_a_stranger_cannot_request_on_someone_elses_match(self):
        db = self._db()
        body = self._body()
        body["user"]["id"] = "U_OTHER"
        from src.modules.connect.handlers import _handle_more

        with patch_modules({"src.modules.connect.db": db}):
            _handle_more(body, MagicMock())
        db.request_rematch.assert_not_called()

    def test_a_missing_match_is_ignored(self):
        db = self._db()
        db.match_by_id.return_value = None
        self._run(db)
        db.request_rematch.assert_not_called()


class TestPauseAndSkip:
    def _body(self, value):
        return {
            "user": {"id": "U1"},
            "channel": {"id": "D1"},
            "team": {"id": "T1"},
            "actions": [{"action_id": "connect:more:3:77", "selected_option": {"value": value}}],
        }

    def test_pause_opts_the_person_out_of_the_programme(self):
        from src.modules.connect.handlers import _handle_more

        db = MagicMock()
        client = MagicMock()
        with patch_modules({"src.modules.connect.db": db}):
            _handle_more(self._body("pause"), client)
        db.opt_out.assert_called_once_with("T1", 3, "U1", mode="off")

    def test_a_failed_pause_says_so_rather_than_claiming_success(self):
        from src.modules.connect.handlers import _handle_more

        db = MagicMock()
        db.opt_out.side_effect = RuntimeError("db down")
        client = MagicMock()
        with patch_modules({"src.modules.connect.db": db}):
            _handle_more(self._body("pause"), client)
        said = client.chat_postEphemeral.call_args.kwargs["text"]
        assert "did not save" in said

    def test_unavailable_is_acknowledged_only_to_the_person(self):
        from src.modules.connect.handlers import _handle_more

        client = MagicMock()
        _handle_more(self._body("skip"), client)
        assert client.chat_postEphemeral.called
        assert not client.chat_postMessage.called
