"""Daily kudos allowance: when the day resets, and how much is left.

The reset is midnight in the giver's own timezone, not UTC, so someone in
Kolkata and someone in Toronto get a fresh allowance at their own midnight.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.modules.kudos.allowance import day_bounds_utc, remaining


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_utc_day_starts_at_utc_midnight():
    start, end = day_bounds_utc("UTC", utc(2026, 9, 16, 13, 0))
    assert start == utc(2026, 9, 16, 0, 0)
    assert end == utc(2026, 9, 17, 0, 0)


def test_toronto_day_starts_at_local_midnight():
    """Toronto is UTC-4 in September, so its day starts at 04:00 UTC."""
    start, end = day_bounds_utc("America/Toronto", utc(2026, 9, 16, 13, 0))
    assert start == utc(2026, 9, 16, 4, 0)
    assert end == utc(2026, 9, 17, 4, 0)


def test_just_after_toronto_midnight_is_already_the_new_day():
    start, _ = day_bounds_utc("America/Toronto", utc(2026, 9, 16, 4, 1))
    assert start == utc(2026, 9, 16, 4, 0)


def test_just_before_toronto_midnight_is_still_the_old_day():
    start, _ = day_bounds_utc("America/Toronto", utc(2026, 9, 16, 3, 59))
    assert start == utc(2026, 9, 15, 4, 0)


def test_half_hour_offset_zone():
    """Kolkata is UTC+5:30, so its day starts at 18:30 UTC the day before."""
    start, end = day_bounds_utc("Asia/Kolkata", utc(2026, 9, 16, 13, 0))
    assert start == utc(2026, 9, 15, 18, 30)
    assert end == utc(2026, 9, 16, 18, 30)


def test_a_zone_ahead_of_utc_can_already_be_tomorrow():
    """At 22:00 UTC, Auckland is on the next calendar day."""
    start, _ = day_bounds_utc("Pacific/Auckland", utc(2026, 9, 16, 22, 0))
    assert start.astimezone(timezone.utc) == utc(2026, 9, 16, 12, 0)


def test_dst_transition_day_is_still_one_day_long():
    """Toronto leaves DST on 2026-11-01, making that local day 25 hours."""
    start, end = day_bounds_utc("America/Toronto", utc(2026, 11, 1, 12, 0))
    assert (end - start).total_seconds() == 25 * 3600


def test_an_unknown_timezone_falls_back_to_utc():
    """A bad tz string must not stop someone giving kudos."""
    start, end = day_bounds_utc("Mars/Olympus_Mons", utc(2026, 9, 16, 13, 0))
    assert start == utc(2026, 9, 16, 0, 0)


def test_an_empty_timezone_falls_back_to_utc():
    start, _ = day_bounds_utc("", utc(2026, 9, 16, 13, 0))
    assert start == utc(2026, 9, 16, 0, 0)


def test_remaining_counts_down_from_the_allowance():
    assert remaining(5, 0) == 5
    assert remaining(5, 2) == 3
    assert remaining(5, 5) == 0


def test_remaining_never_goes_negative():
    """An admin lowering the allowance must not produce a negative balance."""
    assert remaining(3, 7) == 0


def test_a_zero_allowance_means_giving_is_off():
    assert remaining(0, 0) == 0
