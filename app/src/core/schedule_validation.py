"""Validation for the timing fields of a standup schedule.

`scheduler.register_schedule_job` parses `schedule_time` and resolves
`schedule_tz` through pytz. When either value is unusable it logs the problem
and gives up, so the cron job is never registered while the dashboard keeps
reporting the schedule as Active (issue #67). These helpers let the API reject
such a row before it is persisted, and let any process ask why a stored row
cannot be registered.
"""

from __future__ import annotations

import re

import pytz

# 24-hour "HH:MM", the shape register_schedule_job splits on.
_TIME_RE = re.compile(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$")

_TZ_HINT = "Use an IANA timezone name such as Asia/Kolkata, Europe/London or America/New_York."
_TIME_HINT = "Use a 24-hour HH:MM time such as 09:30."


def schedule_timezone_error(value: object) -> str | None:
    """Return why `value` is unusable as a schedule timezone, or None if it is fine."""
    if not isinstance(value, str) or not value.strip():
        return f"Timezone is required. {_TZ_HINT}"
    try:
        pytz.timezone(value.strip())
    except Exception:
        return f"'{value}' is not a valid timezone. {_TZ_HINT}"
    return None


def schedule_time_error(value: object) -> str | None:
    """Return why `value` is unusable as a schedule time, or None if it is fine."""
    if not isinstance(value, str) or not value.strip():
        return f"Time is required. {_TIME_HINT}"
    if not _TIME_RE.match(value.strip()):
        return f"'{value}' is not a valid time. {_TIME_HINT}"
    return None


def schedule_payload_error(data: dict) -> str | None:
    """Validate the timing fields present in a create/update API payload.

    Only keys the caller actually sent are checked, so a partial update stays
    a partial update. Returns the first problem found, or None.
    """
    if "schedule_tz" in data:
        error = schedule_timezone_error(data.get("schedule_tz"))
        if error:
            return error
    if "schedule_time" in data:
        error = schedule_time_error(data.get("schedule_time"))
        if error:
            return error
    return None


def schedule_config_error(schedule: dict) -> str | None:
    """Return why the scheduler will refuse to register `schedule`, or None.

    Mirrors the defaults register_schedule_job applies, so a stored row that
    passes here is a row the scheduler can turn into a cron job.
    """
    return schedule_time_error(schedule.get("schedule_time") or "09:00") or schedule_timezone_error(
        schedule.get("schedule_tz") or "UTC"
    )
