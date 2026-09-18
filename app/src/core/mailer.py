"""Email the app sends about itself: the welcome, and one follow-up a week later.

Install-time email belongs in core. It lived in the standup module, which meant
core's OAuth handler imported a feature module by name, the one thing the module
contract forbids.

Two messages, both tied to an action the recipient took:

  Welcome, on install. Transactional: they installed it thirty seconds ago.
  Day seven, once. Asks a question, and the question depends on whether they
  ever got a standup running. Carries an unsubscribe link, because a message
  that asks for something is no longer purely transactional and Canadian
  anti-spam law does not care how friendly the tone is.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

logger = logging.getLogger(__name__)

FROM = "Morgenruf <hello@morgenruf.dev>"
REPLY_TO = "support@morgenruf.dev"
SITE = "https://morgenruf.dev"
APP = os.environ.get("APP_URL", "https://api.morgenruf.dev").rstrip("/")

# Sender identity, required on any commercial electronic message under CASL.
POSTAL = "CloudDrove, Kitchener, Ontario, Canada"


def unsubscribe_token(email: str) -> str:
    secret = (os.environ.get("FLASK_SECRET_KEY") or "morgenruf-dev").encode()
    return hmac.new(secret, email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_url(email: str) -> str:
    from urllib.parse import quote

    return f"{APP}/email/unsubscribe?e={quote(email)}&t={unsubscribe_token(email)}"


def send(to_email: str, subject: str, html: str, *, kind: str = "transactional") -> bool:
    """Send one email. Returns whether it left the building.

    A suppressed address is skipped before anything is built, so an unsubscribe
    holds even if a caller forgets to check.
    """
    if not to_email:
        logger.info("No address for %s email; nothing sent", kind)
        return False
    try:
        import src.core.db as db  # noqa: PLC0415

        if db.email_is_suppressed(to_email):
            logger.info("Address has unsubscribed; %s email not sent", kind)
            return False
    except Exception as exc:  # a suppression table that is unreadable must not send anyway
        logger.warning("Could not check the suppression list: %s", exc)
        return False

    try:
        import resend  # type: ignore[import]  # noqa: PLC0415
    except ImportError:
        logger.warning("resend is not installed; %s email skipped", kind)
        return False

    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.info("RESEND_API_KEY is not set; %s email skipped", kind)
        return False

    try:
        resend.Emails.send(
            {
                "from": FROM,
                "reply_to": REPLY_TO,
                "to": to_email,
                "subject": subject,
                "html": html,
                "headers": {
                    "List-Unsubscribe": f"<{unsubscribe_url(to_email)}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            }
        )
        logger.info("Sent %s email: %s", kind, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send %s email: %s", kind, exc)
        return False


# ── The template ────────────────────────────────────────────────────────────
# Email clients are a hostile rendering environment: tables, inline styles, no
# web fonts, no flexbox. The dawn palette is the website's, so a person who
# arrives from the email recognises where they landed.

INK = "#12131F"
PAPER = "#FFFDF8"
AMBER = "#FFB23F"
SUN = "#FFD166"
ROOSTER = "#E0322E"
TEXT = "#191B2A"
MUTED = "#5A5E74"
LINE = "#E9E2D6"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def _shell(preheader: str, body: str, email: str) -> str:
    """One frame for every message: sunrise header, content, honest footer."""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="color-scheme" content="light"/></head>
<body style="margin:0;padding:0;background:{PAPER};font-family:{FONT};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER};padding:32px 12px;">
<tr><td align="center">
  <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:560px;max-width:100%;background:#ffffff;border:1px solid {LINE};border-radius:16px;overflow:hidden;">
    <tr><td style="background:{INK};padding:26px 32px;">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>
        <td style="padding-right:12px;"><img src="{SITE}/logo-mark.png" width="38" height="38" alt="" style="display:block;border-radius:8px;"/></td>
        <td style="color:#F6F3EC;font-size:19px;font-weight:700;letter-spacing:-0.02em;">morgenruf</td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:34px 32px 30px;">{body}</td></tr>
    <tr><td style="background:{PAPER};border-top:1px solid {LINE};padding:20px 32px;">
      <p style="margin:0 0 8px;font-size:12.5px;color:{MUTED};line-height:1.55;">
        You are getting this because Morgenruf was installed in your Slack workspace.
        {POSTAL}.
      </p>
      <p style="margin:0;font-size:12.5px;color:{MUTED};">
        <a href="{SITE}" style="color:{MUTED};">morgenruf.dev</a> ·
        <a href="{SITE}/privacy" style="color:{MUTED};">Privacy</a> ·
        <a href="{unsubscribe_url(email)}" style="color:{MUTED};">Unsubscribe</a>
      </p>
    </td></tr>
  </table>
  <p style="margin:16px 0 0;font-size:12px;color:#82869B;">Open source, MIT licensed, and free for every seat.</p>
</td></tr></table></body></html>"""


def _button(href: str, label: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 6px;"><tr>'
        f'<td style="background:{SUN};border-radius:999px;">'
        f'<a href="{href}" style="display:inline-block;padding:13px 26px;font-size:15.5px;font-weight:700;'
        f'color:#26190A;text-decoration:none;">{label}</a></td></tr></table>'
    )


def _step(number: str, title: str, text: str) -> str:
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">'
        f'<tr><td style="background:{PAPER};border:1px solid {LINE};border-radius:12px;padding:14px 16px;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td valign="top" style="padding-right:12px;font-family:{FONT};font-size:15px;font-weight:700;color:{ROOSTER};">{number}</td>'
        f'<td><div style="font-size:15px;font-weight:700;color:{TEXT};margin-bottom:2px;">{title}</div>'
        f'<div style="font-size:14px;color:{MUTED};line-height:1.55;">{text}</div></td>'
        f"</tr></table></td></tr></table>"
    )


def welcome_html(team_name: str, installed_by: str, email: str) -> str:
    """The message that goes out on install.

    The old one said team members would receive a DM each morning, which was
    not true: nothing runs until somebody creates a standup. Fourteen of the
    first twenty workspaces never did, so this one says that plainly and gives
    one thing to press.
    """
    body = f"""
<p style="margin:0 0 6px;font-size:23px;font-weight:700;color:{TEXT};letter-spacing:-0.02em;">
  Morgenruf is in {team_name}</p>
<p style="margin:0 0 22px;font-size:15.5px;color:{MUTED};line-height:1.6;">
  Installed by {installed_by}. Nothing will happen yet, and that is on purpose:
  the bot does not message anybody until you tell it who to ask and when.</p>
{_button(f"{APP}/dashboard", "Create your first standup")}
<p style="margin:18px 0 26px;font-size:13.5px;color:{MUTED};">Takes about a minute. You pick a channel, the
  questions and the hour.</p>
<p style="margin:0 0 12px;font-size:13px;font-weight:700;color:{ROOSTER};">Then this happens every morning</p>
{_step("1", "Everyone gets a direct message", "At the hour you choose, in their own timezone, so nobody is asked at midnight.")}
{_step("2", "They answer whenever they get to it", "No meeting, no waiting for the slowest person on the call.")}
{_step("3", "One summary posts to your channel", "Grouped by person or question, with blockers pulled out.")}
<p style="margin:24px 0 0;font-size:14.5px;color:{MUTED};line-height:1.6;">
  Coffee chats and kudos are in there too, switched off until you want them.
  If anything is confusing, reply to this email: it reaches a person.</p>"""
    return _shell(f"Morgenruf is installed in {team_name}. One step left.", body, email)


def followup_running_html(team_name: str, email: str, standups: int, people: int) -> str:
    """Day seven, for a workspace that got it running.

    Asks one question. A survey link would get ignored; a reply to a human is
    the thing people actually answer.
    """
    body = f"""
<p style="margin:0 0 6px;font-size:23px;font-weight:700;color:{TEXT};letter-spacing:-0.02em;">
  A week of standups in {team_name}</p>
<p style="margin:0 0 20px;font-size:15.5px;color:{MUTED};line-height:1.6;">
  {standups} answers from {people} {"person" if people == 1 else "people"} so far. That is the part that
  usually decides whether a standup habit survives, so: it is working.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 22px;">
  <tr><td style="background:{PAPER};border-left:3px solid {AMBER};border-radius:0 10px 10px 0;padding:16px 18px;">
    <p style="margin:0;font-size:15.5px;color:{TEXT};line-height:1.6;">
      <strong>What is the most annoying thing about it?</strong><br/>
      Reply to this email and it reaches the person who wrote it. One sentence is plenty.</p>
  </td></tr></table>
<p style="margin:0 0 10px;font-size:13px;font-weight:700;color:{ROOSTER};">Two things teams usually turn on next</p>
{_step("·", "Coffee chats", "Pairs people from a channel on a cadence and gets them to agree a time.")}
{_step("·", "Kudos", "A handful of tokens a day each, gone at midnight if unspent.")}
{_button(f"{APP}/dashboard", "Open the dashboard")}"""
    return _shell(f"{standups} standups in your first week. One question.", body, email)


def followup_stalled_html(team_name: str, email: str) -> str:
    """Day seven, for a workspace where nothing ever ran.

    The useful message, and the one that was missing: most workspaces that go
    quiet never created a schedule, and nobody ever asked them why.
    """
    body = f"""
<p style="margin:0 0 6px;font-size:23px;font-weight:700;color:{TEXT};letter-spacing:-0.02em;">
  Nothing has run in {team_name} yet</p>
<p style="margin:0 0 20px;font-size:15.5px;color:{MUTED};line-height:1.6;">
  Morgenruf has been installed for a week and has not asked anybody anything,
  because no standup has been created. That might be deliberate. If it is not,
  it takes about a minute.</p>
{_button(f"{APP}/dashboard", "Create a standup")}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0 20px;">
  <tr><td style="background:{PAPER};border-left:3px solid {AMBER};border-radius:0 10px 10px 0;padding:16px 18px;">
    <p style="margin:0;font-size:15.5px;color:{TEXT};line-height:1.6;">
      <strong>Or tell me what stopped you.</strong><br/>
      Reply to this email. Whether it was the Slack scopes, the setup, or it simply
      was not what you expected, knowing is worth more to me than the install.</p>
  </td></tr></table>
<p style="margin:0 0 10px;font-size:13px;font-weight:700;color:{ROOSTER};">The usual sticking points</p>
{_step("·", "The bot is not in the channel", "Invite it with /invite @Morgenruf, or it cannot post the summary.")}
{_step("·", "Coffee chats look switched off", "They are, until you enable them. They also need three extra Slack scopes.")}
{_step("·", "You wanted Microsoft Teams", "Not yet. Google Chat is in beta, Teams is being built.")}
<p style="margin:22px 0 0;font-size:14px;color:{MUTED};line-height:1.6;">
  If you are done with it, removing the app from Slack deletes the workspace's data.
  No hard feelings, and the reply above still helps.</p>"""
    return _shell(f"Morgenruf has not run in {team_name}. What stopped you?", body, email)


# ── The day-seven follow-up ─────────────────────────────────────────────────


def send_install_followups(days: int = 7) -> tuple[int, int]:
    """One message per workspace, a week after install. Returns (sent, skipped).

    Which message depends on whether a standup was ever created, because the
    interesting question differs: a team that is running gets asked what
    annoys them, and a team where nothing ever ran gets asked what stopped
    them. The second is the one nobody has been asking, and fourteen of the
    first twenty workspaces were in that state.
    """
    import src.core.db as db  # noqa: PLC0415

    sent = skipped = 0
    try:
        pending = db.workspaces_awaiting_followup(days)
    except Exception as exc:
        logger.warning("Could not list workspaces for follow-up: %s", exc)
        return 0, 0

    for row in pending:
        team_id = row["team_id"]
        team_name = row.get("team_name") or "your workspace"
        email = _installer_email(team_id, row.get("installed_by_user_id"))
        if not email:
            # Recorded anyway: without an address there is nothing to retry,
            # and leaving it unrecorded means asking again every single day.
            db.record_install_email(team_id, "followup:no-address")
            skipped += 1
            continue

        running = (row.get("standups") or 0) > 0
        if running:
            html = followup_running_html(team_name, email, row["standups"], row.get("people") or 1)
            subject = f"A week of standups in {team_name}"
            kind = "followup:running"
        else:
            html = followup_stalled_html(team_name, email)
            subject = f"Morgenruf has not run in {team_name} yet"
            kind = "followup:stalled"

        if send(email, subject, html, kind=kind):
            db.record_install_email(team_id, kind, email)
            sent += 1
        else:
            db.record_install_email(team_id, f"{kind}:undeliverable", email)
            skipped += 1

    if sent or skipped:
        logger.info("Install follow-ups: %d sent, %d skipped", sent, skipped)
    return sent, skipped


def _installer_email(team_id: str, user_id) -> str:
    """The installer's address from the roster, which the member sync fills."""
    if not user_id:
        return ""
    try:
        import src.core.db as db  # noqa: PLC0415

        for member in db.get_all_members(team_id):
            if member.get("user_id") == user_id:
                return (member.get("email") or "").strip()
    except Exception as exc:
        logger.warning("Could not look up the installer's address: %s", exc)
    return ""
