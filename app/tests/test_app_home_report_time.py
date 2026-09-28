"""App Home must say when the channel report posts, not when the DMs go out.

A standup created from the Slack "Create a standup" modal with a 09:00 standup
time, a 10:00 report time and America/New_York read "Reports at 09:00 today".
Both App Home builders filled the card's `report_time` from `schedule_time`,
so the report time the creator picked was never shown.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

from tests.support import patch_modules

sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("requests", MagicMock())

if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]

_prior_session_store = sys.modules.get("src.core.session_store")
_ss_mock = MagicMock()
_ss_mock.get_session.return_value = None
_ss_mock.has_session.return_value = False
sys.modules["src.core.session_store"] = _ss_mock

import src.modules.standup.blocks as blocks  # noqa: E402
import src.modules.standup.handlers as handlers  # noqa: E402

if _prior_session_store is not None:
    sys.modules["src.core.session_store"] = _prior_session_store
else:
    sys.modules.pop("src.core.session_store", None)


def _schedule(**overrides):
    row = {
        "id": 41,
        "team_id": "T1",
        "name": "Morning sync",
        "channel_id": "C1",
        "schedule_time": "09:00",
        "report_time": "10:00",
        "schedule_tz": "America/New_York",
        "schedule_days": "mon,tue,wed,thu,fri",
        "participants": ["U1"],
        "questions": ["What did you do?"],
        "active": True,
    }
    row.update(overrides)
    return row


def _section_text(view):
    return "\n".join(b.get("text", {}).get("text", "") for b in view["blocks"] if b.get("type") == "section")


def _handlers():
    captured: dict = {}

    def event(name):
        def decorator(fn):
            captured[name] = fn
            return fn

        return decorator

    app = MagicMock()
    app.event.side_effect = event
    handlers.register_handlers(app)
    return captured


def _open_home(schedule, user_tz="America/New_York"):
    db = MagicMock()
    db.is_on_vacation.return_value = False
    db.get_standup_streak.return_value = 0
    db.get_today_standups.return_value = []
    db.get_standup_schedules.return_value = [schedule]
    client = MagicMock()
    client.users_info.return_value = {"user": {"tz": user_tz, "is_admin": False}}
    client.team_info.return_value = {"team": {"name": "Acme"}}
    with patch_modules({"src.core.db": db}):
        _handlers()["app_home_opened"]({"user": "U1", "view": {"team_id": "T1"}}, client)
    return _section_text(client.views_publish.call_args.kwargs["view"])


class TestReportTimeHelper:
    def test_an_explicit_report_time_wins(self):
        assert handlers._report_time(_schedule()) == "10:00"

    def test_without_one_it_is_an_hour_after_the_standup_like_the_scheduler(self):
        assert handlers._report_time(_schedule(report_time=None)) == "10:00"
        assert handlers._report_time(_schedule(schedule_time="23:30", report_time="")) == "00:30"


class TestAppHomeCard:
    def test_the_card_shows_the_report_time_not_the_standup_time(self):
        text = _open_home(_schedule())
        assert "Reports at 10:00 today." in text
        assert "Reports at 09:00" not in text

    def test_a_schedule_with_no_report_time_shows_the_default(self):
        text = _open_home(_schedule(report_time=None))
        assert "Reports at 10:00 today." in text

    def test_the_timezone_is_named_when_the_reader_is_elsewhere(self):
        text = _open_home(_schedule(), user_tz="Europe/Berlin")
        assert "Reports at 10:00 (America/New_York) today." in text

    def test_a_row_passed_straight_through_does_not_fall_back_to_the_standup_time(self):
        view = blocks.app_home_view([_schedule(report_time=None)], user_id="U1", user_tz="America/New_York")
        assert "Reports at 10:00 today." in _section_text(view)


class TestConfigureView:
    def test_the_schedule_line_still_shows_when_the_standup_runs(self):
        standups = [
            {
                "standup_id": "41",
                "standup_name": "Morning sync",
                "channel_id": "C1",
                "standup_time": "09:00",
                "report_time": "10:00",
                "timezone": "America/New_York",
                "days": ["mon", "tue", "wed", "thu", "fri"],
                "members": ["U1"],
                "active": True,
                "questions": [],
            }
        ]
        text = _section_text(blocks.app_home_configure_view(standups, user_id="U1"))
        assert "Weekdays @ 09:00 (America/New_York)" in text
