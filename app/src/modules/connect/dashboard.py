"""Connect HTTP API.

Built inside register_routes rather than at import time, so importing the
registry does not pull core's dashboard in as a side effect.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_routes(flask_app) -> None:
    from flask import Blueprint, jsonify, request, session

    import src.core.db as db
    import src.modules.connect.db as cdb
    from src.core.dashboard import _admin_required, _login_required
    from src.core.roster import eligible_members
    from src.modules.connect.rounds import match_status

    bp = Blueprint("connect", __name__)

    # Zoom linking lives on the same blueprint. Its two endpoints are reached
    # from a Slack button rather than the dashboard, so they carry a signed
    # token instead of relying on a session.
    from src.modules.connect.zoom_routes import register_zoom_routes  # noqa: PLC0415

    register_zoom_routes(bp)

    @bp.route("/dashboard/api/connect/programs", methods=["GET"])
    @_login_required
    def list_programs():
        team_id = session["team_id"]
        try:
            programs = cdb.get_programs(team_id)
        except Exception as exc:
            logger.warning("connect list_programs: %s", exc)
            return jsonify([])
        for p in programs:
            p["created_at"] = p["created_at"].isoformat() if p.get("created_at") else None
            p["last_round"] = p["last_round"].isoformat() if p.get("last_round") else None
            p["next_round_date"] = p["next_round_date"].isoformat() if p.get("next_round_date") else None
            try:
                # The same intersection the round itself does: people in the
                # channel who are also eligible and have not opted out.
                # Counting the whole workspace claimed a pool nobody would be
                # matched from.
                from slack_sdk import WebClient  # noqa: PLC0415

                import src.modules.connect.slack_api as api  # noqa: PLC0415

                inst = db.get_installation(team_id) or {}
                token = inst.get("bot_token") or ""
                in_channel = set(api.channel_member_ids(WebClient(token=token), p["channel_id"])) if token else None
                eligible = {m.user_id for m in eligible_members(team_id)}
                opted_out = cdb.optout_user_ids(team_id, p["id"])
                pool = eligible if in_channel is None else (eligible & in_channel)
                p["pool_size"] = len(pool - opted_out)
            except Exception as exc:
                # Slack being unreachable is not a reason to fail the page; the
                # number is simply unknown rather than wrong.
                logger.info("connect: could not size the pool for %s: %s", p["id"], exc)
                p["pool_size"] = None
        return jsonify(programs)

    @bp.route("/dashboard/api/connect/programs", methods=["POST"])
    @_admin_required("connect")
    def create_program():
        team_id = session["team_id"]
        data = request.get_json(silent=True) or {}
        channel_id = (data.get("channel_id") or "").strip()
        if not channel_id:
            return jsonify({"error": "Pick a channel to draw people from"}), 400
        try:
            interval = int(data.get("interval_weeks", 1))
        except (TypeError, ValueError):
            return jsonify({"error": "Cadence must be a number of weeks"}), 400
        if interval < 1 or interval > 8:
            return jsonify({"error": "Cadence must be between 1 and 8 weeks"}), 400
        program = cdb.create_program(
            team_id=team_id,
            channel_id=channel_id,
            name=(data.get("name") or "Coffee chats").strip()[:80],
            interval_weeks=interval,
            day_of_week=int(data.get("day_of_week", 1)),
            hour=int(data.get("hour", 10)),
            minute=int(data.get("minute", 0)),
            timezone=(data.get("timezone") or "UTC").strip(),
        )
        program["created_at"] = program["created_at"].isoformat() if program.get("created_at") else None
        return jsonify(program)

    @bp.route("/dashboard/api/connect/programs/<int:program_id>", methods=["POST"])
    @_admin_required("connect")
    def update_program(program_id: int):
        """Change a programme. A body with only `enabled` keeps the old toggle
        behaviour, so the switch on the card still works unchanged."""
        team_id = session["team_id"]
        data = request.get_json(silent=True) or {}
        if set(data) == {"enabled"}:
            cdb.set_program_enabled(team_id, program_id, bool(data["enabled"]))
            return jsonify({"id": program_id, "enabled": bool(data["enabled"])})

        if not cdb.owns_program(team_id, program_id):
            return jsonify({"error": "not found"}), 404

        fields = {}
        if "name" in data:
            fields["name"] = (data.get("name") or "Coffee chats").strip()[:80]
        if "channel_id" in data and (data.get("channel_id") or "").strip():
            fields["channel_id"] = data["channel_id"].strip()
        for key, lo, hi in (("interval_weeks", 1, 8), ("day_of_week", 0, 6), ("hour", 0, 23), ("minute", 0, 59)):
            if key in data:
                try:
                    value = int(data[key])
                except (TypeError, ValueError):
                    return jsonify({"error": f"{key} must be a number"}), 400
                if not lo <= value <= hi:
                    return jsonify({"error": f"{key} must be between {lo} and {hi}"}), 400
                fields[key] = value
        if "timezone" in data:
            fields["timezone"] = (data.get("timezone") or "UTC").strip()
        if "match_working_hours" in data:
            fields["match_working_hours"] = bool(data["match_working_hours"])
        if "meeting_minutes" in data:
            try:
                minutes = int(data["meeting_minutes"])
            except (TypeError, ValueError):
                return jsonify({"error": "meeting_minutes must be a number"}), 400
            if minutes not in (15, 30, 45, 60):
                return jsonify({"error": "meeting_minutes must be 15, 30, 45 or 60"}), 400
            fields["meeting_minutes"] = minutes
        if "meeting_link" in data:
            link = (data.get("meeting_link") or "").strip()
            if link and not link.startswith(("https://", "http://")):
                return jsonify({"error": "The meeting link must be a URL"}), 400
            fields["meeting_link"] = link or None
        if "enabled" in data:
            fields["enabled"] = bool(data["enabled"])

        program = cdb.update_program(team_id, program_id, **fields)
        if not program:
            return jsonify({"error": "not found"}), 404
        program["created_at"] = program["created_at"].isoformat() if program.get("created_at") else None
        return jsonify(program)

    @bp.route("/dashboard/api/connect/programs/<int:program_id>", methods=["DELETE"])
    @_admin_required("connect")
    def delete_program(program_id: int):
        team_id = session["team_id"]
        if not cdb.delete_program(team_id, program_id):
            return jsonify({"error": "not found"}), 404
        return jsonify({"deleted": program_id})

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/run", methods=["POST"])
    @_admin_required("connect")
    def run_now(program_id: int):
        """Start a round immediately, rather than waiting for the cadence.

        Without this a programme could not be tried at all until its scheduled
        day came round, which is a poor way to find out whether it works.
        """
        team_id = session["team_id"]
        if not cdb.owns_program(team_id, program_id):
            return jsonify({"error": "not found"}), 404
        try:
            from src.modules.connect.jobs import run_round  # noqa: PLC0415

            run_round(program_id, force=True)
        except Exception as exc:
            logger.exception("connect run_now failed for %s", program_id)
            return jsonify({"error": str(exc)}), 500
        rounds = cdb.recent_rounds(team_id, program_id, 1)
        return jsonify({"started": True, "round": rounds[0]["id"] if rounds else None})

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/rounds", methods=["GET"])
    @_login_required
    def list_rounds(program_id: int):
        team_id = session["team_id"]
        try:
            rounds = cdb.recent_rounds(team_id, program_id)
        except Exception as exc:
            logger.warning("connect list_rounds: %s", exc)
            return jsonify([])
        for r in rounds:
            r["scheduled_for"] = r["scheduled_for"].isoformat() if r.get("scheduled_for") else None
            r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
        return jsonify(rounds)

    @bp.route("/dashboard/api/connect/rounds/<int:round_id>/matches", methods=["GET"])
    @_login_required
    def list_round_matches(round_id: int):
        """Who was put with whom, and whether it happened."""
        team_id = session["team_id"]
        try:
            matches = cdb.round_matches(team_id, round_id)
        except Exception as exc:
            logger.warning("connect list_round_matches: %s", exc)
            return jsonify([])
        out = []
        for m in matches:
            delivered = m.get("delivered_at")
            out.append(
                {
                    "id": m["id"],
                    "members": list(m["member_ids"] or []),
                    "status": match_status(m["met"], delivered),
                    "delivered_at": delivered.isoformat() if delivered else None,
                    "nudged_at": m["nudged_at"].isoformat() if m.get("nudged_at") else None,
                    # Agreeing a time is the step between an introduction and a
                    # meeting, so a pairing that settled one reads differently
                    # from one that went quiet, even before anybody answers
                    # whether they met.
                    "agreed_at": m["agreed_slot_utc"].isoformat() if m.get("agreed_slot_utc") else None,
                    "has_zoom": bool(m.get("zoom_join_url")),
                }
            )
        return jsonify(out)

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/members", methods=["GET"])
    @_login_required
    def list_program_members(program_id: int):
        """Who is in this programme and how each of them stands.

        There was no way to see or change this from the dashboard at all: the
        opt-out table has existed since the module shipped and only the person
        themselves could write to it, from Slack. An admin could not tell who
        had quietly excluded themselves, let alone put somebody back in.
        """
        team_id = session["team_id"]
        program = cdb.get_program(program_id)
        if not program or program.get("team_id") != team_id:
            return jsonify([]), 404
        try:
            states = cdb.member_states(team_id, program_id)
            paired = cdb.pair_counts(team_id, program_id)
            roster = {m.user_id: m for m in eligible_members(team_id)}
        except Exception as exc:
            logger.warning("connect list_program_members: %s", exc)
            return jsonify([])

        # The channel decides who is in the programme, so it is the source of
        # truth for the list. Without Slack reachable we still show everyone we
        # know about rather than an empty table.
        try:
            from slack_sdk import WebClient

            from src.modules.connect import slack_api as api

            inst = db.get_installation(team_id) or {}
            client = WebClient(token=inst.get("bot_token") or "")
            in_channel = list(api.channel_member_ids(client, program["channel_id"]))
        except Exception:
            logger.info("connect: channel membership unavailable, showing the roster")
            in_channel = list(roster)

        out = []
        for user_id in in_channel:
            member = roster.get(user_id)
            state = states.get(user_id) or {"state": "in", "until": None}
            until = state.get("until")
            out.append(
                {
                    "user_id": user_id,
                    "name": (getattr(member, "real_name", "") or user_id) if member else user_id,
                    "avatar": getattr(member, "avatar", "") if member else "",
                    # Somebody in the channel who is not on the roster is a
                    # deactivated account or a guest: shown, not silently
                    # dropped, because "why is this person never matched" is
                    # the question this table exists to answer.
                    "eligible": bool(member),
                    "state": state["state"],
                    "until": until.isoformat() if hasattr(until, "isoformat") else None,
                    "paired": paired.get(user_id, 0),
                }
            )
        out.sort(key=lambda r: (r["state"] != "in", r["name"].lower()))
        return jsonify(out)

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/members/<user_id>", methods=["POST"])
    @_admin_required("connect")
    def set_program_member(program_id: int, user_id: str):
        """Put somebody in, take them out, or snooze them until a date."""
        team_id = session["team_id"]
        program = cdb.get_program(program_id)
        if not program or program.get("team_id") != team_id:
            return jsonify({"error": "Not found"}), 404

        data = request.get_json(force=True) or {}
        state = str(data.get("state") or "").strip()
        try:
            if state == "in":
                cdb.opt_in(team_id, program_id, user_id)
            elif state == "out":
                cdb.opt_out(team_id, program_id, user_id, mode="off")
            elif state == "snoozed":
                from datetime import date, timedelta

                weeks = int(data.get("weeks") or 2)
                cdb.snooze(team_id, program_id, user_id, date.today() + timedelta(weeks=weeks))
            else:
                return jsonify({"error": "state must be in, out or snoozed"}), 400
        except Exception as exc:
            logger.warning("connect set_program_member: %s", exc)
            return jsonify({"error": "Could not save"}), 500
        return jsonify(cdb.personal_state(team_id, program_id, user_id) | {"user_id": user_id})

    @bp.route("/dashboard/api/connect/zoom", methods=["GET"])
    @_login_required
    def zoom_summary():
        """Whether Zoom is available here, and how many people have connected.

        `configured` is what lets the page say "not set up on this deployment"
        rather than "nobody has connected", which are different problems with
        different fixes.
        """
        from src.modules.connect import zoom as zoom_mod

        team_id = session["team_id"]
        if not zoom_mod.configured():
            return jsonify({"configured": False, "linked": 0, "needs_reconnect": 0})
        try:
            summary = cdb.zoom_link_summary(team_id)
        except Exception as exc:
            logger.warning("connect zoom_summary: %s", exc)
            summary = {"linked": 0, "needs_reconnect": 0}
        return jsonify({"configured": True, **summary})

    @bp.route("/dashboard/api/connect/programs/<int:program_id>/participation", methods=["GET"])
    @_login_required
    def program_participation(program_id: int):
        team_id = session["team_id"]
        try:
            rounds = int(request.args.get("rounds", 6))
        except (TypeError, ValueError):
            rounds = 6
        rounds = max(1, min(rounds, 52))
        try:
            rows = cdb.participation(team_id, program_id, rounds)
        except Exception as exc:
            logger.warning("connect participation: %s", exc)
            return jsonify([])
        for r in rows:
            r["last_met"] = r["last_met"].isoformat() if r.get("last_met") else None
        return jsonify(rows)

    flask_app.register_blueprint(bp)
