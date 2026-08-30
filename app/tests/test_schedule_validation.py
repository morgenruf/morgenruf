"""Tests for schedule_validation: rejecting schedule timing the scheduler cannot use (#67)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# test_handlers stubs pytz with a MagicMock, which would accept every timezone.
# Drop a leaked stub so this module validates against the real tz database.
if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]

from schedule_validation import (  # noqa: E402
    schedule_config_error,
    schedule_payload_error,
    schedule_time_error,
    schedule_timezone_error,
)


class TestScheduleTimezoneError:
    def test_valid_iana_name_accepted(self):
        assert schedule_timezone_error("Asia/Kolkata") is None
        assert schedule_timezone_error("Europe/London") is None
        assert schedule_timezone_error("UTC") is None

    def test_typo_rejected(self):
        """The reporter's typo: one extra 't' and the standup never fires."""
        error = schedule_timezone_error("Asia/Kolkatta")
        assert error is not None
        assert "Asia/Kolkatta" in error

    def test_offset_style_value_rejected(self):
        assert schedule_timezone_error("GMT+5:30") is not None

    def test_empty_and_non_string_rejected(self):
        assert schedule_timezone_error("") is not None
        assert schedule_timezone_error("   ") is not None
        assert schedule_timezone_error(None) is not None
        assert schedule_timezone_error(330) is not None

    def test_message_names_a_valid_example(self):
        assert "Asia/Kolkata" in schedule_timezone_error("IST")


class TestScheduleTimeError:
    def test_valid_times_accepted(self):
        assert schedule_time_error("09:00") is None
        assert schedule_time_error("9:05") is None
        assert schedule_time_error("23:59") is None

    def test_out_of_range_rejected(self):
        assert schedule_time_error("24:00") is not None
        assert schedule_time_error("09:60") is not None

    def test_wrong_shape_rejected(self):
        assert schedule_time_error("9am") is not None
        assert schedule_time_error("0900") is not None
        assert schedule_time_error("") is not None
        assert schedule_time_error(900) is not None


class TestSchedulePayloadError:
    def test_absent_fields_are_not_checked(self):
        assert schedule_payload_error({"name": "Daily"}) is None

    def test_valid_fields_pass(self):
        assert schedule_payload_error({"schedule_tz": "Asia/Kolkata", "schedule_time": "09:30"}) is None

    def test_bad_timezone_reported(self):
        assert schedule_payload_error({"schedule_tz": "Asia/Kolkatta"}) is not None

    def test_bad_time_reported(self):
        assert schedule_payload_error({"schedule_time": "9am"}) is not None


class TestScheduleConfigError:
    def test_row_the_scheduler_accepts(self):
        assert schedule_config_error({"schedule_time": "10:00", "schedule_tz": "Europe/Amsterdam"}) is None

    def test_missing_fields_fall_back_to_defaults(self):
        assert schedule_config_error({}) is None
        assert schedule_config_error({"schedule_time": None, "schedule_tz": None}) is None

    def test_bad_timezone_row_reported(self):
        assert schedule_config_error({"schedule_time": "10:00", "schedule_tz": "IST"}) is not None
