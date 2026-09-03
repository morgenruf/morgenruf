"""#121 — every IANA timezone must be selectable, and UTC must never be a silent default.

The picker offered 63 curated zones. Anyone whose Slack timezone was one of the
other 370 could not select it, could not search for it, and was quietly
preselected UTC on a required, prefilled field, so submitting untouched looked
like a deliberate choice.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("requests", MagicMock())

if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]
import blocks as blocks_mod  # noqa: E402
import pytz  # noqa: E402

# Real zones absent from the curated list, spread across regions.
UNCURATED = [
    "Asia/Manila",
    "America/Halifax",
    "Europe/Lisbon",
    "America/Indiana/Indianapolis",
    "Asia/Riyadh",
    "Africa/Accra",
    "America/Detroit",
]


def _tz_block(cfg=None):
    modal = blocks_mod.create_standup_modal(cfg, bot_channels=[{"id": "C1", "name": "general"}])
    for block in modal["blocks"]:
        if block.get("block_id") == "timezone":
            return block
    raise AssertionError("no timezone block in the modal")


class TestEveryZoneIsSelectable:
    def test_uncurated_zones_are_findable_by_search(self):
        unfindable = [zone for zone in UNCURATED if not blocks_mod.timezone_search(zone)]
        assert unfindable == []

    def test_search_returns_the_exact_zone_asked_for(self):
        results = blocks_mod.timezone_search("Asia/Manila")
        assert "Asia/Manila" in [opt["value"] for opt in results]

    def test_every_common_zone_can_be_found(self):
        missing = [
            zone for zone in pytz.common_timezones if zone not in [o["value"] for o in blocks_mod.timezone_search(zone)]
        ]
        assert missing == []

    def test_search_never_offers_an_invalid_zone(self):
        for opt in blocks_mod.timezone_search("man"):
            pytz.timezone(opt["value"])

    def test_curated_list_still_backs_an_empty_query(self):
        assert len(blocks_mod.timezone_search("")) >= 63


class TestNoSilentUtcDefault:
    def test_an_uncurated_slack_timezone_is_preselected(self):
        for zone in UNCURATED:
            initial = _tz_block({"timezone": zone})["element"].get("initial_option")
            assert initial, f"{zone} was dropped instead of preselected"
            assert initial["value"] == zone, f"{zone} was replaced with {initial['value']}"

    def test_a_curated_timezone_keeps_its_friendly_label(self):
        initial = _tz_block({"timezone": "Asia/Kolkata"})["element"]["initial_option"]
        assert initial["value"] == "Asia/Kolkata"
        assert "IST" in initial["text"]["text"]

    def test_no_timezone_means_no_preselection(self):
        """A required field with nothing filled in forces a deliberate choice."""
        assert _tz_block()["element"].get("initial_option") is None

    def test_an_unusable_timezone_is_not_preselected(self):
        assert _tz_block({"timezone": "Asia/Kolkatta"})["element"].get("initial_option") is None

    def test_utc_is_still_honoured_when_actually_chosen(self):
        initial = _tz_block({"timezone": "UTC"})["element"]["initial_option"]
        assert initial["value"] == "UTC"

    def test_the_timezone_field_stays_required(self):
        assert _tz_block().get("optional") is not True


TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "../src/templates/dashboard.html")


class TestDashboardPickerOffersEveryZone:
    """#121 — the dashboard dropdown carried the same 63-zone shortlist. It at
    least accepted a fully typed zone, but it could not suggest one, so the
    zones the Slack modal dropped were also the ones it could not offer."""

    def _template(self):
        with open(TEMPLATE_PATH, encoding="utf-8") as fh:
            return fh.read()

    def test_the_zone_list_is_seeded_from_the_browser_tz_database(self):
        markup = self._template()
        assert "supportedValuesOf" in markup, (
            "seed ALL_TIMEZONES from Intl.supportedValuesOf('timeZone') so every zone is suggestable"
        )

    def test_the_curated_labels_are_still_used_where_they_exist(self):
        assert "America/Chicago (CT)" in self._template()
