"""What kudos shows on the Slack App Home tab.

Recognition belongs where people already are. A leaderboard that only exists
in a web dashboard is a leaderboard almost nobody sees, and the balance is
only useful at the moment someone is deciding whether to spend it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_TOP_N = 10


def _member_timezone(team_id: str, user_id: str) -> str:
    try:
        import src.core.db as core_db  # noqa: PLC0415

        for row in core_db.get_all_members(team_id):
            if row.get("user_id") == user_id:
                return row.get("tz") or "UTC"
    except Exception:
        pass
    return "UTC"


def home_blocks(team_id: str, user_id: str) -> list[dict]:
    """The viewer's own balance, then who is being recognised.

    Personal numbers come first because they are the ones that prompt an
    action; the leaderboard is context.
    """
    import src.modules.kudos.db as kdb  # noqa: PLC0415

    try:
        state = kdb.allowance_state(team_id, user_id, _member_timezone(team_id, user_id), datetime.now(timezone.utc))
        emoji = state["emoji"]
        received = kdb.get_kudos_leaderboard(team_id, days=30)
        given = kdb.get_giver_leaderboard(team_id, days=30)
    except Exception as exc:
        logger.warning("kudos App Home unavailable for %s: %s", team_id, exc)
        return []

    mine_received = next((r["received"] for r in received if r.get("to_user") == user_id), 0)
    mine_given = next((r["given"] for r in given if r.get("user_id") == user_id), 0)

    blocks: list[dict] = [
        {"type": "divider"},
        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} Kudos", "emoji": True}},
    ]

    if state["allowance"] == 0:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "Giving is switched off for this workspace."}]}
        )
    else:
        left = state["remaining"]
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*You have {left} {emoji} left to give today.*"
                        if left
                        else f"*You have given all {state['allowance']} of your {emoji} today.*"
                    ),
                },
            }
        )
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Given this month: *{mine_given}*  ·  Received: *{mine_received}*  ·  "
                        f"Resets at midnight your time",
                    }
                ],
            }
        )
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "Send `kudos @teammate` and a reason to give one."}],
            }
        )

    if received:
        lines = "\n".join(
            f"{i}. <@{r['to_user']}>  `{r['received']}`" for i, r in enumerate(received[:_TOP_N], start=1)
        )
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Most recognised, last 30 days*\n{lines}"}}
        )
    if given:
        lines = "\n".join(f"{i}. <@{r['user_id']}>  `{r['given']}`" for i, r in enumerate(given[:5], start=1))
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Most generous, last 30 days*\n{lines}"}}
        )
    if not received and not given:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "Nobody has given any yet. Be the first."}]}
        )

    return blocks
