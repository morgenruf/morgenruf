"""The two HTTP endpoints Zoom linking needs.

Linking starts from a button inside Slack, so the person arrives at a browser
with no dashboard session: the link itself has to carry who they are. It is a
signed token rather than user ids in the query string, so the URL cannot be
edited into somebody else's authorisation. Donut's equivalent link has the
same shape (/dals/<token>).

The token is short-lived because it is only ever followed immediately, and it
is bound to the workspace and person it was minted for.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

LINK_MAX_AGE = 900  # fifteen minutes; the button is pressed at once or not at all
_SALT = "connect-zoom-link"


def _serializer():
    from flask import current_app  # noqa: PLC0415
    from itsdangerous import URLSafeTimedSerializer  # noqa: PLC0415

    return URLSafeTimedSerializer(current_app.secret_key, salt=_SALT)


_NONCE_KEY = "zoom_oauth_nonce"


def mint_link_token(team_id: str, user_id: str, nonce: str = "") -> str:
    data = {"t": team_id, "u": user_id}
    if nonce:
        data["n"] = nonce
    return _serializer().dumps(data)


def _load(token: str) -> dict | None:
    from itsdangerous import BadSignature, SignatureExpired  # noqa: PLC0415

    try:
        data = _serializer().loads(token, max_age=LINK_MAX_AGE)
    except SignatureExpired:
        logger.info("zoom: link token expired")
        return None
    except BadSignature:
        logger.warning("zoom: link token rejected")
        return None
    return data if isinstance(data, dict) and data.get("t") and data.get("u") else None


def read_link_token(token: str) -> tuple[str, str] | None:
    data = _load(token)
    return (data["t"], data["u"]) if data else None


def read_callback_state(state: str) -> tuple[str, str] | None:
    """Who came back, only if this browser started the flow and has not
    finished it already.

    A signed state alone could be replayed, or completed in another browser
    with an attacker's code, linking their Zoom account to the victim. The
    nonce is kept in this browser's session and popped, so it works once.
    """
    import hmac  # noqa: PLC0415

    from flask import session  # noqa: PLC0415

    expected = session.pop(_NONCE_KEY, None)
    data = _load(state)
    if not data or not expected or not hmac.compare_digest(str(data.get("n") or ""), expected):
        return None
    return data["t"], data["u"]


def _result(status: str):
    from flask import redirect

    return redirect(f"/connect/zoom/result?status={status}", code=303)


def register_zoom_routes(bp) -> None:
    """Mounted on Connect's own blueprint, so the module owns its endpoints."""
    from flask import redirect, request

    from src.modules.connect import zoom

    @bp.route("/connect/zoom/start")
    def zoom_start():  # noqa: ANN202
        if not zoom.configured():
            return _result("unavailable")
        who = read_link_token(request.args.get("t", ""))
        if not who:
            return _result("expired")
        team_id, user_id = who
        # The state is signed the same way, so the callback can trust who came
        # back, and carries a nonce held in this browser's session so it can
        # only be completed here, once.
        import secrets  # noqa: PLC0415

        from flask import session  # noqa: PLC0415

        nonce = secrets.token_urlsafe(16)
        session[_NONCE_KEY] = nonce
        return redirect(zoom.authorize_url(mint_link_token(team_id, user_id, nonce)))

    @bp.route("/connect/zoom/callback")
    def zoom_callback():  # noqa: ANN202
        import src.modules.connect.db as cdb

        if request.args.get("error"):
            from flask import session  # noqa: PLC0415

            session.pop(_NONCE_KEY, None)
            return _result("denied")

        who = read_callback_state(request.args.get("state", ""))
        code = request.args.get("code", "")
        if not who or not code:
            return _result("invalid")

        team_id, user_id = who
        payload = zoom.exchange_code(code)
        if not payload or not payload.get("refresh_token"):
            return _result("error")

        zoom.store_from_token_response(team_id, user_id, payload)
        # Best effort: naming the account is a nicety, not a reason to fail.
        try:
            me = zoom.whoami(payload.get("access_token") or "")
            if me:
                cdb.set_zoom_identity(team_id, user_id, str(me.get("id") or ""), me.get("email") or "")
        except Exception:
            logger.info("zoom: linked but could not read the account name")

        return _result("connected")
