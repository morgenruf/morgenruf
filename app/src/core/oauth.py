"""OAuth 2.0 Flask blueprint — install, callback, and health routes."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from datetime import datetime
from datetime import timezone as tz

from flask import Blueprint, jsonify, redirect, request, session
from slack_sdk import WebClient
from slack_sdk.oauth import AuthorizeUrlGenerator

import src.core.db as db
from src.core import rate_limit
from src.core.scopes import BOT_SCOPES

logger = logging.getLogger(__name__)

oauth_bp = Blueprint("oauth", __name__)

_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET", "")
_APP_URL = os.environ.get("APP_URL", "http://localhost:3000")

_SCOPES = list(BOT_SCOPES)

_url_generator = AuthorizeUrlGenerator(
    client_id=_CLIENT_ID,
    scopes=_SCOPES,
    redirect_uri=f"{_APP_URL}/oauth/callback",
)


# Resolved once per process. When FLASK_SECRET_KEY is unset we fall back to a
# random value rather than a constant: a predictable state secret would let an
# attacker mint their own OAuth state and defeat the CSRF check on install.
# A random key means state tokens do not survive a restart, which costs an
# in-flight install its callback and is the safe direction to fail in.
_FALLBACK_STATE_SECRET = os.urandom(32)


def _state_secret() -> bytes:
    key = os.environ.get("FLASK_SECRET_KEY")
    if not key:
        logger.warning("FLASK_SECRET_KEY not set, signing OAuth state with a per-process random key")
        return _FALLBACK_STATE_SECRET
    return key.encode() if isinstance(key, str) else key


# Every token this module signs carries its purpose inside the HMAC input, so
# an OAuth state can never be replayed as a dashboard login token or the other
# way round, even though both share one key.
def _sign(purpose: str, payload: str) -> str:
    return hmac.new(_state_secret(), f"{purpose}|{payload}".encode(), hashlib.sha256).hexdigest()


def _make_state(nonce: str | None = None) -> str:
    """Generate an HMAC-signed state token carrying `nonce`.

    /install also stores the nonce in the browser's session, and the callback
    only accepts a state whose nonce matches. That binds the flow to the
    browser that started it, so an attacker cannot hand a victim a callback
    link carrying the attacker's own code (login CSRF).
    """
    nonce = nonce or os.urandom(16).hex()
    ts = str(int(time.time()))
    payload = f"{ts}.{nonce}"
    return f"{payload}.{_sign('state', payload)}"


def _state_nonce(state: str) -> str | None:
    """Return the nonce of a valid state token (at most 10 minutes old), else None."""
    try:
        ts_str, nonce, sig = state.rsplit(".", 2)
        payload = f"{ts_str}.{nonce}"
        if not hmac.compare_digest(_sign("state", payload), sig):
            return None
        age = int(time.time()) - int(ts_str)
        return nonce if 0 <= age <= 600 else None
    except Exception:
        return None


def _verify_state(state: str) -> bool:
    """Verify HMAC-signed state token. Accepts tokens up to 10 minutes old."""
    return _state_nonce(state) is not None


_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def clean_ref(raw: str | None) -> str:
    """The ?ref= of an install link, or "" when it is missing or not a plain tag."""
    ref = (raw or "").strip().lower()
    return ref if _REF_RE.fullmatch(ref) else ""


@oauth_bp.route("/")
def index():
    from src.core.version import APP_VERSION  # noqa: PLC0415

    return jsonify({"name": "morgenruf", "version": APP_VERSION, "status": "ok"})


@oauth_bp.route("/install")
def install():
    """Redirect the browser to the Slack OAuth authorisation page."""
    nonce = os.urandom(16).hex()
    session["oauth_nonce"] = nonce
    session["install_ref"] = clean_ref(request.args.get("ref"))
    url = _url_generator.generate(state=_make_state(nonce))
    return redirect(url)


@oauth_bp.route("/oauth/callback")
@rate_limit.rate_limited(rate_limit.OAUTH_CALLBACK)
def oauth_callback():
    """Exchange the OAuth code for a bot token and store the installation."""
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        logger.warning("OAuth flow returned error: %s", error)
        return redirect("/auth/result?status=denied", code=303)

    incoming_state = request.args.get("state", "")
    if not incoming_state:
        # An install started on Slack's side arrives without our state. Send
        # it through /install so it picks up a state bound to this browser;
        # the code it carried is never exchanged.
        logger.info("OAuth callback without state, restarting through /install")
        return redirect("/install", code=303)
    expected_nonce = session.pop("oauth_nonce", None)
    nonce = _state_nonce(incoming_state)
    if nonce is None or not expected_nonce or not hmac.compare_digest(nonce, expected_nonce):
        logger.warning("OAuth state validation failed")
        return redirect("/auth/result?status=invalid", code=303)

    if not code:
        logger.warning("OAuth callback received with no code")
        return redirect("/auth/result?status=error", code=303)

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
        return redirect("/auth/result?status=error", code=303)

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
        expires_at_str = datetime.fromtimestamp(time.time() + expires_in, tz=tz.utc).isoformat()

    # Persist installation
    is_new_install = False
    try:
        db.reactivate_installation(team_id)
        is_new_install = db.save_installation(
            team_id=team_id,
            team_name=team_name,
            bot_token=bot_token,
            bot_user_id=bot_user_id,
            app_id=app_id,
            installed_by_user_id=authed_user_id,
            bot_refresh_token=refresh_token or None,
            bot_token_expires_at=expires_at_str,
            granted_scopes=db.parse_scope_field(resp.get("scope")),
        )
        db.upsert_workspace_config(team_id)
    except Exception as exc:
        logger.error("Failed to persist installation for %s: %s", team_id, exc)
        # Don't fail the flow — continue to send welcome messages
    else:
        # Only a new install is tagged: sign-in runs through the same flow,
        # and a member signing in from a tagged link did not install anything.
        install_ref = session.get("install_ref", "")
        if install_ref and is_new_install:
            try:
                db.set_install_source(team_id, install_ref)
            except Exception:
                logger.warning("Could not record the install source for %s", team_id)

    # Admin goes to whoever first installs the app, and to Slack's own admins
    # and owners. Anyone else finishing OAuth is only signing in: dashboard
    # sign-in runs through this same flow, so granting admin here to every
    # caller made any member of a workspace an admin with one click.
    if authed_user_id and (is_new_install or _is_slack_admin(bot_token, authed_user_id)):
        try:
            db.ensure_admin(team_id, authed_user_id)
        except Exception as exc:
            logger.warning("Could not set admin role: %s", exc)

    # Welcome DM only on first install, not on reinstall. No email: the DM
    # offers one, and nothing goes to the installer's Slack address unless
    # they press the button (src/core/email_consent.py).
    if is_new_install and authed_user_id:
        try:
            bot_client = WebClient(token=bot_token)
            dm = bot_client.conversations_open(users=authed_user_id)
            dm_channel = dm["channel"]["id"]
            bot_client.chat_postMessage(channel=dm_channel, text=WELCOME_TEXT, blocks=_welcome_blocks())
        except Exception as exc:
            logger.warning("Could not send welcome DM to %s: %s", authed_user_id, exc)

        # Tell the operator, in their own workspace, that this happened.
        try:
            from src.core.alerts import installed  # noqa: PLC0415

            installed(team_id, team_name, authed_user_id, bot_token)
        except Exception as exc:
            logger.warning("Could not post install alert for %s: %s", team_id, exc)

        from src.core.analytics import capture  # noqa: PLC0415

        capture("workspace_installed", team_id)

    # Register scheduler job for this workspace
    _schedule_workspace(team_id, bot_token)

    logger.info("Installation complete for team %s (%s)", team_id, team_name)
    # Set session and pass team_id in URL as fallback for proxies that drop cookies
    session.clear()
    session["team_id"] = team_id
    session["team_name"] = team_name
    session["user_id"] = authed_user_id
    token = _make_login_token(team_id, authed_user_id)
    return redirect(f"{_APP_URL}/dashboard?t={token}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


WELCOME_TEXT = (
    "👋 Morgenruf is installed. Start your team's standup now: pick a channel and a time, that's it. "
    "Type `/morgenruf help` to see everything else."
)


def _welcome_blocks() -> list[dict]:
    """The first DM to the installer: the quick start first, then the email offer."""
    from src.core.email_consent import offer_blocks  # noqa: PLC0415
    from src.core.quickstart_button import button_block  # noqa: PLC0415

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": WELCOME_TEXT}},
        button_block(),
        *offer_blocks(),
    ]


def _is_slack_admin(bot_token: str, user_id: str) -> bool:
    """True when Slack says the user is a workspace admin or owner."""
    try:
        user = WebClient(token=bot_token).users_info(user=user_id)["user"]
    except Exception as exc:
        logger.warning("Could not look up Slack role for %s: %s", user_id, exc)
        return False
    return bool(user.get("is_admin") or user.get("is_owner") or user.get("is_primary_owner"))


def _make_login_token(team_id: str, user_id: str = "") -> str:
    """Short-lived HMAC token to bootstrap dashboard session via URL."""
    import base64

    payload = f"{int(time.time())}.{os.urandom(12).hex()}.{team_id}|{user_id}"
    return base64.urlsafe_b64encode(f"{payload}.{_sign('login', payload)}".encode()).decode()


def make_login_token(team_id: str, user_id: str) -> str:
    """A one-time dashboard sign-in for someone Slack has just identified."""
    return _make_login_token(team_id, user_id)


def _read_login_token(token: str) -> tuple[str, str, str] | None:
    """Return (team_id, user_id, nonce) for a valid token at most 5 minutes old."""
    try:
        import base64

        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = decoded.rsplit(".", 1)
        if not hmac.compare_digest(_sign("login", payload), sig):
            return None
        ts_str, nonce, team_user = payload.split(".", 2)
        if not 0 <= int(time.time()) - int(ts_str) <= 300:
            return None
        team_id, user_id = team_user.split("|", 1)
        return team_id, user_id, nonce
    except Exception:
        return None


def verify_login_token(token: str) -> tuple[str, str] | None:
    """Verify login token, return (team_id, user_id) if valid (5 min window)."""
    parsed = _read_login_token(token)
    return (parsed[0], parsed[1]) if parsed else None


def consume_login_token(token: str) -> tuple[str, str] | None:
    """Like verify_login_token, but each token opens a session only once.

    The token rides in the dashboard URL, so access logs and proxies record
    it. Claiming its nonce in the database means a copy read from a log
    within the five minutes is worthless.
    """
    parsed = _read_login_token(token)
    if not parsed:
        return None
    team_id, user_id, nonce = parsed
    try:
        if not db.claim_login_token(nonce):
            logger.warning("Dashboard login token for %s was already used", team_id)
            return None
    except Exception as exc:
        logger.error("Could not claim dashboard login token: %s", exc)
        return None
    return team_id, user_id


def _schedule_workspace(team_id: str, bot_token: str) -> None:
    """Register a scheduler job for a newly installed workspace."""
    try:
        from src.core.scheduler import get_scheduler, register_workspace_job  # noqa: PLC0415

        scheduler = get_scheduler()
        if scheduler is None:
            return
        config = db.get_workspace_config(team_id) or {}
        register_workspace_job(scheduler, team_id, bot_token, config)
    except Exception as exc:
        logger.warning("Could not register scheduler job for %s: %s", team_id, exc)
