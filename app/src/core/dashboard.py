"""Dashboard Flask blueprint — workspace configuration UI and API."""

from __future__ import annotations

import csv
import hmac
import io
import json
import logging
import os
import re
import secrets
from functools import wraps

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

import src.core.db as db
from src.core.oauth import verify_login_token
from src.core.schedule_validation import schedule_config_error, schedule_payload_error
from src.core.scopes import SCOPE_STRING
from src.core.slack_users import is_human
from src.core.url_guard import is_safe_webhook_url

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__, template_folder="templates")

_APP_URL = os.environ.get("APP_URL", "http://localhost:3000")
_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
_SCOPES = SCOPE_STRING


def _is_safe_webhook_url(url: str) -> bool:
    """Kept as a thin alias so existing call sites and tests are unaffected.

    The implementation moved to url_guard so workflow.py can share it (#81).
    """
    return is_safe_webhook_url(url)


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


def _no_grant_message(module: str) -> str:
    """Why the request was refused, naming the feature as the sidebar does.

    The registry holds the label, so core still knows no feature by name.
    """
    try:
        from src.modules import REGISTRY  # noqa: PLC0415

        spec = next((s for s in REGISTRY if s.name == module), None)
        label = spec.nav[0].label if spec and spec.nav else module
    except Exception:
        label = module
    return f"Ask an admin to put you in charge of {label}"


def _admin_required(arg=None):
    """Require workspace admin, or admin of one named feature.

    Used bare, `@_admin_required`, it means workspace admin, which is right
    for the things that belong to the whole workspace: roles, invitations, API
    keys, the public feed. Used with a feature, `@_admin_required("standup")`,
    a person holding that grant passes too.

    Both spellings work so the change adds a capability without touching the
    seventeen routes that were already correct.
    """
    module = arg if isinstance(arg, str) else None

    def decorate(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            team_id = session.get("team_id")
            user_id = session.get("user_id")
            if not team_id:
                return jsonify({"error": "Unauthorized"}), 401
            try:
                if not db.can_administer(team_id, user_id or "", module):
                    return jsonify({"error": "Admin required" if module is None else _no_grant_message(module)}), 403
            except Exception as exc:
                logger.warning("_admin_required DB error: %s", exc)
                return jsonify({"error": "Service unavailable"}), 503
            return f(*args, **kwargs)

        return wrapper

    # Bare use: the decorator was applied directly to the function.
    return decorate(arg) if callable(arg) else decorate


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
        result = verify_login_token(token)
        if result:
            team_id, user_id = result
            session["team_id"] = team_id
            session["user_id"] = user_id
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
    # The MCP setup panel used to hardcode the hosted endpoint, so every
    # self-hosted install told its users to point their assistant at our
    # SaaS. APP_URL is what the deployment already sets for OAuth.
    return render_template(
        "dashboard.html",
        team_name=team_name,
        team_id=team_id,
        mcp_endpoint=f"{_APP_URL.rstrip('/')}/mcp",
    )


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
# Each standup_schedules row is one "standup".
# ---------------------------------------------------------------------------


def _next_run(row: dict) -> str:
    """When this schedule next fires, ISO 8601 in its own timezone, or "".

    Derived from the schedule's own config, so it is the same answer here in the
    forked dashboard worker as in the process holding the live jobs. Empty for an
    inactive schedule and for one the scheduler would refuse (#119).
    """
    if not row.get("active", True):
        return ""
    try:
        from src.core.scheduler import next_run_at  # noqa: PLC0415

        moment = next_run_at(row)
    except Exception as exc:
        logger.debug("Could not compute next run for schedule %s: %s", row.get("id"), exc)
        return ""
    return moment.isoformat() if moment else ""


def _post_summary_default(data: dict) -> bool:
    """Whether a new standup posts its daily summary.

    Migration 021 defaulted this to FALSE and shipped no control to change it,
    so no install could post a summary at all (#117). New standups post one
    unless the caller says otherwise.
    """
    return bool(data.get("post_summary", True))


def _schedule_to_standup(row: dict, workspace: dict | None = None) -> dict:
    """Normalise a standup_schedules row into a standup API object."""
    questions = row.get("questions") or []
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except Exception:
            questions = []

    participants = row.get("participants") or []
    if isinstance(participants, str):
        try:
            participants = json.loads(participants)
        except Exception:
            participants = []

    raw_days = row.get("schedule_days") or "mon,tue,wed,thu,fri"
    if isinstance(raw_days, str):
        # The column is TEXT, so it may hold a plain list or a Postgres array
        # literal such as {mon,tue}. Splitting the latter on commas leaves the
        # braces attached to the first and last day.
        schedule_days = [d.strip().strip('{}"') for d in raw_days.strip("{}").split(",")]
        schedule_days = [d for d in schedule_days if d]
    else:
        schedule_days = raw_days

    ws = workspace if workspace is not None else {}

    def _ws(key, default=""):
        """Workspace value, falling back to the row for older callers."""
        if key in ws:
            return ws[key]
        return row.get(key, default)

    return {
        "id": row["id"],
        "name": row.get("name") or "Morning Standup",
        "channel_id": row.get("channel_id") or "",
        "schedule_time": row.get("schedule_time") or "09:00",
        "schedule_tz": row.get("schedule_tz") or "UTC",
        "schedule_days": schedule_days,
        "questions": questions,
        "active": row.get("active", True),
        "participants": participants,
        "reminder_minutes": int(row.get("reminder_minutes") or 0),
        # Extended fields — may not be present in all rows
        "report_channel": row.get("report_channel") or "",
        "digest_email": row.get("digest_email") or "",
        "digest_enabled": bool(row.get("digest_enabled")),
        "nudge_missing": bool(row.get("nudge_missing")),
        "nudge_minutes_before": row.get("nudge_minutes_before") or 20,
        "report_time": row.get("report_time") or "",
        "group_by": row.get("group_by") or "member",
        "post_as": row.get("post_as") or "combined",
        "sort_order": row.get("sort_order") or "chronological",
        "edit_window": _HOURS_TO_EDIT_WINDOW.get(_ws("edit_window_hours", 4), "none"),
        "display_avatar": bool(row.get("display_avatar", True)),
        "jira_base_url": _ws("jira_base_url") or "",
        # Not stored: Zendesk autolinking is not implemented. linkify_issues
        # can render it but is never given a URL, and there is no column. The
        # form shows the field as unavailable rather than accepting a value it
        # would throw away.
        "zendesk_base_url": "",
        "github_repo": _ws("github_repo") or "",
        "linear_team": _ws("linear_team") or "",
        "ai_summary_enabled": bool(_ws("ai_summary_enabled", False)),
        "ai_provider": _ws("ai_provider") or "openai",
        "feed_token": _ws("feed_token") or "",
        "feed_public": bool(_ws("feed_public", False)),
        "manager_email": _ws("manager_email") or "",
        "manager_digest_enabled": bool(_ws("manager_digest_enabled", False)),
        "post_to_thread": bool(row.get("post_to_thread", False)),
        "notify_on_report": bool(row.get("notify_on_report", True)),
        "post_summary": bool(row.get("post_summary", False)),
        # #67: an active schedule whose time or timezone the scheduler cannot
        # parse is never registered, so it silently never fires. None when the
        # schedule is fine (or inactive, where not firing is the point).
        "registration_error": schedule_config_error(row) if row.get("active", True) else None,
        # #119: when it next fires, so a standup that runs can be told apart from
        # one that silently never will.
        "next_run": _next_run(row),
    }


# Settings the schedule form shows but that belong to the workspace, not to one
# schedule. Every one of these was accepted by the PUT below, passed to
# update_standup_schedule, and dropped on the floor by its allowlist: the
# dashboard reported success and stored nothing. They are written to
# workspace_config now, which is where their consumers already read them.
_WORKSPACE_SETTING_FIELDS = (
    "ai_summary_enabled",
    "ai_provider",
    "jira_base_url",
    "github_repo",
    "linear_team",
    "manager_email",
    "manager_digest_enabled",
    "feed_token",
    "feed_public",
)

_BOOL_WORKSPACE_FIELDS = ("ai_summary_enabled", "manager_digest_enabled", "feed_public")

# Publishing the workspace's standups is not part of running standups.
_FEED_FIELDS = ("feed_token", "feed_public")

# "Until report time", "4 hours", "No limit" in the form, against the integer
# hours that can_edit_response reads.
_EDIT_WINDOW_TO_HOURS = {"report": 0, "4h": 4, "none": None}
_HOURS_TO_EDIT_WINDOW = {0: "report", 4: "4h"}


def _workspace_settings(team_id: str) -> dict:
    """Workspace-level settings, for merging into a schedule response."""
    try:
        return db.get_workspace_config(team_id) or {}
    except Exception:
        return {}


def _is_workspace_admin() -> bool:
    """True for a full workspace admin, false for a feature admin or member."""
    try:
        return db.get_member_role(session.get("team_id") or "", session.get("user_id") or "") == "admin"
    except Exception:
        return False


def _split_workspace_fields(data: dict) -> dict:
    """Pull the workspace-level settings out of a schedule payload.

    The standup form also carries the public feed switch, which publishes the
    team's standups at an unauthenticated URL. Someone who administers
    standups should not reach that through the form when they cannot reach
    the feed endpoint directly, so those two fields need workspace admin.
    """
    workspace_admin = _is_workspace_admin()
    ws: dict = {}
    for field in _WORKSPACE_SETTING_FIELDS:
        if field not in data:
            continue
        if field in _FEED_FIELDS and not workspace_admin:
            continue
        ws[field] = bool(data[field]) if field in _BOOL_WORKSPACE_FIELDS else data[field]
    if "edit_window" in data:
        ws["edit_window_hours"] = _EDIT_WINDOW_TO_HOURS.get(str(data["edit_window"]), 4)
    return ws


@dashboard_bp.route("/dashboard/api/standups", methods=["GET"])
@_login_required
def api_list_standups():
    team_id = session["team_id"]
    try:
        rows = db.get_standup_schedules(team_id)
        # Merged so the form reads back what was saved. Without this the
        # workspace settings always came back as their defaults, which is why
        # choosing Anthropic and reloading snapped the dropdown to OpenAI.
        ws = _workspace_settings(team_id)
        return jsonify([_schedule_to_standup(r, ws) for r in rows])
    except Exception as exc:
        logger.error("api_list_standups error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/standups", methods=["POST"])
@_admin_required("standup")
def api_create_standup():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    invalid = schedule_payload_error(data)
    if invalid:
        return jsonify({"error": invalid}), 400
    try:
        days = data.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])
        if isinstance(days, list):
            days = ",".join(days)
        row = db.create_standup_schedule(
            team_id,
            name=data.get("name", "Morning Standup"),
            channel_id=data.get("channel_id", ""),
            schedule_time=data.get("schedule_time", "09:00"),
            schedule_tz=data.get("schedule_tz", "UTC"),
            schedule_days=days,
            questions=data.get(
                "questions", ["What did you do yesterday?", "What are you doing today?", "Any blockers?"]
            ),
            participants=data.get("participants", []),
            active=data.get("active", True),
            reminder_minutes=int(data.get("reminder_minutes") or 0),
            post_to_thread=bool(data.get("post_to_thread", False)),
            notify_on_report=bool(data.get("notify_on_report", True)),
            post_summary=_post_summary_default(data),
        )
        return jsonify(_schedule_to_standup(row)), 201
    except Exception as exc:
        logger.error("api_create_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/standups/<standup_id>", methods=["PUT"])
@_admin_required("standup")
def api_update_standup(standup_id: str):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    invalid = schedule_payload_error(data)
    if invalid:
        return jsonify({"error": invalid}), 400
    try:
        kwargs: dict = {}
        for field in (
            "name",
            "channel_id",
            "schedule_time",
            "schedule_tz",
            "questions",
            "participants",
            "active",
            "report_channel",
            "report_time",
            "digest_email",
            "digest_enabled",
            "nudge_missing",
            "nudge_minutes_before",
            "group_by",
        ):
            if field in data:
                kwargs[field] = data[field]
        if "schedule_days" in data:
            days = data["schedule_days"]
            kwargs["schedule_days"] = ",".join(days) if isinstance(days, list) else days
        if "reminder_minutes" in data:
            kwargs["reminder_minutes"] = int(data.get("reminder_minutes") or 0)
        if "post_to_thread" in data:
            kwargs["post_to_thread"] = bool(data["post_to_thread"])
        if "notify_on_report" in data:
            kwargs["notify_on_report"] = bool(data["notify_on_report"])
        if "post_summary" in data:
            kwargs["post_summary"] = bool(data["post_summary"])
        row = db.update_standup_schedule(team_id, int(standup_id), **kwargs)

        # The workspace-level half of the same form.
        ws_fields = _split_workspace_fields(data)
        if ws_fields:
            db.upsert_workspace_config(team_id, **ws_fields)

        return jsonify(_schedule_to_standup(row, _workspace_settings(team_id)))
    except Exception as exc:
        logger.error("api_update_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/standups/<standup_id>", methods=["DELETE"])
@_admin_required("standup")
def api_delete_standup(standup_id: str):
    team_id = session["team_id"]
    try:
        db.delete_standup_schedule(team_id, int(standup_id))
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("api_delete_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/email/subscribe", methods=["GET", "POST"])
def email_subscribe():
    """Record an express opt-in to product update emails.

    The link is in the welcome email, nothing is pre-ticked, and until it is
    pressed the only email anybody gets is about their own install. The record
    is the proof Canadian law asks for, so it keeps when and from where.
    """
    from src.core import mailer  # noqa: PLC0415

    email = (request.args.get("e") or "").strip()
    token = (request.args.get("t") or "").strip()
    if not email or not hmac.compare_digest(token, mailer.unsubscribe_token(email)):
        return _unsubscribe_page("That link is not valid",
                                 "It may have been truncated by your mail client. Write to "
                                 "support@morgenruf.dev and it will be handled by a person."), 400
    try:
        db.grant_email_consent(email, source="welcome-email", ip=request.headers.get("CF-Connecting-IP", ""))
        mailer.sync_contact(email)
    except Exception as exc:
        logger.error("Could not record consent: %s", exc)
        return _unsubscribe_page("Something went wrong",
                                 "Write to support@morgenruf.dev and it will be done by hand."), 500
    return _unsubscribe_page("You are on the list",
                             "About one email a month, when something ships. Every one of them has "
                             "an unsubscribe link, and pressing it stops them immediately.")


@dashboard_bp.route("/email/unsubscribe", methods=["GET", "POST"])
def email_unsubscribe():
    """Stop emailing this address. No login, one click, works from the header.

    Mail clients hit this with POST via List-Unsubscribe-Post, and people click
    it with GET from the footer. Both do the same thing.
    """
    from src.core.mailer import unsubscribe_token  # noqa: PLC0415

    email = (request.args.get("e") or "").strip()
    token = (request.args.get("t") or "").strip()
    if not email or not hmac.compare_digest(token, unsubscribe_token(email)):
        return _unsubscribe_page(
            "That link is not valid",
            "It may have been truncated by your mail client. Write to "
            "support@morgenruf.dev and it will be handled by a person.",
        ), 400
    try:
        db.suppress_email(email)
        db.revoke_email_consent(email)
        from src.core import mailer as _mailer  # noqa: PLC0415

        _mailer.unsync_contact(email)
    except Exception as exc:
        logger.error("unsubscribe failed for one address: %s", exc)
        return _unsubscribe_page(
            "Something went wrong", "Write to support@morgenruf.dev and it will be done by hand."
        ), 500
    return _unsubscribe_page(
        "Unsubscribed",
        "No more email from Morgenruf to this address. The Slack app itself is unaffected and keeps working.",
    )


def _unsubscribe_page(heading: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{heading} — Morgenruf</title></head>
<body style="margin:0;background:#FFFDF8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             display:flex;align-items:center;justify-content:center;min-height:100vh;">
<div style="max-width:440px;padding:32px;text-align:center;">
  <img src="https://morgenruf.dev/logo-mark.png" width="56" height="56" alt="" style="border-radius:12px"/>
  <h1 style="font-size:24px;color:#191B2A;margin:18px 0 10px;">{heading}</h1>
  <p style="font-size:15.5px;color:#5A5E74;line-height:1.6;margin:0 0 22px;">{body}</p>
  <a href="https://morgenruf.dev" style="color:#E0322E;font-weight:600;text-decoration:none;">morgenruf.dev</a>
</div></body></html>"""


# ---------------------------------------------------------------------------
# Me / Role API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/me", methods=["GET"])
@_login_required
def api_me():
    team_id = session["team_id"]
    user_id = session.get("user_id", "")
    try:
        role = db.get_member_role(team_id, user_id)
    except Exception:
        role = "member"
    try:
        modules = sorted(db.module_admin_grants(team_id, user_id))
    except Exception:
        modules = []
    return jsonify(
        {
            "team_id": team_id,
            "user_id": user_id,
            "team_name": session.get("team_name", ""),
            "role": role,
            # Features this person administers without being a workspace admin.
            # An admin administers all of them, which the page derives from the
            # role rather than from a list that would go stale.
            "module_admin": modules,
        }
    )


@dashboard_bp.route("/dashboard/api/members/<user_id>/role", methods=["PUT"])
@_login_required
@_admin_required
def api_set_member_role(user_id: str):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    role = data.get("role", "member")

    # Demoting the last admin leaves nobody who can promote anyone, and every
    # admin-only route shut. The installer still counts as an admin underneath,
    # so this is not strictly a lockout, but it is a foot-gun with no upside.
    if role != "admin":
        try:
            if db.get_member_role(team_id, user_id) == "admin" and db.count_admins(team_id) <= 1:
                return jsonify({"error": "Promote someone else to admin first"}), 400
        except Exception as exc:
            logger.warning("api_set_member_role admin count failed: %s", exc)
    try:
        db.set_member_role(team_id, user_id, role)
        return jsonify({"ok": True, "user_id": user_id, "role": role})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/members/<user_id>/modules/<module>", methods=["PUT", "DELETE"])
@_admin_required
def api_set_module_admin(user_id: str, module: str):
    """Give one person charge of one feature, or take it back.

    This is how a team lead runs the standups and someone else runs a feature
    of their own, without either of them being able to mint API keys or
    publish the workspace's standups. Only a workspace admin hands out a
    grant, including for a feature they have delegated already.

    The feature names come from the registry, so core never knows one by name.
    """
    from src.modules import REGISTRY  # noqa: PLC0415

    team_id = session["team_id"]
    # A feature with nothing to administer cannot be handed to anybody: the
    # grant would sit in the table and change nothing.
    if module not in {spec.name for spec in REGISTRY if getattr(spec, "delegable", False)}:
        return jsonify({"error": "that feature cannot be delegated"}), 404
    try:
        if request.method == "DELETE":
            db.revoke_module_admin(team_id, user_id, module)
        else:
            db.grant_module_admin(team_id, user_id, module, session.get("user_id", ""))
        return jsonify({"ok": True, "user_id": user_id, "module": module, "granted": request.method == "PUT"})
    except Exception as exc:
        logger.error("api_set_module_admin: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Members API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/members", methods=["GET"])
@_login_required
def api_members():
    team_id = session["team_id"]
    token = _get_bot_token()
    if not token:
        return jsonify([])

    # Roles, and who the bot actually holds a row for. This endpoint lists
    # everyone in the Slack workspace, which is right for the participant
    # pickers but meant the Members page said 42 while Analytics said 26 with
    # nothing on either page explaining the difference. Marking each person
    # tells the page which population it is looking at.
    role_map: dict[str, str] = {}
    tracked: set[str] = set()
    try:
        for r in db.get_active_members(team_id):
            role_map[r["user_id"]] = r.get("role", "member")
            tracked.add(r["user_id"])
    except Exception as e:
        logger.warning("Unexpected error in api_members loading role map: %s", e)

    try:
        grants = db.team_module_admins(team_id)
    except Exception as e:
        logger.warning("Unexpected error in api_members loading module grants: %s", e)
        grants = {}

    channel_id = request.args.get("channel_id")

    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=token)

        # If channel_id provided, fetch only that channel's members
        channel_member_ids = None
        if channel_id:
            channel_member_ids = set()
            cursor = None
            while True:
                resp = client.conversations_members(channel=channel_id, limit=500, cursor=cursor or "")
                channel_member_ids.update(resp.get("members", []))
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        # Paginate through all workspace users
        all_users = []
        cursor = None
        while True:
            result = client.users_list(limit=200, cursor=cursor or "")
            all_users.extend(result.get("members", []))
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        members = []
        for u in all_users:
            if not is_human(u):
                continue
            uid = u["id"]
            if channel_member_ids is not None and uid not in channel_member_ids:
                continue
            profile = u.get("profile", {})
            members.append(
                {
                    "id": uid,
                    "name": profile.get("real_name") or u.get("name", ""),
                    "display_name": profile.get("display_name") or u.get("name", ""),
                    "avatar": profile.get("image_48", ""),
                    "email": profile.get("email", ""),
                    "tz": u.get("tz", "UTC"),
                    "role": role_map.get(uid, "member"),
                    "module_admin": sorted(grants.get(uid, ())),
                    # False means: in Slack, but the bot holds no active row,
                    # so they are in no standup and in no participation figure.
                    "tracked": uid in tracked,
                }
            )
        return jsonify(members)
    except Exception as exc:
        logger.error("api_members error: %s", exc)
        # Fall back to DB members
        try:
            rows = db.get_active_members(team_id)
            return jsonify(
                [
                    {
                        "id": r["user_id"],
                        "name": r.get("real_name", ""),
                        # Stored on the last roster sync, so the page still
                        # shows faces and handles when Slack is unreachable.
                        "display_name": r.get("display_name") or "",
                        "avatar": r.get("avatar_url") or "",
                        "email": r.get("email", ""),
                        "tz": r.get("tz", "UTC"),
                        "role": r.get("role", "member"),
                        "module_admin": sorted(grants.get(r["user_id"], ())),
                        "tracked": True,
                    }
                    for r in rows
                ]
            )
        except Exception:
            return jsonify([])


@dashboard_bp.route("/dashboard/api/members/invite", methods=["POST"])
@_login_required
@_admin_required
def api_invite_admin():
    """Look up a Slack user by name/email and grant them admin role."""
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id", "").strip()
    role = data.get("role", "admin")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    token = _get_bot_token()
    if not token:
        return jsonify({"error": "No bot token"}), 500
    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=token)
        info = client.users_info(user=user_id)
        u = info["user"]
        profile = u.get("profile", {})
        db.upsert_member(
            team_id=team_id,
            user_id=user_id,
            real_name=profile.get("real_name") or u.get("name", ""),
            email=profile.get("email", ""),
            tz=u.get("tz", "UTC"),
        )
        db.set_member_role(team_id, user_id, role)
        return jsonify(
            {"ok": True, "user_id": user_id, "role": role, "name": profile.get("real_name") or u.get("name", "")}
        )
    except Exception as exc:
        logger.error("api_invite_admin error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Channels API (helper for dropdowns)
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/channels", methods=["GET"])
@_login_required
def api_channels():
    token = _get_bot_token()
    if not token:
        logger.warning("api_channels: no bot token found for team %s", session.get("team_id"))
        return jsonify([])
    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=token)
        channels = []
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "exclude_archived": True, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = client.users_conversations(**kwargs)
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


def _participation_summary(overview: dict) -> dict:
    """Return the headline participation figures without the per-member rows.

    The denominator travels with the percentage so the UI can say
    "of N enrolled members" rather than showing a bare number.
    """
    return {
        "days": int(overview.get("days") or 7),
        "completion_rate": int(overview.get("completion_rate") or 0),
        "expected": int(overview.get("expected") or 0),
        "completed": int(overview.get("completed") or 0),
        "missed": int(overview.get("missed") or 0),
        "responses": int(overview.get("responses") or 0),
        "total_members": int(overview.get("total_members") or 0),
        "enrolled_members": int(overview.get("enrolled_members") or 0),
        "unenrolled_members": int(overview.get("unenrolled_members") or 0),
        "on_vacation_members": int(overview.get("on_vacation_members") or 0),
        "responding_members": int(overview.get("responding_members") or 0),
    }


@dashboard_bp.route("/dashboard/api/stats", methods=["GET"])
@_login_required
def api_stats():
    team_id = session["team_id"]
    try:
        stats = db.get_dashboard_stats(team_id)
        return jsonify(stats)
    except Exception as exc:
        logger.warning("api_stats error: %s", exc)
        return jsonify(
            {
                "completion_rate": 0,
                "active_members": 0,
                "total_responses": 0,
                "responses_this_week": 0,
                "total_members": 0,
                "enrolled_members": 0,
                "unenrolled_members": 0,
                "on_vacation_members": 0,
                "expected_responses": 0,
                "completed_responses": 0,
                "missed_responses": 0,
                "days": 7,
                "schedules": [],
            }
        )


# Channel names the bot is not a member of, resolved once per process.
# users.conversations only lists channels the bot has joined, so a standup that
# mentions any other channel rendered the raw id: "#C0B3JSAQWPL" instead of a
# name.
_CHANNEL_NAME_CACHE: dict[str, str] = {}
_CHANNEL_MENTION = re.compile(r"<#(C[A-Z0-9]+)(?:\|[^>]*)?>")


def _resolve_channel_names(token: str, standups: list[dict]) -> dict[str, str]:
    """Look up the channels mentioned in these answers, by id."""
    referenced: set[str] = set()
    for row in standups:
        for field in ("yesterday", "today", "blockers"):
            value = row.get(field)
            if value:
                referenced.update(_CHANNEL_MENTION.findall(str(value)))
    if not referenced:
        return {}

    found = {cid: _CHANNEL_NAME_CACHE[cid] for cid in referenced if cid in _CHANNEL_NAME_CACHE}
    missing = referenced - set(found)
    if not missing:
        return found

    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=token)
    except Exception as exc:
        logger.warning("Could not build a client to resolve channel names: %s", exc)
        return found

    # Bounded, so a standup full of mentions cannot turn one page load into
    # dozens of Slack calls.
    for cid in sorted(missing)[:25]:
        try:
            info = client.conversations_info(channel=cid)
            name = (info.get("channel") or {}).get("name")
            if name:
                _CHANNEL_NAME_CACHE[cid] = name
                found[cid] = name
        except Exception as exc:
            # Private, archived, or in another workspace. Nothing to show.
            logger.debug("Could not resolve channel %s: %s", cid, exc)
    return found


def _attach_questions(team_id: str, standups: list[dict]) -> None:
    """Label each standup with the questions it was actually asked.

    The report hardcoded "Yesterday", "Today" and "Blockers", which are the
    default questions and not necessarily the ones a schedule asks. A schedule
    asking "Availability in Hours" third had "4:30 Hrs" printed under a red
    Blockers heading. Same mistake as counting that answer as a blocker, which
    `blockers.py` already fixed on the computing side.

    `schedule_id` on the standup is the reliable answer, but it only exists on
    rows written since it was added. For older rows, fall back to the
    schedules the person belongs to, and only when they all ask the same
    thing: someone in a morning and an evening standup with different
    questions is genuinely ambiguous, so those keep the generic labels rather
    than being given a guess.
    """
    if not standups:
        return
    try:
        schedules = db.get_standup_schedules(team_id)
    except Exception as exc:
        logger.warning("Could not load schedules for report labels: %s", exc)
        return

    by_id: dict[int, list] = {}
    per_user: dict[str, list[list]] = {}
    for sched in schedules:
        questions = sched.get("questions") or []
        if not questions:
            continue
        by_id[int(sched.get("id") or 0)] = questions
        if not sched.get("active"):
            continue
        for user_id in sched.get("participants") or []:
            per_user.setdefault(user_id, []).append(questions)

    def unanimous(user_id: str) -> list | None:
        found = per_user.get(user_id) or []
        if not found:
            return None
        first = found[0]
        return first if all(q == first for q in found) else None

    for row in standups:
        schedule_id = row.get("schedule_id")
        questions = by_id.get(int(schedule_id)) if schedule_id else None
        row["questions"] = questions or unanimous(row.get("user_id", "")) or None


@dashboard_bp.route("/dashboard/api/reports", methods=["GET"])
@_login_required
def api_reports():
    """Return standup history with participation stats, filterable by date/member."""
    team_id = session["team_id"]
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    user_id_filter = request.args.get("user_id")
    try:
        standups = db.get_standups(
            team_id,
            from_date=date_from or None,
            to_date=date_to or None,
            days=30,
        )
        if user_id_filter:
            standups = [s for s in standups if s.get("user_id") == user_id_filter]

        _attach_questions(team_id, standups)
        channel_names = _resolve_channel_names(token, standups) if (token := _get_bot_token()) else {}

        days = 7
        if date_from:
            try:
                from datetime import datetime as _dt

                d = _dt.fromisoformat(date_from)
                days = max(1, (_dt.utcnow() - d).days + 1)
            except Exception as e:
                logger.warning("Unexpected error in api_reports parsing date_from: %s", e)
        overview = db.get_participation_overview(team_id, days=days)
        total_days = days

        member_summary = []
        for p in overview.get("members") or []:
            expected = int(p.get("expected") or 0)
            rate = int(p.get("completion_rate") or 0)
            member_summary.append(
                {
                    "user_id": p.get("user_id", ""),
                    "name": p.get("real_name") or p.get("user_id", ""),
                    "responses": int(p.get("responses") or 0),
                    "completed": int(p.get("completed") or 0),
                    "expected": expected,
                    # "total" used to be the length of the window, which asked
                    # a three-day-a-week member for five standups. It is now
                    # what that member was actually asked for.
                    "total": expected,
                    "enrolled": bool(p.get("enrolled")),
                    "on_vacation": bool(p.get("on_vacation")),
                    "schedules": p.get("schedules") or [],
                    "completion_rate": rate,
                    "stars": int(rate * 5 / 100 + 0.5) if expected else 0,
                }
            )

        return jsonify(
            {
                "standups": standups,
                "channel_names": channel_names,
                "participation": member_summary,
                "total_days": total_days,
                "summary": _participation_summary(overview),
                "schedules": overview.get("schedules") or [],
            }
        )
    except Exception as exc:
        logger.error("api_reports error: %s", exc)
        return jsonify(
            {
                "standups": [],
                "participation": [],
                "total_days": 7,
                "summary": _participation_summary({}),
                "schedules": [],
            }
        )


# ---------------------------------------------------------------------------
# Webhooks API
# ---------------------------------------------------------------------------

# Bytes of entropy in a signing secret. token_urlsafe(32) yields 43 characters.
_WEBHOOK_SECRET_BYTES = 32


def _new_webhook_secret() -> str:
    """Generate a signing secret. The raw value is handed to the operator once."""
    return secrets.token_urlsafe(_WEBHOOK_SECRET_BYTES)


def _iso(value):
    """Render a timestamp for JSON, passing through anything already a string."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _public_webhook(hook: dict) -> dict:
    """Strip the signing secret out of a webhook row before it leaves the server.

    The raw secret is returned exactly twice in its life, by the create and
    rotate endpoints, and never again. Listings get ``has_secret`` plus a short
    prefix, enough for the UI to tell two secrets apart and to warn about rows
    that predate signing and are still delivering unsigned.
    """
    secret = hook.get("secret") or ""
    return {
        "id": hook.get("id"),
        "url": hook.get("webhook_url"),
        "webhook_url": hook.get("webhook_url"),
        "events": list(hook.get("events") or []),
        "has_secret": bool(secret),
        "secret_prefix": secret[:6] if secret else None,
        "signed": bool(secret),
        "created_at": _iso(hook.get("created_at")),
    }


def _clean_events(raw) -> tuple[list[str] | None, str | None]:
    """Validate an ``events`` field from a request body.

    Returns ``(events, error)``. ``events`` is None when the caller did not
    supply the field at all, which means "leave it alone".
    """
    if raw is None:
        return None, None
    if not isinstance(raw, list):
        return None, "events must be a list"
    if not raw:
        return None, "events must not be empty"
    cleaned: list[str] = []
    for item in raw:
        name = db.normalize_webhook_event(str(item))
        if name not in db.WEBHOOK_EVENTS:
            return None, f"Unknown event {item!r}. Valid events: {', '.join(db.WEBHOOK_EVENTS)}"
        if name not in cleaned:
            cleaned.append(name)
    return cleaned, None


@dashboard_bp.route("/dashboard/api/webhooks", methods=["GET"])
@_login_required
def api_list_webhooks():
    team_id = session["team_id"]
    try:
        hooks = db.get_webhooks(team_id)
        return jsonify([_public_webhook(h) for h in hooks])
    except Exception as exc:
        logger.warning("api_list_webhooks error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/webhooks/events", methods=["GET"])
@_login_required
def api_webhook_events():
    """List the event names a webhook can subscribe to."""
    return jsonify({"events": list(db.WEBHOOK_EVENTS), "default": list(db.DEFAULT_WEBHOOK_EVENTS)})


@dashboard_bp.route("/dashboard/api/webhooks", methods=["POST"])
@_admin_required
def api_add_webhook():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    url_val = data.get("url", "").strip()
    if not url_val:
        return jsonify({"error": "url is required"}), 400
    if not _is_safe_webhook_url(url_val):
        return jsonify({"error": "Invalid or unsafe webhook URL"}), 400
    events, err = _clean_events(data.get("events"))
    if err:
        return jsonify({"error": err}), 400
    try:
        secret = _new_webhook_secret()
        hook = db.add_webhook(team_id, url_val, secret=secret, events=events)
        body = _public_webhook(hook)
        # The only time the raw secret is ever returned. Store it now or rotate.
        body["secret"] = secret
        body["secret_shown_once"] = True
        return jsonify(body), 201
    except Exception as exc:
        logger.error("api_add_webhook error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/webhooks/<hook_id>", methods=["PATCH"])
@_admin_required
def api_update_webhook(hook_id: str):
    """Update a webhook's URL and/or its event subscription."""
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}

    url_val = data.get("url")
    if url_val is not None:
        url_val = str(url_val).strip()
        if not url_val:
            return jsonify({"error": "url must not be empty"}), 400
        if not _is_safe_webhook_url(url_val):
            return jsonify({"error": "Invalid or unsafe webhook URL"}), 400

    events, err = _clean_events(data.get("events"))
    if err:
        return jsonify({"error": err}), 400
    if url_val is None and events is None:
        return jsonify({"error": "Nothing to update"}), 400

    try:
        hook = db.update_webhook(team_id, int(hook_id), url=url_val, events=events)
        if not hook:
            return jsonify({"error": "Webhook not found"}), 404
        return jsonify(_public_webhook(hook))
    except ValueError:
        return jsonify({"error": "Invalid webhook id"}), 400
    except Exception as exc:
        logger.error("api_update_webhook error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/webhooks/<hook_id>/rotate", methods=["POST"])
@_admin_required
def api_rotate_webhook_secret(hook_id: str):
    """Issue a new signing secret and return it once.

    Rotating is also how a pre-signing webhook adopts signing: those rows keep
    a NULL secret and deliver unsigned until an operator rotates deliberately,
    because turning on signatures behind the receiver's back would break a
    strict verifier that has never been given a key.
    """
    team_id = session["team_id"]
    try:
        secret = _new_webhook_secret()
        hook = db.rotate_webhook_secret(team_id, int(hook_id), secret)
        if not hook:
            return jsonify({"error": "Webhook not found"}), 404
        body = _public_webhook(hook)
        body["secret"] = secret
        body["secret_shown_once"] = True
        return jsonify(body)
    except ValueError:
        return jsonify({"error": "Invalid webhook id"}), 400
    except Exception as exc:
        logger.error("api_rotate_webhook_secret error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/webhooks/<hook_id>/test", methods=["POST"])
@_admin_required
def api_test_webhook(hook_id: str):
    """Send a synthetic event through the real signing and logging path."""
    team_id = session["team_id"]
    try:
        hook = db.get_webhook(team_id, int(hook_id))
        if not hook:
            return jsonify({"error": "Webhook not found"}), 404
        if not _is_safe_webhook_url(hook.get("webhook_url") or ""):
            return jsonify({"error": "Invalid or unsafe webhook URL"}), 400

        from datetime import datetime, timezone  # noqa: PLC0415

        from src.modules.standup.handlers import deliver_webhook  # noqa: PLC0415

        events = list(hook.get("events") or db.DEFAULT_WEBHOOK_EVENTS)
        event_type = events[0] if events else "standup.completed"
        payload = {
            "team_id": team_id,
            "test": True,
            "message": "Test delivery from the Morgenruf dashboard.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        result = deliver_webhook(hook, event_type, payload, team_id=team_id)
        return jsonify(result)
    except ValueError:
        return jsonify({"error": "Invalid webhook id"}), 400
    except Exception as exc:
        logger.error("api_test_webhook error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/webhooks/<hook_id>/deliveries", methods=["GET"])
@_login_required
def api_webhook_deliveries(hook_id: str | None = None):
    """Recent delivery attempts, newest first, for the team or one webhook."""
    team_id = session["team_id"]
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    try:
        webhook_id = int(hook_id) if hook_id is not None else None
    except ValueError:
        return jsonify({"error": "Invalid webhook id"}), 400
    try:
        rows = db.get_webhook_deliveries(team_id, webhook_id=webhook_id, limit=limit)
        for row in rows:
            row["created_at"] = _iso(row.get("created_at"))
        return jsonify(rows)
    except Exception as exc:
        logger.warning("api_webhook_deliveries error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/webhooks/<hook_id>", methods=["DELETE"])
@_admin_required
def api_delete_webhook(hook_id: str):
    team_id = session["team_id"]
    try:
        db.delete_webhook(team_id, int(hook_id))
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
    """Per-member participation for the last N days.

    Members in no active schedule stay in the list with `enrolled` false and an
    expected count of 0, so the UI can render them as "not enrolled" instead of
    a misleading "0 of 7".
    """
    team_id = session["team_id"]
    days = int(request.args.get("days", 7))
    try:
        overview = db.get_participation_overview(team_id, days)
        stats = overview["members"]
        for row in stats:
            last = row.get("last_standup")
            if last is not None and hasattr(last, "isoformat"):
                row["last_standup"] = last.isoformat()
            row["responses"] = int(row.get("responses") or 0)
            row["days_with_blockers"] = int(row.get("days_with_blockers") or 0)
            row["expected"] = int(row.get("expected") or 0)
            row["completed"] = int(row.get("completed") or 0)
            row["missed"] = int(row.get("missed") or 0)
            row["completion_rate"] = int(row.get("completion_rate") or 0)
            row["enrolled"] = bool(row.get("enrolled"))
            row["on_vacation"] = bool(row.get("on_vacation"))
            row["schedules"] = row.get("schedules") or []
            row["schedule_ids"] = [int(s) for s in (row.get("schedule_ids") or [])]
        # Return the workspace totals alongside the rows so the page shows the
        # same completion rate as the Standups card. The client used to average
        # the per-member ratios, which weights a member with one expected
        # standup the same as one with ten and produced a different headline for
        # the same window (#85).
        return jsonify(
            {
                "members": stats,
                "days": overview["days"],
                # The dates the grid draws columns for. This endpoint builds its
                # payload from an explicit key list, so anything added to
                # compute_participation has to be named here too or the client
                # silently gets nothing.
                "window_days": overview.get("window_days") or [],
                "expected": overview["expected"],
                "completed": overview["completed"],
                "missed": overview["missed"],
                "completion_rate": overview["completion_rate"],
                "enrolled_members": overview["enrolled_members"],
                "unenrolled_members": overview["unenrolled_members"],
                "on_vacation_members": overview["on_vacation_members"],
                "schedules": overview["schedules"],
            }
        )
    except Exception as exc:
        logger.error("api_analytics error: %s", exc)
        return jsonify({"members": [], "schedules": []})


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
        fieldnames=[
            "standup_date",
            "user_id",
            "yesterday",
            "today",
            "blockers",
            "has_blockers",
            "submitted_at",
            "mood",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "standup_date": row.get("standup_date", ""),
                "user_id": row.get("user_id", ""),
                "yesterday": row.get("yesterday", ""),
                "today": row.get("today", ""),
                "blockers": row.get("blockers", ""),
                "has_blockers": row.get("has_blockers", ""),
                "submitted_at": row.get("submitted_at", ""),
                "mood": row.get("mood", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=standups-{team_id}.csv"},
    )


# ── Templates API ──────────────────────────────────────────────────────────


@dashboard_bp.route("/dashboard/api/templates", methods=["GET"])
@_login_required
def api_templates():
    from src.modules.standup.templates_library import TEMPLATES  # noqa: PLC0415

    return jsonify(TEMPLATES)


# ── Workflow Rules API ──────────────────────────────────────────────────────


@dashboard_bp.route("/dashboard/api/rules", methods=["GET"])
@_login_required
def api_list_rules():
    team_id = session["team_id"]
    try:
        from src.modules.standup.workflow import get_rules  # noqa: PLC0415

        rules = get_rules(team_id)
        return jsonify(rules)
    except Exception as exc:
        logger.error("api_list_rules: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/rules", methods=["POST"])
@_admin_required("standup")
def api_create_rule():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        from src.modules.standup.workflow import save_rule  # noqa: PLC0415

        rule_id = save_rule(
            team_id=team_id,
            name=data.get("name", ""),
            trigger=data.get("trigger", ""),
            condition_value=data.get("condition_value") or None,
            action=data.get("action", ""),
            action_target=data.get("action_target", ""),
            action_message=data.get("action_message") or None,
        )
        if rule_id is None:
            return jsonify({"error": "Could not save rule"}), 500
        return jsonify({"id": rule_id}), 201
    except Exception as exc:
        logger.error("api_create_rule: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/rules/<int:rule_id>", methods=["DELETE"])
@_admin_required("standup")
def api_delete_rule(rule_id: int):
    team_id = session["team_id"]
    try:
        from src.modules.standup.workflow import delete_rule  # noqa: PLC0415

        delete_rule(rule_id, team_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Public Feed ─────────────────────────────────────────────────────────────


@dashboard_bp.route("/feed/<token>")
def public_feed(token: str):
    from datetime import date  # noqa: PLC0415

    config = db.get_workspace_by_feed_token(token)
    if not config or not config.get("feed_public"):
        return "<h2>Feed not found or not public.</h2>", 404
    team_id = config["team_id"]
    standups = db.get_standups(team_id, days=1)
    today = date.today().strftime("%A, %B %-d, %Y")
    return render_template("feed.html", standups=standups, config=config, today=today)


@dashboard_bp.route("/dashboard/api/feed-token", methods=["POST"])
@_admin_required
def api_generate_feed_token():
    team_id = session["team_id"]
    token = secrets.token_urlsafe(24)
    db.upsert_workspace_config(team_id, feed_token=token, feed_public=True)
    app_url = os.environ.get("APP_URL", "")
    return jsonify({"token": token, "url": f"{app_url}/feed/{token}"})


@dashboard_bp.route("/dashboard/api/feed-token", methods=["DELETE"])
@_admin_required
def api_disable_feed():
    team_id = session["team_id"]
    db.upsert_workspace_config(team_id, feed_public=False)
    return jsonify({"ok": True})


# ── MCP API Key management ───────────────────────────────────────────────────


@dashboard_bp.route("/dashboard/api/mcp/keys", methods=["GET"])
@_login_required
def api_get_mcp_keys():
    team_id = session["team_id"]
    keys = db.get_mcp_keys(team_id)
    return jsonify({"keys": keys})


@dashboard_bp.route("/dashboard/api/mcp/keys", methods=["POST"])
@_admin_required
def api_create_mcp_key():
    team_id = session["team_id"]
    name = request.json.get("name", "Default") if request.json else "Default"
    key = db.generate_mcp_key(team_id, name)
    return jsonify({"key": key, "message": "Save this key — it won't be shown again!"})


@dashboard_bp.route("/dashboard/api/mcp/keys/<int:key_id>", methods=["DELETE"])
@_admin_required
def api_revoke_mcp_key(key_id: int):
    team_id = session["team_id"]
    db.revoke_mcp_key(key_id, team_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Module toggles
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/modules", methods=["GET"])
@_login_required
def api_list_modules():
    """Every registered module, with whether it is active for this workspace.

    The registry is read lazily so core keeps no import-time dependency on any
    module.
    """
    from src.core.modules import active_modules, deploy_allowlist  # noqa: PLC0415
    from src.modules import REGISTRY  # noqa: PLC0415

    team_id = session["team_id"]
    granted = db.granted_scopes(team_id)
    settings = db.module_settings(team_id)
    allowlist = deploy_allowlist()
    active = {m.name for m in active_modules(REGISTRY, granted, settings, allowlist)}
    return jsonify(
        [
            {
                "name": spec.name,
                "active": spec.name in active,
                "enabled": settings.get(spec.name, spec.default_enabled),
                "required_scopes": list(spec.required_scopes),
                "missing_scopes": sorted(set(spec.required_scopes) - set(granted)),
                "available": allowlist is None or spec.name in allowlist,
                # Whether the Members page may offer this as a grant.
                "delegable": bool(getattr(spec, "delegable", False)),
                "nav": [{"label": n.label, "path": n.path} for n in spec.nav],
            }
            for spec in REGISTRY
        ]
    )


@dashboard_bp.route("/dashboard/api/modules/<name>", methods=["POST"])
@_admin_required
def api_set_module(name: str):
    """Enable or disable one module for this workspace.

    Enabling a module whose scopes are not granted returns 409 rather than
    silently doing nothing, so the dashboard can offer a re-authorise link
    instead of a toggle that appears to work.
    """
    from src.modules import REGISTRY  # noqa: PLC0415

    team_id = session["team_id"]
    spec = next((s for s in REGISTRY if s.name == name), None)
    if spec is None:
        return jsonify({"error": "unknown module"}), 404
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    if enabled and not db.has_scopes(team_id, spec.required_scopes):
        return jsonify(
            {
                "error": "missing_scopes",
                "required": list(spec.required_scopes),
                "reauthorise_url": "/install",
            }
        ), 409
    db.set_module_enabled(team_id, name, enabled)
    return jsonify({"module": name, "enabled": enabled})
