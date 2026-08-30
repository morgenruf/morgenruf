"""The Standups card and the Analytics card must report the same rate (#85).

They disagreed on the live dashboard, 27 percent against 31 percent, for the
same seven day window. `get_dashboard_stats` was already delegating to the
participation overview; the Analytics figure was computed in the browser as an
unweighted mean of per-member ratios, which is a different statistic.

These tests pin the arithmetic on the server side and prove the two entry
points agree on identical input.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

for _name in ("psycopg2", "psycopg2.extras"):
    sys.modules.setdefault(_name, MagicMock())

import db  # noqa: E402


def _workspace():
    """One member expected 10 times, five members expected once each.

    Chosen because the mean of per-member ratios and the aggregate rate differ
    sharply here, which is exactly the shape that produced the live mismatch.
    """
    heavy = ["U_heavy"]
    light = [f"U_light{i}" for i in range(5)]
    schedules = [
        {
            "id": 1,
            "team_id": "T",
            "name": "Daily",
            "schedule_days": "mon,tue,wed,thu,fri",
            "schedule_tz": "UTC",
            "schedule_time": "09:00",
            "participants": heavy,
            "active": True,
        },
        {
            "id": 2,
            "team_id": "T",
            "name": "Second daily",
            "schedule_days": "mon,tue,wed,thu,fri",
            "schedule_tz": "UTC",
            "schedule_time": "18:00",
            "participants": heavy,
            "active": True,
        },
        {
            "id": 3,
            "team_id": "T",
            "name": "Mondays",
            "schedule_days": "mon",
            "schedule_tz": "UTC",
            "schedule_time": "09:00",
            "participants": light,
            "active": True,
        },
    ]
    members = [{"user_id": u, "real_name": u, "active": True, "on_vacation": False} for u in heavy + light]
    days = [dt.date(2026, 3, 9) + dt.timedelta(d) for d in range(5)]
    submissions = []
    # The heavy member answers on 1 of 5 days, so 2 of 10 occurrences.
    submissions.append({"user_id": "U_heavy", "standup_date": days[0]})
    submissions.append({"user_id": "U_heavy", "standup_date": days[0]})
    # Every light member answers their single Monday occurrence.
    for u in light:
        submissions.append({"user_id": u, "standup_date": days[0]})
    return schedules, members, submissions, dt.datetime(2026, 3, 13, 23, 0, tzinfo=dt.timezone.utc)


class TestAggregateNotMeanOfRatios:
    def test_hand_computed_aggregate(self):
        schedules, members, submissions, now = _workspace()
        result = db.compute_participation(schedules, members, submissions, days=5, now=now)
        # expected: heavy 10, light 5 x 1 = 15. completed: 2 + 5 = 7.
        assert result["expected"] == 15
        assert result["completed"] == 7
        assert result["completion_rate"] == round(7 / 15 * 100)  # 47

    def test_mean_of_ratios_would_have_said_something_else(self):
        """Documents the bug this replaces, so nobody reintroduces the average."""
        schedules, members, submissions, now = _workspace()
        result = db.compute_participation(schedules, members, submissions, days=5, now=now)
        enrolled = [m for m in result["members"] if m["enrolled"]]
        mean_of_ratios = round(sum(m["completed"] / m["expected"] for m in enrolled) / len(enrolled) * 100)
        assert mean_of_ratios == 87  # five members at 100 percent, one at 20
        assert result["completion_rate"] == 47
        assert mean_of_ratios != result["completion_rate"]


class TestBothCardsAgree:
    def test_dashboard_stats_matches_the_overview(self, monkeypatch):
        schedules, members, submissions, now = _workspace()
        monkeypatch.setattr(db, "_fetch_participation_inputs", lambda team_id, days: (schedules, members, submissions))
        monkeypatch.setattr(db, "_utc_now", lambda: now)

        overview = db.get_participation_overview("T", days=5)
        stats = db.get_dashboard_stats("T")

        # The Standups card and the Analytics card read from these two.
        assert stats["completion_rate"] == overview["completion_rate"]
        assert stats["expected_responses"] == overview["expected"]
        assert stats["completed_responses"] == overview["completed"]
        assert stats["enrolled_members"] == overview["enrolled_members"]

    def test_overview_exposes_what_the_headline_needs(self, monkeypatch):
        schedules, members, submissions, now = _workspace()
        monkeypatch.setattr(db, "_fetch_participation_inputs", lambda team_id, days: (schedules, members, submissions))
        monkeypatch.setattr(db, "_utc_now", lambda: now)

        overview = db.get_participation_overview("T", days=5)
        for key in ("completion_rate", "expected", "completed", "enrolled_members", "schedules", "members"):
            assert key in overview, key
        # Per-schedule totals must sum to the workspace numerator, so a filtered
        # headline is aggregated the same way as the unfiltered one.
        assert sum(s["completed"] for s in overview["schedules"]) == overview["completed"]
        assert sum(s["expected"] for s in overview["schedules"]) == overview["expected"]
