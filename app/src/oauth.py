"""OAuth 2.0 Flask blueprint — install, callback, and health routes."""

from __future__ import annotations

import logging
import os

from flask import Blueprint, redirect, request, jsonify, session
from markupsafe import escape
from slack_sdk import WebClient
from slack_sdk.oauth import AuthorizeUrlGenerator

import db
from mailer import send_welcome_email

logger = logging.getLogger(__name__)

oauth_bp = Blueprint("oauth", __name__)

_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET", "")
_APP_URL = os.environ.get("APP_URL", "http://localhost:3000")

_SCOPES = [
    "channels:read",
    "chat:write",
    "im:history",
    "im:read",
    "im:write",
    "users:read",
    "users:read.email",
]

_url_generator = AuthorizeUrlGenerator(
    client_id=_CLIENT_ID,
    scopes=_SCOPES,
    redirect_uri=f"{_APP_URL}/oauth/callback",
)


@oauth_bp.route("/")
def index():
    return jsonify({"name": "morgenruf", "version": "1.0.0", "status": "ok"})


@oauth_bp.route("/install")
def install():
    """Redirect the browser to the Slack OAuth authorisation page."""
    state = os.urandom(16).hex()
    session['oauth_state'] = state
    url = _url_generator.generate(state=state)
    return redirect(url)


@oauth_bp.route("/oauth/callback")
def oauth_callback():
    """Exchange the OAuth code for a bot token and store the installation."""
    incoming_state = request.args.get("state", "")
    if not incoming_state or incoming_state != session.pop("oauth_state", None):
        return "Invalid state parameter", 400

    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        logger.warning("OAuth flow returned error: %s", error)
        return f"<h3>Installation cancelled: {escape(error)}</h3>", 400

    if not code:
        logger.warning("OAuth callback received with no code")
        return "<h3>Missing authorisation code</h3>", 400

    client = WebClient()
    try:
        resp = client.oauth_v2_access(
            client_id=_CLIENT_ID,
            client_secret=_CLIENT_SECRET,
            code=code,
            redirect_uri=f"{_APP_URL}/oauth/callback",
        )
    except Exception as exc:
        logger.error("oauth_v2_access failed: %s", exc)
        return "<h3>OAuth exchange failed — please try again</h3>", 500

    team_id: str = resp["team"]["id"]
    team_name: str = resp["team"]["name"]
    bot_token: str = resp["access_token"]
    bot_user_id: str = resp["bot_user_id"]
    app_id: str = resp["app_id"]
    authed_user_id: str = resp.get("authed_user", {}).get("id", "")

    # Persist installation
    try:
        db.save_installation(
            team_id=team_id,
            team_name=team_name,
            bot_token=bot_token,
            bot_user_id=bot_user_id,
            app_id=app_id,
            installed_by_user_id=authed_user_id,
        )
        db.upsert_workspace_config(team_id)
    except Exception as exc:
        logger.error("Failed to persist installation for %s: %s", team_id, exc)
        # Don't fail the flow — continue to send welcome messages

    # Send welcome DM to the installing user
    if authed_user_id:
        try:
            bot_client = WebClient(token=bot_token)
            dm = bot_client.conversations_open(users=authed_user_id)
            dm_channel = dm["channel"]["id"]
            bot_client.chat_postMessage(
                channel=dm_channel,
                text=(
                    "👋 Welcome to Morgenruf! I'll ping you every morning for your standup. "
                    "Type `help` to see what I can do."
                ),
            )
        except Exception as exc:
            logger.warning("Could not send welcome DM to %s: %s", authed_user_id, exc)

    # Send welcome email (best-effort)
    _try_send_welcome_email(bot_token, team_name, authed_user_id)

    # Register scheduler job for this workspace
    _schedule_workspace(team_id, bot_token)

    logger.info("Installation complete for team %s (%s)", team_id, team_name)
    # Store team in session and redirect to dashboard
    session["team_id"] = team_id
    session["team_name"] = team_name
    return redirect(f"{_APP_URL}/dashboard")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_send_welcome_email(bot_token: str, team_name: str, user_id: str) -> None:
    if not user_id:
        return
    try:
        bot_client = WebClient(token=bot_token)
        info = bot_client.users_info(user=user_id)
        profile = info["user"]["profile"]
        email = profile.get("email", "")
        real_name = profile.get("real_name", user_id)
        if email:
            send_welcome_email(to_email=email, team_name=team_name, installed_by=real_name)
    except Exception as exc:
        logger.warning("Could not retrieve user email for welcome message: %s", exc)


def _schedule_workspace(team_id: str, bot_token: str) -> None:
    """Register a scheduler job for a newly installed workspace."""
    try:
        from scheduler import get_scheduler, register_workspace_job  # noqa: PLC0415

        scheduler = get_scheduler()
        if scheduler is None:
            return
        config = db.get_workspace_config(team_id) or {}
        register_workspace_job(scheduler, team_id, bot_token, config)
    except Exception as exc:
        logger.warning("Could not register scheduler job for %s: %s", team_id, exc)
