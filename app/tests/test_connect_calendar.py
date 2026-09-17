"""Turning a proposed time into something a calendar accepts.

This is the half of calendar integration that needs no OAuth: a link that opens
the reader's own calendar with the event filled in. They press save, which is
also the honest arrangement, because without calendar access we never knew
whether they were free.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from src.modules.connect.calendar import google_link, ics, outlook_link

WHEN = datetime(2026, 9, 18, 14, 0, tzinfo=timezone.utc)


def _params(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# ── google ───────────────────────────────────────────────────────────────────


def test_the_google_link_carries_start_and_end():
    p = _params(google_link(WHEN, 30, "Coffee chat"))
    assert p["dates"] == "20260918T140000Z/20260918T143000Z"


def test_the_duration_is_respected():
    assert _params(google_link(WHEN, 45, "x"))["dates"].endswith("T144500Z")
    assert _params(google_link(WHEN, 60, "x"))["dates"].endswith("T150000Z")


def test_the_separator_stays_literal():
    """Google documents the range as start/end; an encoded slash is fragile."""
    assert "/" in google_link(WHEN, 30, "x").split("dates=")[1].split("&")[0]


def test_a_naive_time_is_treated_as_utc_not_local():
    """A reader's zone must not shift the event."""
    naive = datetime(2026, 9, 18, 14, 0)
    assert _params(google_link(naive, 30, "x"))["dates"].startswith("20260918T140000Z")


def test_a_zoned_time_is_converted_rather_than_relabelled():
    from zoneinfo import ZoneInfo

    ist = WHEN.astimezone(ZoneInfo("Asia/Kolkata"))
    assert _params(google_link(ist, 30, "x"))["dates"] == "20260918T140000Z/20260918T143000Z"


def test_the_room_travels_as_the_location():
    p = _params(google_link(WHEN, 30, "Coffee chat", "hello", "https://meet.example/r"))
    assert p["location"] == "https://meet.example/r"


def test_a_zero_length_meeting_still_produces_a_valid_range():
    p = _params(google_link(WHEN, 0, "x"))
    start, end = p["dates"].split("/")
    assert end > start


# ── outlook ──────────────────────────────────────────────────────────────────


def test_the_outlook_link_carries_both_ends():
    p = _params(outlook_link(WHEN, 30, "Coffee chat"))
    assert p["startdt"] == "2026-09-18T14:00:00Z"
    assert p["enddt"] == "2026-09-18T14:30:00Z"


# ── ics ──────────────────────────────────────────────────────────────────────


def test_the_ics_is_a_single_complete_event():
    body = ics(WHEN, 30, "Coffee chat")
    assert body.startswith("BEGIN:VCALENDAR")
    assert body.rstrip().endswith("END:VCALENDAR")
    assert body.count("BEGIN:VEVENT") == 1


def test_ics_lines_end_the_way_the_format_requires():
    assert "\r\n" in ics(WHEN, 30, "x")


def test_separators_in_the_title_are_escaped():
    """A comma or semicolon would otherwise end the field early."""
    line = next(ln for ln in ics(WHEN, 30, "A; B, C").split("\r\n") if ln.startswith("SUMMARY"))
    assert line == "SUMMARY:A" + chr(92) + "; B" + chr(92) + ", C"


def test_a_newline_in_the_description_does_not_break_the_file():
    line = next(ln for ln in ics(WHEN, 30, "x", "one\ntwo").split("\r\n") if ln.startswith("DESCRIPTION"))
    assert line == "DESCRIPTION:one\\ntwo"


def test_the_end_follows_the_duration():
    body = ics(WHEN, 45, "x")
    assert "DTEND:20260918T144500Z" in body


def test_an_explicit_uid_is_used_so_a_resend_updates_rather_than_duplicates():
    assert "UID:round-7-match-3@morgenruf" in ics(WHEN, 30, "x", uid="round-7-match-3")


def test_the_duration_never_produces_an_end_before_the_start():
    for minutes in (-10, 0, 1):
        body = ics(WHEN, minutes, "x")
        start = next(ln for ln in body.split("\r\n") if ln.startswith("DTSTART")).split(":")[1]
        end = next(ln for ln in body.split("\r\n") if ln.startswith("DTEND")).split(":")[1]
        assert end > start, minutes


def test_a_long_meeting_crosses_midnight_correctly():
    late = datetime(2026, 9, 18, 23, 30, tzinfo=timezone.utc)
    body = ics(late, 60, "x")
    assert "DTEND:20260919T003000Z" in body
    assert late + timedelta(minutes=60) == datetime(2026, 9, 19, 0, 30, tzinfo=timezone.utc)
