"""Two settings that saved and did nothing, and one column with no feature.

video_mode was written by the settings page and read by nothing: a programme
set to Zoom or to "they sort it out" still had its shared meeting_link pasted
into every introduction. next_round_date had no way to be set at all, and
include_guests was never read anywhere.
"""

from __future__ import annotations

import pathlib
from datetime import date
from unittest.mock import MagicMock

from src.modules.connect.rounds import is_round_due
from tests.support import patch_modules

CONNECT = pathlib.Path(__file__).resolve().parent.parent / "src/modules/connect"


class TestVideoModeChangesBehaviour:
    def _program(self, mode, link="https://meet.example/abc"):
        return {"id": 1, "channel_id": "C1", "video_mode": mode, "meeting_link": link, "meeting_minutes": 30}

    def _room_for(self, mode, zoom_url="https://zoom.us/j/1"):
        from src.modules.connect import handlers

        db = MagicMock()
        db.program_for_round.return_value = self._program(mode)
        match = {"id": 5, "team_id": "T1", "round_id": 3, "member_ids": ["U1", "U2"], "zoom_join_url": zoom_url}
        with patch_modules({"src.modules.connect.db": db}):
            # zoom_join_url already set, so no Zoom call is made.
            return handlers._room_for(match, ["U1", "U2"], date.today())

    def test_a_shared_room_is_used_when_that_is_the_choice(self):
        assert self._room_for("link") == "https://meet.example/abc"

    def test_zoom_mode_does_not_fall_back_to_the_shared_link(self):
        # A silent substitution would hide that the Zoom side is not working.
        assert self._room_for("zoom") == "https://zoom.us/j/1"

    def test_none_means_no_room_at_all(self):
        assert self._room_for("none") == ""

    def test_delivery_drops_the_link_unless_it_was_chosen(self):
        src = (CONNECT / "jobs.py").read_text()
        assert 'meeting_link = (program.get("meeting_link") or "") if video_mode == "link" else ""' in src

    def test_the_zoom_prompt_is_only_offered_in_zoom_mode(self):
        # Offering it otherwise upsells a workspace on something it declined.
        src = (CONNECT / "jobs.py").read_text()
        assert 'if video_mode == "zoom":' in src

    def test_the_calendar_link_points_at_the_same_room_as_the_message(self):
        src = (CONNECT / "handlers.py").read_text()
        assert "_room_for(match, members, slot)" in src

    def test_the_old_helper_is_gone_rather_than_left_uncalled(self):
        src = (CONNECT / "handlers.py").read_text()
        assert "def _room(match" not in src


class TestPinnedNextRound:
    def test_without_a_pin_the_cadence_decides(self):
        assert is_round_due(1, date(2026, 9, 1), date(2026, 9, 8)) is True
        assert is_round_due(2, date(2026, 9, 1), date(2026, 9, 8)) is False

    def test_a_future_pin_holds_the_round_back_even_when_due(self):
        # The cadence says yes; the admin said later.
        assert is_round_due(1, date(2026, 9, 1), date(2026, 9, 8), pinned=date(2026, 9, 20)) is False

    def test_a_reached_pin_releases_the_round_even_when_not_due(self):
        assert is_round_due(8, date(2026, 9, 1), date(2026, 9, 8), pinned=date(2026, 9, 8)) is True

    def test_a_spent_pin_falls_back_to_the_cadence(self):
        # The pinned round already ran, so the pin must not hold everything
        # afterwards to the same date.
        assert is_round_due(1, date(2026, 9, 20), date(2026, 9, 28), pinned=date(2026, 9, 20)) is True

    def test_a_programme_that_never_ran_still_respects_a_pin(self):
        assert is_round_due(1, None, date(2026, 9, 1), pinned=date(2026, 9, 10)) is False
        assert is_round_due(1, None, date(2026, 9, 10), pinned=date(2026, 9, 10)) is True

    def test_the_pin_is_cleared_once_the_round_runs(self):
        src = (CONNECT / "jobs.py").read_text()
        assert "next_round_date=None" in src

    def test_it_can_be_set_and_read_from_the_page(self):
        markup = (CONNECT.parent.parent / "core/templates/dashboard.html").read_text()
        assert 'id="cs-next-date"' in markup
        assert "next_round_date:" in markup
        api = (CONNECT / "dashboard.py").read_text()
        assert 'p["next_round_date"]' in api


class TestIncludeGuestsIsGone:
    """It had no feature behind it and needed roster data we do not collect."""

    def test_the_column_is_dropped(self):
        sql = (CONNECT / "migrations/046_drop_include_guests.sql").read_text()
        assert "DROP COLUMN IF EXISTS include_guests" in sql

    def test_and_removed_from_the_write_allowlist(self):
        assert "include_guests" not in (CONNECT / "db.py").read_text()
