"""Asking the installer before emailing them: the button, and what it records.

Morgenruf reads the installer's address from Slack (users:read.email). Slack's
marketplace guidelines ask for explicit consent before contacting that
address, given during install or onboarding. So nothing is emailed until the
installer presses "Email me setup tips", offered in the install DM and on the
App Home, and a second button on the App Home withdraws it.

Only the installer is offered it, because every one of these messages is
about the install. Nobody else's Slack address is ever emailed.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

OPT_IN_ACTION = "email:opt_in"
OPT_OUT_ACTION = "email:opt_out"

OFFER_TEXT = (
    "*Want setup tips by email?*\n"
    "Press the button and I will send you a welcome email with how to get started, "
    "one check-in a week later, and a weekly standup digest on Sundays. "
    "Nothing is emailed until you press it, and you can stop any time from the Home tab."
)
_ON_TEXT = (
    "*Setup emails are on.*\n"
    "You get the welcome email, one check-in a week after install, and a weekly standup digest on Sundays."
)
_NOT_INSTALLER = "Only the person who installed Morgenruf can turn on setup emails."
_NOT_OWNER = "Only the person who turned on setup emails can turn them off."
_FAILED = "I couldn't save that just now. Please try again in a minute."


def _button(action_id: str, label: str, style: str = "") -> dict:
    button = {
        "type": "button",
        "action_id": action_id,
        "text": {"type": "plain_text", "text": label},
        "value": action_id,
    }
    if style:
        button["style"] = style
    return button


def offer_blocks() -> list[dict]:
    """The ask, for the install DM."""
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": OFFER_TEXT}},
        {"type": "actions", "elements": [_button(OPT_IN_ACTION, "Email me setup tips", "primary")]},
    ]


def home_blocks(team_id: str, user_id: str) -> list[dict]:
    """The App Home setting, shown only to the installer or whoever opted in."""
    import src.core.db as db  # noqa: PLC0415

    try:
        consent = db.setup_email_consent(team_id)
        inst = db.get_installation(team_id) or {}
    except Exception as exc:
        logger.warning("email consent App Home unavailable for %s: %s", team_id, exc)
        return []

    if consent:
        if consent.get("user_id") != user_id:
            return []
        return [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": _ON_TEXT},
                "accessory": _button(OPT_OUT_ACTION, "Stop setup emails"),
            },
        ]
    if inst.get("installed_by_user_id") != user_id:
        return []
    return [{"type": "divider"}, *offer_blocks()]


def opt_in(client, team_id: str, user_id: str) -> str:
    """Record the opt-in and send the welcome. Returns what to tell them."""
    import src.core.db as db  # noqa: PLC0415
    from src.core import mailer  # noqa: PLC0415

    inst = db.get_installation(team_id) or {}
    if inst.get("installed_by_user_id") != user_id:
        return _NOT_INSTALLER
    db.grant_setup_email_consent(team_id, user_id)
    # Pressing it again, or again after stopping, does not repeat the welcome.
    if db.install_email_sent(team_id, "welcome"):
        return "Setup emails are on again. You can stop them any time from the Morgenruf Home tab."
    team_name = inst.get("team_name") or "your workspace"
    if mailer.send_welcome(client, team_id, team_name, user_id):
        return "Done. The welcome email is on its way. You can stop setup emails any time from the Morgenruf Home tab."
    return (
        "Setup emails are on, but I couldn't send the welcome email: Slack gave me no address for you. "
        "You can turn this off any time from the Morgenruf Home tab."
    )


def opt_out(team_id: str, user_id: str) -> str:
    import src.core.db as db  # noqa: PLC0415

    consent = db.setup_email_consent(team_id)
    if consent and consent.get("user_id") != user_id:
        return _NOT_OWNER
    db.revoke_setup_email_consent(team_id)
    return "Setup emails are stopped. Nothing more will be emailed to you. You can turn them back on from the Home tab."


def _ids(body: dict) -> tuple[str, str]:
    user_id = body["user"]["id"]
    team_id = (body.get("team") or {}).get("id") or body["user"].get("team_id", "")
    return team_id, user_id


def _reply(client, body: dict, user_id: str, text: str) -> None:  # noqa: ANN001
    """Answer where they pressed it.

    Pressed in the install DM, the offer in that message is swapped for the
    answer and the rest of the welcome stays. Pressed on the App Home, the
    answer arrives as a DM.
    """
    container = body.get("container") or {}
    if container.get("type") == "message" and container.get("channel_id"):
        kept = [
            block
            for block in (body.get("message") or {}).get("blocks") or []
            if block.get("type") != "actions" and (block.get("text") or {}).get("text") != OFFER_TEXT
        ]
        try:
            client.chat_update(
                channel=container["channel_id"],
                ts=container.get("message_ts", ""),
                text=text,
                blocks=[*kept, {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}],
            )
            return
        except Exception as exc:
            logger.info("email consent: could not update the DM: %s", exc)
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception as exc:
        logger.info("email consent: could not confirm to %s: %s", user_id, exc)


def register_slack(app) -> None:
    """Attach the two buttons to the Bolt app."""

    @app.action(OPT_IN_ACTION)
    def handle_opt_in(ack, body, client):  # noqa: ANN001
        ack()
        team_id, user_id = _ids(body)
        try:
            text = opt_in(client, team_id, user_id)
        except Exception:
            logger.exception("email consent: opt-in failed in %s", team_id)
            text = _FAILED
        _reply(client, body, user_id, text)

    @app.action(OPT_OUT_ACTION)
    def handle_opt_out(ack, body, client):  # noqa: ANN001
        ack()
        team_id, user_id = _ids(body)
        try:
            text = opt_out(team_id, user_id)
        except Exception:
            logger.exception("email consent: opt-out failed in %s", team_id)
            text = _FAILED
        _reply(client, body, user_id, text)
