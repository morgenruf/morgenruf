"""Agreeing a time, which is the step that otherwise does not happen.

Donut introduces two people and leaves them to negotiate. Both are willing and
neither wants to be the one who picks, so the introduction dies in the DM. One
tap per acceptable time lets the bot settle it as soon as everyone has accepted
the same one, with no calendar access and no OAuth.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

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

    def test_each_time_gets_its_own_button(self):
        _, blocks = self._msg()
        buttons = [b["accessory"] for b in blocks if b.get("accessory")]
        assert len(buttons) == 2
        assert all(b["text"]["text"] == "Works for me" for b in buttons)

    def test_the_button_carries_the_match_and_the_slot(self):
        _, blocks = self._msg()
        acc = next(b["accessory"] for b in blocks if b.get("accessory"))
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
        for action_id in emitted:
            assert self._handled(action_id), f"nothing handles {action_id}"

    def test_the_calendar_button_on_the_confirmation_has_a_handler(self):
        # A url button still posts an interaction, and an unhandled one logs a
        # Bolt warning on every tap.
        _, blocks = cb.agreed_message(["U1", "U2"], "Friday", "https://cal")
        ids = [e["action_id"] for b in blocks if b["type"] == "actions" for e in b["elements"]]
        for action_id in ids:
            assert self._handled(action_id), f"nothing handles {action_id}"
