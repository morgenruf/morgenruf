"""Agreeing a time, which is the step that otherwise does not happen.

Donut introduces two people and leaves them to negotiate. Both are willing and
neither wants to be the one who picks, so the introduction dies in the DM. One
tap per acceptable time lets the bot settle it as soon as everyone has accepted
the same one, with no calendar access and no OAuth.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.modules.connect import blocks as cb
from src.modules.connect.hours import local_label, zone_city

from tests.support import patch_modules

SLOT = datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc)


class TestLocalTimes:
    """A UTC time is one neither reader thinks in."""

    def test_both_zones_appear(self):
        label = local_label(SLOT, ["Asia/Kolkata", "Europe/Amsterdam"])
        assert "Kolkata 12:30" in label
        assert "Amsterdam 09:00" in label
        assert "UTC" not in label

    def test_the_earlier_clock_reads_first(self):
        # The person for whom it is early should see the ask being made of them.
        label = local_label(SLOT, ["Asia/Kolkata", "Europe/Amsterdam"])
        assert label.index("Amsterdam") < label.index("Kolkata")

    def test_one_shared_zone_is_written_once(self):
        label = local_label(SLOT, ["Asia/Kolkata", "Asia/Kolkata"])
        assert label.count("Kolkata") == 1

    def test_an_unknown_zone_falls_back_to_utc_rather_than_failing(self):
        assert local_label(SLOT, ["Mars/Olympus"]) == "Friday 07:00 UTC"

    def test_no_zones_at_all_still_renders(self):
        assert "07:00 UTC" in local_label(SLOT, [])

    def test_a_naive_datetime_is_treated_as_utc(self):
        naive = SLOT.replace(tzinfo=None)
        assert local_label(naive, ["Europe/Amsterdam"]) == local_label(SLOT, ["Europe/Amsterdam"])

    def test_city_drops_the_region(self):
        assert zone_city("America/Argentina/Buenos_Aires") == "Buenos Aires"
        assert zone_city("") == "UTC"


class TestIntroMessageSlots:
    def _msg(self, **kw):
        times = [
            {"label": "Friday · Amsterdam 09:00 · Kolkata 12:30", "utc": SLOT.isoformat(), "add_url": "https://cal"},
            {
                "label": "Friday · Amsterdam 11:00 · Kolkata 14:30",
                "utc": (SLOT + timedelta(hours=2)).isoformat(),
                "add_url": "https://cal2",
            },
        ]
        times[0].update(kw.pop("first", {}))
        return cb.intro_message(["U1", "U2"], seed=1, program_id=1, suggested_times=times, match_id=77, **kw)

    def _accept_buttons(self, blocks):
        # The intro section also carries an overflow, so select on type.
        return [b["accessory"] for b in blocks if b.get("accessory") and b["accessory"]["type"] == "button"]

    def test_each_time_gets_its_own_button(self):
        _, blocks = self._msg()
        buttons = self._accept_buttons(blocks)
        assert len(buttons) == 2
        assert all(b["text"]["text"] == "Works for me" for b in buttons)

    def test_the_button_carries_the_match_and_the_slot(self):
        _, blocks = self._msg()
        acc = self._accept_buttons(blocks)[0]
        assert acc["action_id"].startswith("connect:accept_slot:77:")
        assert acc["value"] == SLOT.isoformat()

    def test_who_already_accepted_is_shown(self):
        _, blocks = self._msg(first={"accepted": ["U1"]})
        text = "\n".join(b["text"]["text"] for b in blocks if b.get("text"))
        assert "<@U1> can make this one" in text

    def test_slack_block_limit_is_respected(self):
        _, blocks = self._msg()
        assert len(blocks) <= 50


class TestAgreedMessage:
    def test_it_names_the_time_and_offers_a_calendar_link(self):
        text, blocks = cb.agreed_message(["U1", "U2"], "Friday · Amsterdam 09:00", "https://cal")
        assert "Settled" in text
        urls = [e["url"] for b in blocks if b["type"] == "actions" for e in b["elements"]]
        assert urls == ["https://cal"]

    def test_without_a_link_there_is_no_dead_button(self):
        _, blocks = cb.agreed_message(["U1", "U2"], "Friday", "")
        assert not [b for b in blocks if b["type"] == "actions"]

    def test_it_still_says_calendars_were_not_checked(self):
        # The honest caveat has to survive: we never read anyone's calendar.
        _, blocks = cb.agreed_message(["U1", "U2"], "Friday", "https://cal")
        ctx = " ".join(e["text"] for b in blocks if b["type"] == "context" for e in b["elements"])
        assert "calendars" in ctx


class TestAcceptSlotHandler:
    """The handler re-reads everything, because a group DM can be days old."""

    def _body(self, user="U1", match=77, slot=SLOT):
        return {
            "user": {"id": user},
            "channel": {"id": "D1"},
            "actions": [{"action_id": f"connect:accept_slot:{match}:{slot.isoformat()}", "value": slot.isoformat()}],
        }

    def _db(self, agreed=None, votes=None, members=("U1", "U2")):
        db = MagicMock()
        db.match_by_id.return_value = {
            "id": 77,
            "team_id": "T1",
            "round_id": 5,
            "member_ids": list(members),
            "agreed_slot_utc": agreed,
        }
        db.slot_votes.return_value = votes if votes is not None else {}
        db.agree_slot.return_value = True
        db.program_for_round.return_value = {"meeting_link": ""}
        return db

    def _run(self, body, db):
        from src.modules.connect.handlers import _accept_slot

        client = MagicMock()
        with patch_modules({"src.modules.connect.db": db}):
            _accept_slot(body, client)
        return client

    def test_one_acceptance_records_and_waits(self):
        db = self._db(votes={SLOT: ["U1"]})
        self._run(self._body("U1"), db)
        db.accept_slot.assert_called_once()
        db.agree_slot.assert_not_called()

    def test_the_other_person_is_told_a_time_is_on_the_table(self):
        # An ephemeral reply would tell the tapper what they already know and
        # leave the other one unaware, so nothing would ever get settled.
        db = self._db(votes={SLOT: ["U1"]})
        client = self._run(self._body("U1"), db)
        assert client.chat_postMessage.called
        sent = client.chat_postMessage.call_args.kwargs
        assert "<@U1>" in sent["text"]
        blocks_text = " ".join(b["text"]["text"] for b in sent["blocks"])
        assert "<@U2>" in blocks_text
        assert "settled" in blocks_text

    def test_the_last_acceptance_settles_it(self):
        db = self._db(votes={SLOT: ["U1", "U2"]})
        client = self._run(self._body("U2"), db)
        db.agree_slot.assert_called_once()
        assert client.chat_postMessage.called
        assert "Settled" in client.chat_postMessage.call_args.kwargs["text"]

    def test_an_already_settled_match_is_not_resettled(self):
        db = self._db(agreed=SLOT)
        client = self._run(self._body("U1"), db)
        db.accept_slot.assert_not_called()
        db.agree_slot.assert_not_called()
        assert client.chat_postEphemeral.called

    def test_a_stranger_cannot_agree_someone_elses_time(self):
        db = self._db(votes={SLOT: ["U1"]})
        self._run(self._body("U_OTHER"), db)
        db.accept_slot.assert_not_called()

    def test_a_simultaneous_final_tap_confirms_once(self):
        # agree_slot is conditional on the match still being unsettled, so the
        # loser of the race posts nothing.
        db = self._db(votes={SLOT: ["U1", "U2"]})
        db.agree_slot.return_value = False
        client = self._run(self._body("U2"), db)
        assert not client.chat_postMessage.called

    def test_an_unparseable_slot_is_ignored_not_crashed(self):
        db = self._db()
        body = self._body()
        body["actions"][0]["value"] = "not-a-time"
        self._run(body, db)
        db.accept_slot.assert_not_called()

    def test_a_missing_match_is_ignored(self):
        db = self._db()
        db.match_by_id.return_value = None
        self._run(self._body(), db)
        db.accept_slot.assert_not_called()


class TestTheButtonIsActuallyWired:
    """A button whose action_id nothing handles is a dead button.

    This module has shipped unreachable work twice: a job registered in the
    wrong function, and scopes declared nowhere but the module itself. The
    action_id here is built from an f-string, so a typo in either the message
    or the handler pattern would be invisible until somebody tapped it.
    """

    def _registered_actions(self):
        registered = []

        class FakeApp:
            def action(self, pattern):
                registered.append(pattern)
                return lambda f: f

            def __getattr__(self, _):
                return lambda *a, **k: lambda f: f

        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / "src/modules/connect/handlers.py"
        spec = importlib.util.spec_from_file_location("connect_handlers_probe", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.register_handlers(FakeApp())
        return registered

    def _handled(self, action_id):
        for p in self._registered_actions():
            if hasattr(p, "match"):
                if p.match(action_id):
                    return True
            elif p == action_id:
                return True
        return False

    def test_the_action_id_the_message_emits_has_a_handler(self):
        _, blocks = cb.intro_message(
            ["U1", "U2"],
            seed=1,
            program_id=1,
            suggested_times=[{"label": "Friday", "utc": SLOT.isoformat(), "add_url": ""}],
            match_id=77,
        )
        emitted = [b["accessory"]["action_id"] for b in blocks if b.get("accessory")]
        assert emitted, "the message produced no accept button at all"
        emitted += [e["action_id"] for b in blocks if b["type"] == "actions" for e in b["elements"]]
        assert "connect:suggest_time:77" in emitted
        for action_id in emitted:
            assert self._handled(action_id), f"nothing handles {action_id}"

    def test_the_calendar_button_on_the_confirmation_has_a_handler(self):
        # A url button still posts an interaction, and an unhandled one logs a
        # Bolt warning on every tap.
        _, blocks = cb.agreed_message(["U1", "U2"], "Friday", "https://cal")
        ids = [e["action_id"] for b in blocks if b["type"] == "actions" for e in b["elements"]]
        for action_id in ids:
            assert self._handled(action_id), f"nothing handles {action_id}"

    def test_the_suggested_time_button_has_a_handler(self):
        # Deliberately the accept_slot handler, not a new one, so a suggested
        # time settles exactly as an offered one does.
        _, blocks = cb.suggested_time_message("U1", "Friday", 77, SLOT.isoformat(), ["U2"])
        action_id = blocks[0]["accessory"]["action_id"]
        assert action_id.startswith("connect:accept_slot:77:")
        assert self._handled(action_id), f"nothing handles {action_id}"


class TestSuggestAnotherTime:
    """The offered slots are a guess from working hours. When none of them
    works, the member needs a way to propose one that the bot can still settle,
    rather than typing a time into the DM where nothing can act on it."""

    def _db(self, agreed=None, votes=None, members=("U1", "U2")):
        db = MagicMock()
        db.match_by_id.return_value = {
            "id": 77,
            "team_id": "T1",
            "round_id": 5,
            "member_ids": list(members),
            "agreed_slot_utc": agreed,
        }
        db.slot_votes.return_value = votes if votes is not None else {}
        db.agree_slot.return_value = True
        db.program_for_round.return_value = {"meeting_link": ""}
        return db

    def _open(self, db, user="U1"):
        from src.modules.connect.handlers import _open_suggest_time

        body = {
            "user": {"id": user},
            "channel": {"id": "D1"},
            "trigger_id": "TRIG",
            "actions": [{"action_id": "connect:suggest_time:77", "value": "77"}],
        }
        client = MagicMock()
        with patch_modules({"src.modules.connect.db": db}):
            _open_suggest_time(body, client)
        return client

    def _submit(self, db, when, user="U1"):
        import json

        from src.modules.connect.handlers import _submit_suggest_time

        picked = {cb.SUGGEST_TIME_ACTION: {"selected_date_time": int(when.timestamp())}}
        view = {
            "private_metadata": json.dumps({"match_id": 77, "channel_id": "D1"}),
            "state": {"values": {cb.SUGGEST_TIME_BLOCK: picked}},
        }
        ack, client = MagicMock(), MagicMock()
        with patch_modules({"src.modules.connect.db": db}):
            _submit_suggest_time(ack, {"user": {"id": user}}, view, client)
        return ack, client

    @staticmethod
    def _future(days=2):
        return (datetime.now(timezone.utc) + timedelta(days=days)).replace(second=0, microsecond=0)

    def test_the_intro_offers_it_under_the_slots(self):
        _, blocks = cb.intro_message(
            ["U1", "U2"],
            seed=1,
            program_id=1,
            suggested_times=[{"label": "Friday", "utc": SLOT.isoformat(), "add_url": ""}],
            match_id=77,
        )
        actions = [b for b in blocks if b["type"] == "actions"]
        assert len(actions) == 1
        button = actions[0]["elements"][0]
        assert button["text"]["text"] == "Suggest another time"
        assert button["action_id"] == "connect:suggest_time:77"
        # It sits after the slots and before the caveat, which is kept.
        idx = blocks.index(actions[0])
        assert blocks[idx - 1].get("accessory", {}).get("action_id", "").startswith("connect:accept_slot:")
        assert blocks[idx + 1]["type"] == "context"

    def test_no_slots_means_no_button(self):
        _, blocks = cb.intro_message(["U1", "U2"], seed=1, program_id=1, match_id=77)
        assert not [b for b in blocks if b["type"] == "actions"]

    def test_a_member_gets_the_picker(self):
        client = self._open(self._db())
        client.views_open.assert_called_once()
        kwargs = client.views_open.call_args.kwargs
        assert kwargs["trigger_id"] == "TRIG"
        view = kwargs["view"]
        assert view["callback_id"] == cb.SUGGEST_TIME_CALLBACK
        assert view["title"]["text"] == "Suggest a time"
        assert view["submit"]["text"] == "Suggest"
        assert view["blocks"][0]["element"]["type"] == "datetimepicker"
        assert '"match_id": 77' in view["private_metadata"]
        assert '"channel_id": "D1"' in view["private_metadata"]

    def test_a_stranger_gets_nothing(self):
        client = self._open(self._db(), user="U_OTHER")
        client.views_open.assert_not_called()

    def test_a_settled_match_says_so_instead_of_opening(self):
        client = self._open(self._db(agreed=SLOT))
        client.views_open.assert_not_called()
        assert "already settled" in client.chat_postEphemeral.call_args.kwargs["text"]

    def test_a_past_time_is_refused_on_the_modal(self):
        db = self._db()
        ack, client = self._submit(db, datetime.now(timezone.utc) - timedelta(hours=1))
        assert ack.call_args.kwargs["response_action"] == "errors"
        assert cb.SUGGEST_TIME_BLOCK in ack.call_args.kwargs["errors"]
        db.accept_slot.assert_not_called()
        client.chat_postMessage.assert_not_called()

    def test_a_time_weeks_away_is_refused(self):
        db = self._db()
        ack, _ = self._submit(db, self._future(days=30))
        assert ack.call_args.kwargs["response_action"] == "errors"
        db.accept_slot.assert_not_called()

    def test_settled_while_the_modal_was_open_is_refused(self):
        db = self._db(agreed=SLOT)
        ack, _ = self._submit(db, self._future())
        assert ack.call_args.kwargs["response_action"] == "errors"
        db.accept_slot.assert_not_called()

    def test_a_stranger_submitting_records_nothing(self):
        db = self._db()
        ack, client = self._submit(db, self._future(), user="U_OTHER")
        ack.assert_called_once_with()
        db.accept_slot.assert_not_called()
        client.chat_postMessage.assert_not_called()

    def test_a_suggestion_counts_as_the_proposers_vote_and_asks_the_rest(self):
        when = self._future()
        db = self._db(votes={when: ["U1"]})
        ack, client = self._submit(db, when)
        ack.assert_called_once_with()
        db.accept_slot.assert_called_once_with(77, "T1", "U1", when)
        db.agree_slot.assert_not_called()
        sent = client.chat_postMessage.call_args.kwargs
        assert sent["channel"] == "D1"
        section = sent["blocks"][0]
        assert section["text"]["text"].startswith("<@U1> suggested *")
        assert "<@U2>" in section["text"]["text"]
        button = section["accessory"]
        assert button["text"]["text"] == "Works for me"
        assert button["action_id"] == f"connect:accept_slot:77:{when.isoformat()}"
        assert button["value"] == when.isoformat()

    def test_the_time_is_rounded_to_the_minute(self):
        when = self._future()
        db = self._db(votes={when: ["U1"]})
        self._submit(db, when + timedelta(seconds=20))
        assert db.accept_slot.call_args.args[3] == when

    def test_a_group_of_three_waits_for_everyone(self):
        when = self._future()
        db = self._db(votes={when: ["U1"]}, members=("U1", "U2", "U3"))
        _, client = self._submit(db, when)
        db.agree_slot.assert_not_called()
        text = client.chat_postMessage.call_args.kwargs["blocks"][0]["text"]["text"]
        assert "<@U2>" in text and "<@U3>" in text

    def test_if_the_others_already_picked_that_time_it_settles_at_once(self):
        when = self._future()
        db = self._db(votes={when: ["U1", "U2"]})
        _, client = self._submit(db, when)
        db.agree_slot.assert_called_once()
        assert "Settled" in client.chat_postMessage.call_args.kwargs["text"]

    def test_the_other_members_tap_settles_through_the_usual_flow(self):
        from src.modules.connect.handlers import _accept_slot

        when = self._future()
        db = self._db(votes={when: ["U1"]})
        _, client = self._submit(db, when)
        button = client.chat_postMessage.call_args.kwargs["blocks"][0]["accessory"]

        db.slot_votes.return_value = {when: ["U1", "U2"]}
        body = {
            "user": {"id": "U2"},
            "channel": {"id": "D1"},
            "actions": [{"action_id": button["action_id"], "value": button["value"]}],
        }
        tap_client = MagicMock()
        with patch_modules({"src.modules.connect.db": db}):
            _accept_slot(body, tap_client)
        db.agree_slot.assert_called_once()
        assert db.agree_slot.call_args.args == (77, when)
        assert "Settled" in tap_client.chat_postMessage.call_args.kwargs["text"]


class TestZoomOnlyForTheAgreedTime:
    """A tap that does not settle the match must not book a Zoom meeting.

    Building the label used to resolve the room, and in Zoom mode that created
    the meeting on the first tap. If the pair then agreed a different time (a
    suggestion, say), the meeting stayed booked for the first one.
    """

    def _run(self, votes, user):
        from src.modules.connect import handlers

        db = TestAcceptSlotHandler()._db(votes=votes)
        db.program_for_round.return_value = {"video_mode": "zoom"}
        zoom_room = MagicMock(return_value="https://zoom.us/j/1")
        client = MagicMock()
        with patch_modules({"src.modules.connect.db": db}), patch.object(handlers, "_zoom_room", zoom_room):
            handlers._accept_slot(TestAcceptSlotHandler()._body(user), client)
        return zoom_room, client

    def test_a_first_tap_books_nothing(self):
        zoom_room, _ = self._run({SLOT: ["U1"]}, "U1")
        zoom_room.assert_not_called()

    def test_the_settling_tap_books_the_agreed_time_once(self):
        zoom_room, client = self._run({SLOT: ["U1", "U2"]}, "U2")
        zoom_room.assert_called_once()
        assert zoom_room.call_args.args[2] == SLOT
        assert "https://zoom.us/j/1" in str(client.chat_postMessage.call_args.kwargs["blocks"])
