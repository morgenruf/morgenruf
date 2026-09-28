"""Member profile: what a person says about themselves.

Core rather than a module, because Intros, Onboarding buddies and
Celebrations all read it and none of them owns it. This file holds the parts
with no I/O (parsing, formatting, planning a CSV import), so they can be
tested without a database or Slack. Writes go through
db.upsert_member_profile; the Slack surface is in profile_slack.py.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Slack member ids: U for users, W for Enterprise Grid org users. Underscores
# are not in real ids but are harmless, and the test fixtures use them.
USER_ID_RE = re.compile(r"^[UW][A-Z0-9_]{2,}$")

# An admin exporting from an HR tool is the expected source. Five thousand
# rows is far beyond any workspace we run, and keeps one request bounded.
MAX_IMPORT_ROWS = 5000

_MONTH_DAY = re.compile(r"^(\d{1,2})-(\d{1,2})$")
_FULL_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def is_user_id(value: str) -> bool:
    return bool(USER_ID_RE.match(value or ""))


def set_by_admin(row: dict | None) -> bool:
    """Whether someone other than the person wrote this profile last."""
    if not row:
        return False
    return bool(row.get("updated_by")) and row.get("updated_by") != row.get("user_id")


def to_record(user_id: str, row: dict | None) -> dict:
    """The API shape of a profile, with defaults for someone who has none yet."""
    row = row or {}
    return {
        "user_id": user_id,
        "birth_month": row.get("birth_month"),
        "birth_day": row.get("birth_day"),
        "start_date": row.get("start_date"),
        "role": row.get("role"),
        "location": row.get("location"),
        "ask_me_about": row.get("ask_me_about"),
        "celebrate": bool(row.get("celebrate", True)),
        "updated_by": row.get("updated_by"),
        "updated_at": row.get("updated_at"),
        "set_by_admin": set_by_admin(row),
        "left_at": row.get("left_at"),
    }


def birthday_label(month: int | None, day: int | None) -> str:
    """The birthday as "14 March", or "" when none is set."""
    if not month or not day:
        return ""
    return f"{day} {MONTHS[month - 1]}"


def joined_label(start: date | None) -> str:
    """The start date as "Joined Mar 2023", or "" when none is set."""
    if not start:
        return ""
    return f"Joined {MONTHS[start.month - 1][:3]} {start.year}"


def is_empty(row: dict | None) -> bool:
    """True when nothing a person would recognise as their profile is set."""
    if not row:
        return True
    return not any(row.get(k) for k in ("birth_month", "start_date", "role", "location", "ask_me_about"))


# ── CSV import ──────────────────────────────────────────────────────────────


class ImportFormatError(ValueError):
    """The file as a whole cannot be read, as opposed to one bad row."""


def parse_birthday(text: str) -> tuple[int, int]:
    """Month and day from `MM-DD` or a full `YYYY-MM-DD` date.

    The year of a full date is read only to check the day exists, then
    dropped. It is never returned, so it cannot be stored. 29 February is
    accepted either way.
    """
    raw = (text or "").strip()
    match = _MONTH_DAY.match(raw)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        year = 2000  # a leap year, so 29 February passes
    else:
        match = _FULL_DATE.match(raw)
        if not match:
            raise ValueError(f"Birthday {raw!r} is not MM-DD or YYYY-MM-DD.")
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        date(year, month, day)
    except ValueError:
        raise ValueError(f"Birthday {raw!r} is not a real date.") from None
    return month, day


def parse_start_date(text: str) -> date:
    raw = (text or "").strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"Start date {raw!r} is not YYYY-MM-DD.") from None


def read_import(csv_text: str) -> list[dict]:
    """Rows of `email,birthday,start_date`, each parsed or carrying its error.

    Header names are matched case-insensitively and in any order; extra
    columns are ignored so an HR export can be pasted as it comes. A blank
    cell means "leave this field alone", never "clear it".
    """
    text = (csv_text or "").lstrip("﻿")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportFormatError("The file is empty.") from None
    except csv.Error as exc:
        raise ImportFormatError(f"The file is not valid CSV: {exc}") from None

    columns = {name.strip().lower(): i for i, name in enumerate(header)}
    if "email" not in columns:
        raise ImportFormatError("The first row must name the columns: email,birthday,start_date.")
    if "birthday" not in columns and "start_date" not in columns:
        raise ImportFormatError("Add a birthday column, a start_date column, or both.")

    def cell(values: list[str], name: str) -> str:
        i = columns.get(name)
        return values[i].strip() if i is not None and i < len(values) else ""

    rows: list[dict] = []
    seen: dict[str, int] = {}
    try:
        for values in reader:
            if not any(v.strip() for v in values):
                continue
            if len(rows) >= MAX_IMPORT_ROWS:
                raise ImportFormatError(
                    f"The file has more than {MAX_IMPORT_ROWS} rows. Split it and import each part."
                )
            line = reader.line_num
            email = cell(values, "email").lower()
            row = {
                "line": line,
                "email": email,
                "birth_month": None,
                "birth_day": None,
                "start_date": None,
                "error": None,
            }
            rows.append(row)
            if not email or "@" not in email:
                row["error"] = "Missing or invalid email."
                continue
            if email in seen:
                row["error"] = f"This email is also on line {seen[email]}."
                continue
            seen[email] = line
            try:
                birthday = cell(values, "birthday")
                if birthday:
                    row["birth_month"], row["birth_day"] = parse_birthday(birthday)
                start = cell(values, "start_date")
                if start:
                    row["start_date"] = parse_start_date(start)
            except ValueError as exc:
                row["error"] = str(exc)
                continue
            if row["birth_month"] is None and row["start_date"] is None:
                row["error"] = "Neither a birthday nor a start date."
    except csv.Error as exc:
        raise ImportFormatError(f"The file is not valid CSV: {exc}") from None
    return rows


def plan_import(rows: list[dict], members: list[dict], profiles: dict[str, dict], overwrite: bool) -> list[dict]:
    """Decide what happens to each row, without writing anything.

    `members` are the workspace's active members (user_id, email), and
    `profiles` the existing profiles by user id. Each row gets a status:

    - ready: will be written
    - unchanged: the profile already holds these values
    - kept: the person set their own profile, and overwrite is off
    - unmatched: no active member has this email
    - invalid: the row itself is wrong; `error` says how

    A profile the person wrote themselves (updated_by is their own id) is
    left whole unless the admin ticks overwrite, including fields they left
    empty. Filling in around someone's own entries would mark the row as set
    by an admin, and the next import would then overwrite what they typed.
    """
    by_email: dict[str, str] = {}
    for m in members:
        email = (m.get("email") or "").strip().lower()
        if email and m.get("user_id"):
            by_email.setdefault(email, m["user_id"])

    planned: list[dict] = []
    for row in rows:
        out = {**row, "user_id": None, "status": "invalid"}
        planned.append(out)
        if row.get("error"):
            continue
        user_id = by_email.get(row["email"])
        if not user_id:
            out["status"] = "unmatched"
            out["error"] = "No active member has this email."
            continue
        out["user_id"] = user_id
        existing = profiles.get(user_id)
        if existing and existing.get("updated_by") == user_id and not overwrite:
            out["status"] = "kept"
            out["error"] = "Set by the member. Tick overwrite to replace it."
            continue
        if existing and _same_dates(existing, row):
            out["status"] = "unchanged"
            continue
        out["status"] = "ready"
    return planned


def _same_dates(existing: dict, row: dict) -> bool:
    if row.get("birth_month") is not None and (
        existing.get("birth_month") != row["birth_month"] or existing.get("birth_day") != row["birth_day"]
    ):
        return False
    if row.get("start_date") is not None and existing.get("start_date") != row["start_date"]:
        return False
    return True


def import_fields(row: dict) -> dict:
    """What an import row writes: only the date fields it actually carries."""
    fields: dict = {}
    if row.get("birth_month") is not None:
        fields["birth_month"] = row["birth_month"]
        fields["birth_day"] = row["birth_day"]
    if row.get("start_date") is not None:
        fields["start_date"] = row["start_date"].isoformat()
    return fields


def summarise_import(planned: list[dict], preview: bool, overwrite: bool, written: int) -> dict:
    counts = {s: 0 for s in ("ready", "unchanged", "kept", "unmatched", "invalid")}
    for row in planned:
        counts[row["status"]] += 1
    return {
        "preview": preview,
        "overwrite": overwrite,
        "rows_read": len(planned),
        **counts,
        "written": written,
        "rows": [
            {
                "line": r["line"],
                "email": r["email"],
                "user_id": r.get("user_id"),
                "status": r["status"],
                "birth_month": r.get("birth_month"),
                "birth_day": r.get("birth_day"),
                "start_date": r.get("start_date"),
                "error": r.get("error"),
            }
            for r in planned
        ],
    }
