"""Deleting the data of workspaces that removed the app without telling us.

Slack sends app_uninstalled or tokens_revoked when a workspace removes the
app, and the handler purges at once. Not every removal arrives that way: the
member sync also finds workspaces whose token answers account_inactive or
invalid_auth and retires them, which until now deleted nothing. The listing
and the privacy page promise the data goes, so this sweep purges them once a
grace period has passed.

The grace period depends on what Slack said. account_inactive and a revoked
token mean the workspace is gone. invalid_auth can be a token refresh that
went wrong on our side, fixed by a reinstall, so it waits a week. Any other
reason is never purged here. A reinstall sets active again, and a purge
re-checks that under a row lock, so a workspace that came back is never
touched.

It is a dry run unless PURGE_INACTIVE_WORKSPACES is exactly "1": it logs every
workspace it would purge, with row counts per table, and deletes nothing.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

ENABLE_ENV = "PURGE_INACTIVE_WORKSPACES"

_GONE = timedelta(hours=24)
_MAYBE_OURS = timedelta(days=7)

# How long after retirement a workspace is purged, by the reason recorded.
# A reason not listed here is never purged by the sweep.
GRACE_BY_REASON: dict[str, timedelta] = {
    "account_inactive": _GONE,
    "token_revoked": _GONE,
    "tokens_revoked": _GONE,
    "app_uninstalled": _GONE,
    "invalid_auth": _MAYBE_OURS,
    "not_authed": _MAYBE_OURS,
}


def purge_enabled() -> bool:
    return os.environ.get(ENABLE_ENV, "").strip() == "1"


def is_due(row: dict, now: datetime) -> bool:
    """True when this retired workspace has waited out its grace period."""
    grace = GRACE_BY_REASON.get(row.get("deactivated_reason") or "")
    since = row.get("deactivated_at")
    if grace is None or since is None:
        return False
    return now - since >= grace


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{table}={n}" for table, n in counts.items() if n) or "no rows"


def sweep_inactive_workspaces(now: datetime | None = None) -> list[dict]:
    """Purge, or in a dry run list, every retired workspace past its grace period.

    Returns one entry per workspace that was due, with what happened to it.
    """
    import src.core.db as db  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    enabled = purge_enabled()
    report: list[dict] = []
    for row in db.purge_candidates():
        if not is_due(row, now):
            continue
        team_id, team_name = row["team_id"], row.get("team_name") or ""
        since = f"inactive since {row['deactivated_at']:%Y-%m-%d %H:%M} UTC ({row.get('deactivated_reason')})"
        entry = {"team_id": team_id, "team_name": team_name}
        try:
            if not enabled:
                counts = db.workspace_data_counts(team_id)
                logger.info(
                    "Workspace purge dry run: would purge %s (%s), %s: %s. Set %s=1 to delete.",
                    team_id,
                    team_name,
                    since,
                    _format_counts(counts),
                    ENABLE_ENV,
                )
                report.append({**entry, "action": "would_purge", "rows": sum(counts.values())})
                continue

            deleted = db.purge_workspace(team_id, expect_deactivated_at=row["deactivated_at"])
            if deleted is None:
                logger.info("Workspace purge: skipped %s (%s), it came back or is already purged", team_id, team_name)
                report.append({**entry, "action": "skipped", "rows": 0})
                continue
            logger.info("Workspace purge: purged %s (%s), %s: %s", team_id, team_name, since, _format_counts(deleted))
            report.append({**entry, "action": "purged", "rows": sum(deleted.values())})
        except Exception:
            logger.exception("Workspace purge failed for %s", team_id)
            report.append({**entry, "action": "failed", "rows": 0})

    purged = [r for r in report if r["action"] == "purged"]
    if purged:
        from src.core.alerts import notify  # noqa: PLC0415

        notify(f":wastebasket: Deleted the data of {len(purged)} removed workspace{'s' if len(purged) != 1 else ''}.")
    return report
