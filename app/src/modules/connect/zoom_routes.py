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


def mint_link_token(team_id: str, user_id: str) -> str:
    return _serializer().dumps({"t": team_id, "u": user_id})


def read_link_token(token: str) -> tuple[str, str] | None:
    from itsdangerous import BadSignature, SignatureExpired  # noqa: PLC0415

    try:
        data = _serializer().loads(token, max_age=LINK_MAX_AGE)
    except SignatureExpired:
        logger.info("zoom: link token expired")
        return None
    except BadSignature:
        logger.warning("zoom: link token rejected")
        return None
    team_id, user_id = data.get("t"), data.get("u")
    return (team_id, user_id) if team_id and user_id else None


def _page(title: str, body: str, ok: bool = True) -> str:
    """A plain page, because this is the one place a Slack user leaves Slack.

    No dashboard chrome: they arrived from a button and are about to go back.
    """
    colour = "#1a7f5a" if ok else "#a1343c"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
          background:#12141a; color:#e8eaed;
          font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  .card {{ max-width:30rem; padding:2rem; background:#1a1d26; border:1px solid #2a2e3a;
           border-radius:12px; text-align:center; }}
  h1 {{ margin:0 0 .5rem; font-size:1.25rem; color:{colour}; }}
  p {{ margin:0; color:#a8adb8; }}
</style></head>
<body><div class="card"><h1>{title}</h1><p>{body}</p></div></body></html>"""


def register_zoom_routes(bp) -> None:
    """Mounted on Connect's own blueprint, so the module owns its endpoints."""
    from flask import redirect, request

    from src.modules.connect import zoom

    @bp.route("/connect/zoom/start")
    def zoom_start():  # noqa: ANN202
        if not zoom.configured():
            return _page("Zoom is not set up", "This Morgenruf deployment has no Zoom credentials.", ok=False), 503
        who = read_link_token(request.args.get("t", ""))
        if not who:
            return _page(
                "That link has expired",
                "Open the coffee chat message in Slack and press the button again.",
                ok=False,
            ), 400
        team_id, user_id = who
        # The state is signed the same way, so the callback can trust who came
        # back without keeping server-side state for a redirect that may never
        # return.
        return redirect(zoom.authorize_url(mint_link_token(team_id, user_id)))

    @bp.route("/connect/zoom/callback")
    def zoom_callback():  # noqa: ANN202
        import src.modules.connect.db as cdb

        if request.args.get("error"):
            return _page("Zoom was not connected", "You declined the request. Nothing has changed.", ok=False)

        who = read_link_token(request.args.get("state", ""))
        code = request.args.get("code", "")
        if not who or not code:
            return _page("That did not work", "Please start again from Slack.", ok=False), 400

        team_id, user_id = who
        payload = zoom.exchange_code(code)
        if not payload or not payload.get("refresh_token"):
            return _page("Zoom refused the connection", "Please try again from Slack.", ok=False), 502

        zoom.store_from_token_response(team_id, user_id, payload)
        # Best effort: naming the account is a nicety, not a reason to fail.
        try:
            me = zoom.whoami(payload.get("access_token") or "")
            if me:
                cdb.set_zoom_identity(team_id, user_id, str(me.get("id") or ""), me.get("email") or "")
        except Exception:
            logger.info("zoom: linked but could not read the account name")

        return _page(
            "Zoom connected",
            "You can close this tab. Your next coffee chat will come with a meeting once you and "
            "the other person agree a time.",
        )
