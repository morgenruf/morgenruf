"""Dashboard Flask blueprint — workspace configuration UI and API."""

from __future__ import annotations

import csv
import io
import json
import ipaddress
import logging
import os
import uuid
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import db
from oauth import verify_login_token

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__, template_folder="templates")

_APP_URL = os.environ.get("APP_URL", "http://localhost:3000")
_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
_SCOPES = "channels:read,chat:write,im:history,im:read,im:write,users:read,users:read.email"


def _is_safe_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
        except ValueError:
            pass  # hostname, not IP — allow it (DNS resolution at request time)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("team_id"):
            if request.path.startswith("/dashboard/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("dashboard.login"))
        return f(*args, **kwargs)
    return wrapper


def _get_bot_token() -> str | None:
    team_id = session.get("team_id")
    if not team_id:
        return None
    try:
        inst = db.get_installation(team_id)
        return inst["bot_token"] if inst else None
    except Exception as exc:
        logger.warning("Could not get bot token: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard")
def dashboard():
    # Accept one-time login token from OAuth redirect to bootstrap session
    token = request.args.get("t")
    if token:
        team_id = verify_login_token(token)
        if team_id:
            session["team_id"] = team_id
            try:
                inst = db.get_installation(team_id)
                session["team_name"] = inst["team_name"] if inst else team_id
            except Exception:
                session["team_name"] = team_id
            return redirect(url_for("dashboard.dashboard"))

    if not session.get("team_id"):
        return redirect(url_for("dashboard.login"))

    team_id = session["team_id"]
    try:
        inst = db.get_installation(team_id)
        team_name = inst["team_name"] if inst else team_id
    except Exception:
        team_name = team_id
    return render_template("dashboard.html", team_name=team_name, team_id=team_id)


@dashboard_bp.route("/dashboard/login")
def login():
    if session.get("team_id"):
        return redirect(url_for("dashboard.dashboard"))
    # Use /install which generates a proper HMAC state
    return redirect(url_for("oauth.install"))


@dashboard_bp.route("/dashboard/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard.login"))


# ---------------------------------------------------------------------------
# Standup config API
# Each workspace_config row is treated as one "standup".
# For workspaces that haven't created one yet, we support creation.
# ---------------------------------------------------------------------------

def _config_to_standup(cfg: dict) -> dict:
    """Normalise a workspace_config row into a standup API object."""
    questions = cfg.get("questions") or []
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except Exception:
            questions = []
    return {
        "id": cfg.get("id", 1),
        "name": cfg.get("name", "Morning Standup"),
        "channel_id": cfg.get("channel_id") or "",
        "schedule_time": cfg.get("schedule_time") or "09:00",
        "schedule_tz": cfg.get("schedule_tz") or "UTC",
        "schedule_days": (cfg.get("schedule_days") or "mon,tue,wed,thu,fri").split(","),
        "questions": questions,
        "active": cfg.get("active", True),
        "participants": cfg.get("participants") or [],
        "report_channel": cfg.get("report_channel") or "",
        "report_time": cfg.get("report_time") or "",
        "group_by": cfg.get("group_by") or "member",
        "post_as": cfg.get("post_as") or "combined",
        "sort_order": cfg.get("sort_order") or "chronological",
        "edit_window": cfg.get("edit_window") or "report",
        "display_avatar": cfg.get("display_avatar", True),
        "jira_base_url": cfg.get("jira_base_url") or "",
        "zendesk_base_url": cfg.get("zendesk_base_url") or "",
        "reminder_minutes": int(cfg.get("reminder_minutes") or 0),
    }


@dashboard_bp.route("/dashboard/api/standups", methods=["GET"])
@_login_required
def api_list_standups():
    team_id = session["team_id"]
    try:
        cfg = db.get_workspace_config(team_id)
        if cfg:
            return jsonify([_config_to_standup(cfg)])
        return jsonify([])
    except Exception as exc:
        logger.error("api_list_standups error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/standups", methods=["POST"])
@_login_required
def api_create_standup():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        days = data.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])
        if isinstance(days, list):
            days = ",".join(days)
        db.upsert_workspace_config(
            team_id,
            channel_id=data.get("channel_id", ""),
            schedule_time=data.get("schedule_time", "09:00"),
            schedule_tz=data.get("schedule_tz", "UTC"),
            schedule_days=days,
            questions=data.get("questions", ["What did you do yesterday?", "What are you doing today?", "Any blockers?"]),
            active=data.get("active", True),
            reminder_minutes=int(data.get("reminder_minutes") or 0),
        )
        cfg = db.get_workspace_config(team_id)
        return jsonify(_config_to_standup(cfg)), 201
    except Exception as exc:
        logger.error("api_create_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/standups/<standup_id>", methods=["PUT"])
@_login_required
def api_update_standup(standup_id: str):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        days = data.get("schedule_days")
        if isinstance(days, list):
            days = ",".join(days)
        kwargs: dict = {}
        if "channel_id" in data:
            kwargs["channel_id"] = data["channel_id"]
        if "schedule_time" in data:
            kwargs["schedule_time"] = data["schedule_time"]
        if "schedule_tz" in data:
            kwargs["schedule_tz"] = data["schedule_tz"]
        if days is not None:
            kwargs["schedule_days"] = days
        if "questions" in data:
            kwargs["questions"] = data["questions"]
        if "active" in data:
            kwargs["active"] = data["active"]
        if "reminder_minutes" in data:
            kwargs["reminder_minutes"] = int(data.get("reminder_minutes") or 0)
        if kwargs:
            db.upsert_workspace_config(team_id, **kwargs)
        cfg = db.get_workspace_config(team_id)
        return jsonify(_config_to_standup(cfg))
    except Exception as exc:
        logger.error("api_update_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/standups/<standup_id>", methods=["DELETE"])
@_login_required
def api_delete_standup(standup_id: str):
    team_id = session["team_id"]
    try:
        db.upsert_workspace_config(team_id, active=False)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("api_delete_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Members API
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/members", methods=["GET"])
@_login_required
def api_members():
    token = _get_bot_token()
    if not token:
        return jsonify([])
    try:
        from slack_sdk import WebClient  # noqa: PLC0415
        client = WebClient(token=token)
        result = client.users_list(limit=200)
        members = []
        for u in result.get("members", []):
            if u.get("deleted") or u.get("is_bot") or u.get("id") == "USLACKBOT":
                continue
            profile = u.get("profile", {})
            members.append({
                "id": u["id"],
                "name": profile.get("real_name") or u.get("name", ""),
                "display_name": profile.get("display_name") or u.get("name", ""),
                "avatar": profile.get("image_48", ""),
                "email": profile.get("email", ""),
                "tz": u.get("tz", "UTC"),
            })
        return jsonify(members)
    except Exception as exc:
        logger.error("api_members error: %s", exc)
        # Fall back to DB members
        try:
            rows = db.get_active_members(session["team_id"])
            return jsonify([
                {"id": r["user_id"], "name": r.get("real_name", ""), "email": r.get("email", ""), "tz": r.get("tz", "UTC")}
                for r in rows
            ])
        except Exception:
            return jsonify([])


# ---------------------------------------------------------------------------
# Channels API (helper for dropdowns)
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/channels", methods=["GET"])
@_login_required
def api_channels():
    token = _get_bot_token()
    if not token:
        return jsonify([])
    try:
        from slack_sdk import WebClient  # noqa: PLC0415
        client = WebClient(token=token)
        channels = []
        cursor = None
        while True:
            kwargs = {"types": "public_channel", "exclude_archived": True, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = client.conversations_list(**kwargs)
            for c in result.get("channels", []):
                channels.append({"id": c["id"], "name": c["name"]})
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return jsonify(sorted(channels, key=lambda c: c["name"]))
    except Exception as exc:
        logger.error("api_channels error: %s", exc)
        return jsonify([])


# ---------------------------------------------------------------------------
# Stats API
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/stats", methods=["GET"])
@_login_required
def api_stats():
    team_id = session["team_id"]
    try:
        stats = db.get_dashboard_stats(team_id)
        return jsonify(stats)
    except Exception as exc:
        logger.warning("api_stats error: %s", exc)
        return jsonify({
            "completion_rate": 0,
            "active_members": 0,
            "total_responses": 0,
            "responses_this_week": 0,
        })


# ---------------------------------------------------------------------------
# Webhooks API
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/webhooks", methods=["GET"])
@_login_required
def api_list_webhooks():
    team_id = session["team_id"]
    try:
        hooks = db.get_webhooks(team_id)
        return jsonify(hooks)
    except Exception as exc:
        logger.warning("api_list_webhooks error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/webhooks", methods=["POST"])
@_login_required
def api_add_webhook():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    url_val = data.get("url", "").strip()
    if not url_val:
        return jsonify({"error": "url is required"}), 400
    if not _is_safe_webhook_url(url_val):
        return jsonify({"error": "Invalid or unsafe webhook URL"}), 400
    try:
        hook = db.add_webhook(team_id, url_val)
        return jsonify(hook), 201
    except Exception as exc:
        logger.error("api_add_webhook error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/webhooks/<hook_id>", methods=["DELETE"])
@_login_required
def api_delete_webhook(hook_id: str):
    team_id = session["team_id"]
    try:
        db.delete_webhook(team_id, hook_id)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("api_delete_webhook error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Analytics API
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/analytics", methods=["GET"])
@_login_required
def api_analytics():
    team_id = session["team_id"]
    days = int(request.args.get("days", 7))
    try:
        stats = db.get_participation_stats(team_id, days)
        for row in stats:
            if row.get("last_standup"):
                row["last_standup"] = row["last_standup"].isoformat()
            row["responses"] = int(row.get("responses") or 0)
            row["days_with_blockers"] = int(row.get("days_with_blockers") or 0)
        return jsonify(stats)
    except Exception as exc:
        logger.error("api_analytics error: %s", exc)
        return jsonify([])


# ---------------------------------------------------------------------------
# CSV Export API
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/export/csv", methods=["GET"])
@_login_required
def api_export_csv():
    team_id = session["team_id"]
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    try:
        rows = db.export_standups(team_id, from_date, to_date)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["standup_date", "user_id", "yesterday", "today", "blockers", "has_blockers", "submitted_at", "mood"],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "standup_date": row.get("standup_date", ""),
            "user_id": row.get("user_id", ""),
            "yesterday": row.get("yesterday", ""),
            "today": row.get("today", ""),
            "blockers": row.get("blockers", ""),
            "has_blockers": row.get("has_blockers", ""),
            "submitted_at": row.get("submitted_at", ""),
            "mood": row.get("mood", ""),
        })
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=standups-{team_id}.csv"},
    )
