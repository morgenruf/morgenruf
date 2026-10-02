"""Signing in to the dashboard from inside Slack.

The dashboard's "Sign in with Slack" is the app's install flow. It works as a
login for the person who installed Morgenruf, but for anyone else Slack treats
it as a new install, and a workspace that requires approval for apps stops
them there. So a member had no way into their own profile or standups.

Slack has already confirmed who clicked a button or typed a command, so the
app hands that person a sign-in link of their own: the same one-time token the
install flow ends with (signed, five minutes, one use). It is only ever shown
to the person it is for, in a modal or an ephemeral reply.
"""

from __future__ import annotations

from src.core.links import dashboard_url

ACTION = "open_dashboard"
LINK_ACTION = "dashboard_signin_link"
LINK_MINUTES = 5

EXPLAINER = (
    f"This link signs you in as you. It works once, for {LINK_MINUTES} minutes. "
    "Need another? Click *Dashboard* on the Home tab again, or type `/morgenruf dashboard`."
)


def signin_url(team_id: str, user_id: str) -> str:
    from src.core.oauth import make_login_token  # noqa: PLC0415

    return f"{dashboard_url()}?t={make_login_token(team_id, user_id)}"


def _link_blocks(url: str) -> list[dict]:
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Your settings, standup history and profile are in the dashboard."},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": LINK_ACTION,
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Open your dashboard", "emoji": True},
                    "url": url,
                }
            ],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": EXPLAINER}]},
    ]


def signin_modal(team_id: str, user_id: str) -> dict:
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Morgenruf dashboard"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": _link_blocks(signin_url(team_id, user_id)),
    }


def signin_message(team_id: str, user_id: str) -> dict:
    """An ephemeral reply to `/morgenruf dashboard`."""
    return {
        "text": "Open your Morgenruf dashboard",
        "blocks": _link_blocks(signin_url(team_id, user_id)),
        "response_type": "ephemeral",
    }
