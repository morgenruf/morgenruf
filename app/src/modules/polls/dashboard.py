"""Polls HTTP API.

Built inside register_routes, like every module, so importing the registry
does not load core's dashboard.

The page shows what the Slack message shows, never more: while a poll hides
its results there is no count per option, and an anonymous poll never names
anyone. A member sees the polls in channels they could read in Slack, plus
their own; workspace admins and Polls admins see every poll.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MODULE_NAME = "polls"


def poll_payload(poll: dict, counts: list[int], voters_by_option: dict[int, list[str]] | None, can_close: bool) -> dict:
    """One poll for the browser, with results only where Slack shows them."""
    options = list(poll.get("options") or [])
    counts = list(counts or []) + [0] * (len(options) - len(counts or []))
    showing = bool(poll.get("closed_at")) or not poll.get("hide_results")
    names = None if poll.get("anonymous") or not showing else (voters_by_option or {})
    return {
        "id": poll["id"],
        "question": poll["question"],
        "channel_id": poll["channel_id"],
        "created_by": poll["created_by"],
        "anonymous": bool(poll.get("anonymous")),
        "multiple": bool(poll.get("multiple")),
        "hide_results": bool(poll.get("hide_results")),
        "created_at": poll.get("created_at"),
        "closes_at": poll.get("closes_at"),
        "closed_at": poll.get("closed_at"),
        "total_votes": sum(counts),
        "can_close": bool(can_close) and not poll.get("closed_at"),
        "options": [
            {
                "text": text,
                "votes": counts[i] if showing else None,
                "voters": list(names.get(i, [])) if names is not None else None,
            }
            for i, text in enumerate(options)
        ],
    }


def register_routes(flask_app) -> None:
    from flask import jsonify, session
    from flask_smorest import Blueprint

    import src.core.db as db
    import src.modules.polls.db as pdb
    from src.core.api import api_errors, register_api_blueprint
    from src.core.dashboard import _can_see_channel, _get_bot_token, _login_required
    from src.modules.polls import schemas
    from src.modules.polls.handlers import finish_poll

    bp = Blueprint("polls", __name__)

    def _client():
        token = _get_bot_token()
        if not token:
            return None
        from slack_sdk import WebClient  # noqa: PLC0415

        return WebClient(token=token)

    def _is_admin(team_id: str, user_id: str) -> bool:
        try:
            return db.can_administer(team_id, user_id, "polls")
        except Exception as exc:
            logger.warning("polls admin check failed: %s", exc)
            return False

    def _named_voters(poll: dict) -> dict[int, list[str]] | None:
        if poll.get("anonymous"):
            return None
        try:
            return pdb.voters(poll["id"])
        except Exception as exc:
            logger.warning("polls: could not read voters for %s: %s", poll["id"], exc)
            return {}

    @bp.route("/dashboard/api/polls", methods=["GET"])
    @_login_required
    @bp.doc(operationId="listPolls", tags=["Polls"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Poll(many=True))
    def list_polls():
        team_id = session["team_id"]
        user_id = session.get("user_id") or ""
        try:
            polls = pdb.list_polls(team_id)
        except Exception as exc:
            logger.error("polls list: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        admin = _is_admin(team_id, user_id)
        client = None if admin else _client()
        seen: dict[str, bool] = {}

        def visible(poll: dict) -> bool:
            if admin or poll.get("created_by") == user_id:
                return True
            channel_id = poll.get("channel_id") or ""
            if channel_id not in seen:
                seen[channel_id] = client is not None and _can_see_channel(client, channel_id, user_id)
            return seen[channel_id]

        return [
            poll_payload(p, p.get("counts") or [], _named_voters(p), admin or p.get("created_by") == user_id)
            for p in polls
            if visible(p)
        ]

    @bp.route("/dashboard/api/polls/<int:poll_id>/close", methods=["POST"])
    @_login_required
    @bp.doc(operationId="closePoll", tags=["Polls"], security=[{"sessionCookie": [], "csrfHeader": []}])
    @api_errors(bp)
    @bp.response(200, schemas.Poll)
    def close_poll(poll_id: int):
        """Close a poll, as the Close button in Slack does. Its creator or a Polls admin."""
        team_id = session["team_id"]
        user_id = session.get("user_id") or ""
        try:
            poll = pdb.get_poll(poll_id)
        except Exception as exc:
            logger.error("polls close: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        if not poll or poll.get("team_id") != team_id:
            return jsonify({"error": "Poll not found"}), 404
        if poll.get("created_by") != user_id and not _is_admin(team_id, user_id):
            return jsonify({"error": "Only the person who started this poll, or a Polls admin, can close it"}), 403
        if not poll.get("closed_at"):
            try:
                finish_poll(_client(), poll_id)
            except Exception as exc:
                logger.error("polls close %s: %s", poll_id, exc)
                return jsonify({"error": "Service unavailable"}), 503
        poll = pdb.get_poll(poll_id) or poll
        return poll_payload(poll, pdb.tally(poll_id), _named_voters(poll), False)

    register_api_blueprint(flask_app, bp)
