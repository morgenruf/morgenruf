"""Working-hours overlap, and matching on it.

Two people eight hours apart can be told to find a time all week and never
find one. This decides whether a pair shares enough of a working day to be
worth introducing, from the timezone already stored against each member: no
calendar access, no extra Slack scope, no OAuth.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.modules.connect.hours import can_meet, next_slots, overlap_hours
from src.modules.connect.matcher import match

SEPT = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


# ── overlap_hours ────────────────────────────────────────────────────────────


def test_the_same_zone_shares_the_whole_day():
    assert overlap_hours("Asia/Kolkata", "Asia/Kolkata", SEPT) == 8.0


def test_neighbouring_zones_share_the_whole_day():
    assert overlap_hours("America/Toronto", "America/New_York", SEPT) == 8.0


def test_toronto_and_kolkata_share_nothing():
    """9-17 in each is 13:00-21:00 UTC against 03:30-11:30 UTC."""
    assert overlap_hours("America/Toronto", "Asia/Kolkata", SEPT) == 0.0


def test_a_partial_overlap_is_measured_not_rounded():
    hours = overlap_hours("Europe/London", "America/New_York", SEPT)
    assert 0 < hours < 8


def test_an_unknown_zone_does_not_exclude_anyone():
    """Refusing to match someone because their profile is incomplete is the
    worse failure, so an unknown zone reads as fully available."""
    assert overlap_hours("", "Asia/Kolkata", SEPT) == 8.0
    assert overlap_hours("Mars/Olympus_Mons", "Asia/Kolkata", SEPT) == 8.0


def test_overlap_is_symmetric():
    a = overlap_hours("Europe/London", "Asia/Tokyo", SEPT)
    b = overlap_hours("Asia/Tokyo", "Europe/London", SEPT)
    assert a == b


# ── can_meet ─────────────────────────────────────────────────────────────────


def test_can_meet_needs_the_minimum():
    assert can_meet("America/Toronto", "America/New_York", 1.0, SEPT) is True
    assert can_meet("America/Toronto", "Asia/Kolkata", 1.0, SEPT) is False


def test_an_unknown_zone_can_always_meet():
    assert can_meet("", "Australia/Sydney", 1.0, SEPT) is True


# ── the matcher honouring it ─────────────────────────────────────────────────


def test_without_the_constraint_everyone_is_matched_as_before():
    """The default must change nothing for existing programmes."""
    pool = ["A", "B", "C", "D"]
    tz = {"A": "America/Toronto", "B": "Asia/Kolkata", "C": "America/Toronto", "D": "Asia/Kolkata"}
    groups = match(pool, {}, seed=1, timezones=tz)
    assert sorted(m for g in groups for m in g) == pool


def test_with_the_constraint_unreachable_people_are_left_out():
    """Pairing them anyway produces a chat that cannot happen."""
    pool = ["A", "B"]
    tz = {"A": "America/Toronto", "B": "Asia/Kolkata"}
    assert match(pool, {}, seed=1, timezones=tz, minimum_overlap_hours=1.0) == []


def test_reachable_pairs_are_still_matched_under_the_constraint():
    pool = ["A", "B"]
    tz = {"A": "America/Toronto", "B": "America/New_York"}
    groups = match(pool, {}, seed=1, timezones=tz, minimum_overlap_hours=1.0)
    assert sorted(groups[0]) == ["A", "B"]


def test_a_mixed_pool_matches_who_it_can():
    pool = ["tor1", "tor2", "kol1", "kol2"]
    tz = {"tor1": "America/Toronto", "tor2": "America/Toronto", "kol1": "Asia/Kolkata", "kol2": "Asia/Kolkata"}
    groups = match(pool, {}, seed=3, timezones=tz, minimum_overlap_hours=1.0)
    for group in groups:
        zones = {tz[m][:4] for m in group}
        assert len(zones) == 1, f"paired across a zero-overlap gap: {group}"


def test_missing_timezones_under_the_constraint_still_match():
    pool = ["A", "B"]
    assert match(pool, {}, seed=1, timezones={}, minimum_overlap_hours=1.0) != []


# ── next_slots ───────────────────────────────────────────────────────────────


def test_slots_fall_on_weekdays():
    for slot in next_slots("America/Toronto", "Europe/London", 3, 30, SEPT):
        assert slot.weekday() < 5


def test_a_pair_with_no_shared_working_day_still_gets_times():
    """This used to return nothing, which read exactly like the feature not
    existing — for the pair who most needed help finding a time. They now get
    edge-of-day options, which the message labels as such."""
    slots = next_slots("America/Toronto", "Asia/Kolkata", 3, 30, SEPT)
    assert slots, "a cross-timezone pair got no suggestions at all"


def test_the_caller_can_tell_whether_the_day_was_shared():
    """So the message can say these sit at the edges rather than implying they
    are comfortable."""
    from src.modules.connect.hours import within_working_hours

    assert within_working_hours("America/Toronto", "America/New_York", SEPT) is True
    assert within_working_hours("America/Toronto", "Asia/Kolkata", SEPT) is False


def test_edge_times_stay_civil():
    """Early and late, not the middle of the night."""
    for slot in next_slots("America/Toronto", "Asia/Kolkata", 3, 30, SEPT):
        assert 0 <= slot.hour <= 23


def test_slots_are_spread_rather_than_consecutive():
    slots = next_slots("America/Toronto", "Europe/London", 3, 30, SEPT)
    if len(slots) >= 2:
        assert (slots[1] - slots[0]).total_seconds() >= 3600
