"""The Monday usage report, posted to the operator's alert channel.

One message a week that says whether outside teams use Morgenruf: weekly
active people, which workspaces are active, trying or idle, what was removed,
and where new installs came from. Counts and workspace names only, never a
person. Workspaces listed in MORGENRUF_INTERNAL_TEAMS (the operator's own)
are left out.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import date, datetime, timezone

ACTIVE_AT = 3


def internal_teams() -> set[str]:
    """MORGENRUF_INTERNAL_TEAMS: the operator's own workspaces, left out of
    the report and never nudged."""
    raw = os.environ.get("MORGENRUF_INTERNAL_TEAMS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _name(row: dict) -> str:
    from src.core.alerts import _escape  # noqa: PLC0415

    return _escape(row.get("team_name") or row.get("team_id") or "?")


def _people(row: dict) -> int:
    return int(row.get("people_7d") or 0)


def _names(rows: list[dict], with_people: bool = False) -> str:
    return ", ".join(f"{_name(r)} {_people(r)}" if with_people else _name(r) for r in rows)


def build(rows: list[dict], internal: set[str], today: date | None = None) -> str:
    """The report text for `rows` (see db.usage_report_rows), without `internal` teams."""
    today = today or datetime.now(timezone.utc).date()
    outside = [r for r in rows if r.get("team_id") not in internal]
    live = [r for r in outside if r.get("active")]
    removed = [r for r in outside if r.get("removed_this_week")]
    by_people = sorted(live, key=lambda r: (-_people(r), _name(r)))

    active = [r for r in by_people if _people(r) >= ACTIVE_AT]
    trying = [r for r in by_people if 0 < _people(r) < ACTIVE_AT]
    quiet = [r for r in by_people if _people(r) == 0 and r.get("has_standup")]
    idle = [r for r in by_people if _people(r) == 0 and not r.get("has_standup")]
    activated = sum(1 for r in live if r.get("activated_this_week"))
    sources = Counter((r.get("install_source") or "direct") for r in outside if r.get("installed_this_week"))

    lines = [
        f"*Morgenruf, week to {today.strftime('%a')} {today.day} {today.strftime('%b')}*",
        f"Weekly active people: {sum(_people(r) for r in live)}",
        f"Outside workspaces: {len(live)} installed, {activated} activated this week, {len(removed)} removed",
    ]
    if active:
        lines.append(f"Active teams ({ACTIVE_AT}+ people): {_names(active, with_people=True)}")
    if trying:
        lines.append(f"Trying (1 to {ACTIVE_AT - 1} people): {_names(trying, with_people=True)}")
    if quiet:
        lines.append(f"Standup set, no answers this week: {_names(quiet)}")
    if idle:
        nudged = [r for r in idle if r.get("nudged")]
        suffix = f" (nudged: {_names(nudged)})" if nudged else ""
        lines.append(f"Installed, no standup yet: {_names(idle)}{suffix}")
    if removed:
        lines.append(f"Removed this week: {_names(removed)}")
    watercooler = [r for r in live if int(r.get("watercooler_7d") or 0) > 0]
    if watercooler:
        posts = sum(int(r.get("watercooler_7d") or 0) for r in watercooler)
        lines.append(f"Watercooler: {posts} questions posted in {len(watercooler)} workspaces")
    if sources:
        ranked = sorted(sources.items(), key=lambda kv: (-kv[1], kv[0]))
        lines.append("New installs by source: " + ", ".join(f"{src} {n}" for src, n in ranked))
    return "\n".join(lines)


def post_weekly() -> bool:
    """Build the report from the database and post it. True when it was posted."""
    import src.core.db as db  # noqa: PLC0415
    from src.core.alerts import notify  # noqa: PLC0415

    return notify(build(db.usage_report_rows(), internal_teams()))
