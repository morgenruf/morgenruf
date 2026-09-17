"""Turning a proposed time into something a calendar will accept.

This is the half of calendar integration that needs no OAuth: a link that
opens the person's own calendar with the event already filled in. They still
press save, which also means we never claim to know whether they are free.

Free/busy lookup and creating the event on someone's behalf need per-user
OAuth and, for Google, a verified app. That is a separate piece of work; this
one is useful on its own and works for every user from the moment it ships.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

# Slack renders a link label, so keep these short enough to sit on one line.
GOOGLE_BASE = "https://calendar.google.com/calendar/render"
OUTLOOK_BASE = "https://outlook.office.com/calendar/0/deeplink/compose"


def _utc(when: datetime) -> datetime:
    """Everything is emitted in UTC, so a reader's zone cannot shift the event."""
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _google_stamp(when: datetime) -> str:
    return _utc(when).strftime("%Y%m%dT%H%M%SZ")


def google_link(start: datetime, minutes: int, title: str, details: str = "", location: str = "") -> str:
    """A Google Calendar event with the fields already filled in."""
    start_utc = _utc(start)
    end_utc = start_utc + timedelta(minutes=max(1, minutes))
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{_google_stamp(start_utc)}/{_google_stamp(end_utc)}",
    }
    if details:
        params["details"] = details
    if location:
        params["location"] = location
    # safe="/" keeps the start/end separator literal, as Google documents it.
    return f"{GOOGLE_BASE}?{urlencode(params, quote_via=lambda v, *_: quote(v, safe=chr(47)))}"


def outlook_link(start: datetime, minutes: int, title: str, details: str = "", location: str = "") -> str:
    """The same for Outlook on the web."""
    start_utc = _utc(start)
    end_utc = start_utc + timedelta(minutes=max(1, minutes))
    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": title,
        "startdt": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enddt": end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if details:
        params["body"] = details
    if location:
        params["location"] = location
    return f"{OUTLOOK_BASE}?{urlencode(params, quote_via=quote)}"


def _ics_escape(value: str) -> str:
    """Commas, semicolons and newlines are field separators in iCalendar."""
    out = value.replace(chr(92), chr(92) * 2)
    out = out.replace(";", chr(92) + ";")
    out = out.replace(",", chr(92) + ",")
    return out.replace("\n", chr(92) + "n")


def ics(start: datetime, minutes: int, title: str, details: str = "", location: str = "", uid: str = "") -> str:
    """A minimal VEVENT, for a client that takes a file rather than a link."""
    start_utc = _utc(start)
    end_utc = start_utc + timedelta(minutes=max(1, minutes))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Morgenruf//Coffee chats//EN",
        "BEGIN:VEVENT",
        f"UID:{uid or stamp}@morgenruf",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{_ics_escape(title)}",
    ]
    if details:
        lines.append(f"DESCRIPTION:{_ics_escape(details)}")
    if location:
        lines.append(f"LOCATION:{_ics_escape(location)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines)
