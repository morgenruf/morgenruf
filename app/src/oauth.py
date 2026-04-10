"""OAuth 2.0 Flask blueprint — install, callback, and health routes."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone as tz

import db
from flask import Blueprint, jsonify, redirect, request, session
from mailer import send_welcome_email
from markupsafe import escape
from slack_sdk import WebClient
from slack_sdk.oauth import AuthorizeUrlGenerator

logger = logging.getLogger(__name__)

oauth_bp = Blueprint("oauth", __name__)

_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET", "")
_APP_URL = os.environ.get("APP_URL", "http://localhost:3000")

_SCOPES = [
    "channels:read",
    "chat:write",
    "commands",
    "groups:read",
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


def _state_secret() -> bytes:
    key = os.environ.get("FLASK_SECRET_KEY", "fallback-insecure-key")
    return key.encode() if isinstance(key, str) else key


def _make_state() -> str:
    """Generate a self-contained HMAC-signed state token (no session needed)."""
    nonce = os.urandom(16).hex()
    ts = str(int(time.time()))
    payload = f"{ts}.{nonce}"
    sig = hmac.new(_state_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_state(state: str) -> bool:
    """Verify HMAC-signed state token. Accepts tokens up to 10 minutes old."""
    try:
        ts_str, nonce, sig = state.rsplit(".", 2)
        payload = f"{ts_str}.{nonce}"
        expected = hmac.new(_state_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False
        age = int(time.time()) - int(ts_str)
        return 0 <= age <= 600  # 10 minute window
    except Exception:
        return False


@oauth_bp.route("/")
def index():
    return jsonify({"name": "morgenruf", "version": "1.1.3", "status": "ok"})


@oauth_bp.route("/install")
def install():
    """Redirect the browser to the Slack OAuth authorisation page."""
    state = _make_state()
    url = _url_generator.generate(state=state)
    return redirect(url)


@oauth_bp.route("/oauth/callback")
def oauth_callback():
    """Exchange the OAuth code for a bot token and store the installation."""
    incoming_state = request.args.get("state", "")
    if incoming_state and not _verify_state(incoming_state):
        logger.warning("OAuth state validation failed: %r", incoming_state)
        return "Invalid state parameter", 400
    if not incoming_state:
        logger.warning("OAuth callback received without state — proceeding (direct install flow)")

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
    refresh_token: str = resp.get("refresh_token", "")
    expires_in: int = resp.get("expires_in", 0)

    # Compute absolute expiry timestamp
    expires_at_str = None
    if expires_in > 0:
        expires_at_str = datetime.fromtimestamp(
            time.time() + expires_in, tz=tz.utc
        ).isoformat()

    # Persist installation
    is_new_install = False
    try:
        is_new_install = db.save_installation(
            team_id=team_id,
            team_name=team_name,
            bot_token=bot_token,
            bot_user_id=bot_user_id,
            app_id=app_id,
            installed_by_user_id=authed_user_id,
            bot_refresh_token=refresh_token or None,
            bot_token_expires_at=expires_at_str,
        )
        db.upsert_workspace_config(team_id)
    except Exception as exc:
        logger.error("Failed to persist installation for %s: %s", team_id, exc)
        # Don't fail the flow — continue to send welcome messages

    # Grant admin role to the installing user
    if authed_user_id:
        try:
            db.ensure_admin(team_id, authed_user_id)
        except Exception as exc:
            logger.warning("Could not set admin role: %s", exc)

    # Send welcome DM and email only on first install, not on reinstall
    if is_new_install and authed_user_id:
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
    # Set session and pass team_id in URL as fallback for proxies that drop cookies
    session["team_id"] = team_id
    session["team_name"] = team_name
    session["user_id"] = authed_user_id
    token = _make_login_token(team_id, authed_user_id)
    return redirect(f"{_APP_URL}/dashboard?t={token}")


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


def _make_login_token(team_id: str, user_id: str = "") -> str:
    """Short-lived HMAC token to bootstrap dashboard session via URL."""
    ts = str(int(time.time()))
    payload = f"{ts}.{team_id}|{user_id}"
    sig = hmac.new(_state_secret(), payload.encode(), hashlib.sha256).hexdigest()
    import base64

    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def verify_login_token(token: str) -> tuple[str, str] | None:
    """Verify login token, return (team_id, user_id) if valid (5 min window).

    Returns None if invalid. user_id may be empty for tokens issued before
    this version.
    """
    try:
        import base64

        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        ts_str, team_user, sig = decoded.split(".", 2)
        payload = f"{ts_str}.{team_user}"
        expected = hmac.new(_state_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if int(time.time()) - int(ts_str) > 300:
            return None
        if "|" in team_user:
            team_id, user_id = team_user.split("|", 1)
        else:
            team_id, user_id = team_user, ""
        return team_id, user_id
    except Exception:
        return None


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
