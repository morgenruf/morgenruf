"""Polls as MCP tools.

Results go through the dashboard's poll_payload, so an assistant sees what
the Slack message shows and never more: no counts while a poll hides its
results, and no names on an anonymous poll, ever. Anonymous votes are stored
under an HMAC anyway, so there are no names to leak, but the rule is applied
here too rather than relied on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.mcp_tools import identity, member_identities, window
from src.modules.polls.dashboard import poll_payload


def _list(args: dict, team_id: str) -> Any:
    import src.modules.polls.db as pdb  # noqa: PLC0415

    days, limit = window(args)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    people = member_identities(team_id)
    # Newest first, so the ones inside the window are a prefix of the page.
    return [
        {
            "id": p["id"],
            "question": p["question"],
            "channel_id": p["channel_id"],
            "created_by": identity(people, p["created_by"]),
            "created_at": p["created_at"],
            "closes_at": p.get("closes_at"),
            "status": "closed" if p.get("closed_at") else "open",
            "total_votes": sum(p.get("counts") or []),
            "anonymous": bool(p.get("anonymous")),
            "multiple": bool(p.get("multiple")),
            "hide_results": bool(p.get("hide_results")),
        }
        for p in pdb.list_polls(team_id, limit)
        if p["created_at"] >= since
    ]


def _results(args: dict, team_id: str) -> Any:
    import src.modules.polls.db as pdb  # noqa: PLC0415

    poll_id = args.get("poll_id")
    if not poll_id:
        return {"error": "poll_id is required. Call list_polls first."}
    poll = pdb.get_poll(int(poll_id))
    if not poll or poll.get("team_id") != team_id:
        return {"error": "Poll not found."}
    voters = None if poll.get("anonymous") else pdb.voters(poll["id"])
    shown = poll_payload(poll, pdb.tally(poll["id"]), voters, False)
    people = member_identities(team_id)
    total = shown["total_votes"]
    options = []
    for o in shown["options"]:
        option = {"text": o["text"], "votes": o["votes"]}
        if o["votes"] is not None:
            option["percent"] = round(o["votes"] / total * 100, 1) if total else 0.0
        if o["voters"] is not None:
            option["voters"] = [identity(people, u) for u in o["voters"]]
        options.append(option)
    return {
        "id": shown["id"],
        "question": shown["question"],
        "status": "closed" if shown["closed_at"] else "open",
        "anonymous": shown["anonymous"],
        "multiple": shown["multiple"],
        "results_hidden_until_close": options[0]["votes"] is None if options else False,
        "total_votes": total,
        "options": options,
    }


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_polls",
            "description": (
                "Polls started in the last N days, newest first: question, channel, who started it, "
                "open or closed, total votes, and whether it is anonymous. On a poll that allows "
                "several choices, total votes counts picks, not people."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days (default: 30)"},
                    "limit": {"type": "integer", "description": "How many to return (default: 50, max: 200)"},
                },
            },
            "handler": _list,
        },
        {
            "name": "get_poll_results",
            "description": (
                "Votes and percentage per option for one poll, and who picked what on a named poll. "
                "An anonymous poll returns counts only. A poll that hides results until it closes "
                "returns no counts while it is open."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"poll_id": {"type": "integer", "description": "Poll id from list_polls"}},
                "required": ["poll_id"],
            },
            "handler": _results,
        },
    ]
