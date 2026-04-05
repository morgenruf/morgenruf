"""Welcome email via Resend API."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, html: str) -> None:
    """Send an email via the Resend API."""
    try:
        import resend  # type: ignore[import]
    except ImportError:
        logger.warning("resend package not installed — skipping email")
        return
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.debug("RESEND_API_KEY not configured — skipping email")
        return
    try:
        resend.Emails.send({
            "from": "hello@morgenruf.dev",
            "reply_to": "support@morgenruf.dev",
            "to": to_email,
            "subject": subject,
            "html": html,
        })
        logger.info("Sent email '%s' to %s", subject, to_email)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)


def send_weekly_digest(
    to_email: str,
    team_name: str,
    stats: dict,
    participation: list[dict],
) -> None:
    """Send weekly standup digest email with per-member breakdown."""
    if not to_email:
        logger.warning("No email for weekly digest — skipping")
        return

    total = stats.get("total_responses", 0)
    total_members = stats.get("total_members", 0)
    rate = stats.get("completion_rate", 0)

    rows_html = ""
    for p in participation:
        name = p.get("real_name") or p.get("user_id", "")
        responses = p.get("responses", 0)
        blockers = p.get("days_with_blockers", 0)
        last = str(p.get("last_standup", ""))[:10] if p.get("last_standup") else "—"
        bar = "🟢" * min(responses, 5) + "⬜" * max(0, 5 - min(responses, 5))
        rows_html += (
            f"<tr>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;'>{name}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:center;'>{bar} {responses}/5</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:center;'>{'🚧 ' + str(blockers) if blockers else '—'}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;color:#999;'>{last}</td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 8px rgba(0,0,0,.06);">
<tr><td style="background:linear-gradient(135deg,#6366f1,#4f46e5);padding:32px 40px;">
  <h1 style="margin:0;color:#fff;font-size:22px;">☀️ Weekly Standup Digest</h1>
  <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:14px;">{team_name} · This week's summary</p>
</td></tr>
<tr><td style="padding:32px 40px;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="text-align:center;padding:16px;background:#f5f3ff;border-radius:8px;">
        <div style="font-size:28px;font-weight:700;color:#4f46e5;">{total}</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">Total Responses</div>
      </td>
      <td width="16"></td>
      <td style="text-align:center;padding:16px;background:#f0fdf4;border-radius:8px;">
        <div style="font-size:28px;font-weight:700;color:#16a34a;">{rate}%</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">Participation Rate</div>
      </td>
      <td width="16"></td>
      <td style="text-align:center;padding:16px;background:#fef3c7;border-radius:8px;">
        <div style="font-size:28px;font-weight:700;color:#d97706;">{total_members}</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">Active Members</div>
      </td>
    </tr>
  </table>
  <h2 style="font-size:15px;color:#111;margin:28px 0 12px;">Member Breakdown</h2>
  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #f0f0f0;border-radius:8px;overflow:hidden;">
    <tr style="background:#f9fafb;">
      <th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600;">Member</th>
      <th style="padding:8px 12px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Responses</th>
      <th style="padding:8px 12px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Blockers</th>
      <th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600;">Last Standup</th>
    </tr>
    {rows_html}
  </table>
  <p style="margin:28px 0 0;text-align:center;">
    <a href="https://api.morgenruf.dev/dashboard" style="display:inline-block;background:#6366f1;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600;">Open Dashboard →</a>
  </p>
</td></tr>
<tr><td style="background:#f9fafb;padding:20px 40px;text-align:center;font-size:12px;color:#9ca3af;">
  Morgenruf · Self-hosted standup bot · <a href="https://morgenruf.dev" style="color:#6366f1;text-decoration:none;">morgenruf.dev</a>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""

    _send(to_email, f"📊 Weekly Standup Digest — {team_name}", html)


def send_welcome_email(to_email: str, team_name: str, installed_by: str) -> None:
    """Send welcome email on new workspace installation."""
    try:
        import resend  # type: ignore[import]
    except ImportError:
        logger.warning("resend package not installed — skipping welcome email")
        return

    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.debug("RESEND_API_KEY not configured — skipping welcome email")
        return

    try:
        resend.Emails.send({
            "from": "hello@morgenruf.dev",
            "to": to_email,
            "subject": f"Morgenruf is now active in {team_name}",
            "html": welcome_email_html(team_name, installed_by),
        })
        logger.info("Sent welcome email to %s for team %s", to_email, team_name)
    except Exception as exc:
        logger.error("Failed to send welcome email to %s: %s", to_email, exc)


def welcome_email_html(team_name: str, installed_by: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background:#4f46e5;padding:32px 40px;text-align:center;">
              <div style="font-size:32px;margin-bottom:8px;">🌅</div>
              <div style="color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.5px;">Morgenruf</div>
              <div style="color:#c7d2fe;font-size:13px;margin-top:4px;">Your daily standup bot</div>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;">
              <p style="font-size:20px;font-weight:700;color:#1a1a1a;margin:0 0 8px;">Good morning! ☀️</p>
              <p style="font-size:15px;color:#555;margin:0 0 28px;line-height:1.6;">
                Morgenruf has been successfully installed in <strong style="color:#1a1a1a;">{team_name}</strong> by {installed_by}.
              </p>

              <p style="font-size:13px;font-weight:700;color:#4f46e5;text-transform:uppercase;letter-spacing:0.5px;margin:0 0 16px;">What happens next</p>

              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding:12px 16px;background:#f8f7ff;border-radius:8px;margin-bottom:8px;">
                    <table><tr>
                      <td style="font-size:20px;padding-right:12px;">💬</td>
                      <td style="font-size:14px;color:#333;line-height:1.5;">Team members receive a DM each morning with their standup questions</td>
                    </tr></table>
                  </td>
                </tr>
                <tr><td style="height:8px;"></td></tr>
                <tr>
                  <td style="padding:12px 16px;background:#f8f7ff;border-radius:8px;">
                    <table><tr>
                      <td style="font-size:20px;padding-right:12px;">📋</td>
                      <td style="font-size:14px;color:#333;line-height:1.5;">Responses are collected and posted as a clean summary to your team channel</td>
                    </tr></table>
                  </td>
                </tr>
                <tr><td style="height:8px;"></td></tr>
                <tr>
                  <td style="padding:12px 16px;background:#f8f7ff;border-radius:8px;">
                    <table><tr>
                      <td style="font-size:20px;padding-right:12px;">⚙️</td>
                      <td style="font-size:14px;color:#333;line-height:1.5;">Configure your schedule, channel, and team from the dashboard</td>
                    </tr></table>
                  </td>
                </tr>
              </table>

              <div style="margin-top:32px;text-align:center;">
                <a href="https://api.morgenruf.dev/dashboard"
                   style="display:inline-block;background:#4f46e5;color:#ffffff;font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;">
                  Open Dashboard →
                </a>
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px;background:#f8f8f8;border-top:1px solid #eee;text-align:center;">
              <p style="font-size:12px;color:#999;margin:0;">
                The Morgenruf team · <a href="https://morgenruf.dev" style="color:#4f46e5;text-decoration:none;">morgenruf.dev</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Shared HTML helpers
# ---------------------------------------------------------------------------

def _email_wrapper(content: str, footer_extra: str = "") -> str:
    """Wrap content in the dark-theme morgenruf email shell."""
    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="UTF-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
        "<style>"
        "  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');"
        "  * { box-sizing: border-box; margin: 0; padding: 0; }"
        "  body { background: #0a0a0a; color: #e5e5e5; font-family: 'Inter', sans-serif; }"
        "</style>"
        "</head>"
        '<body style="background:#0a0a0a;color:#e5e5e5;font-family:\'Inter\',Arial,sans-serif;'
        'padding:40px 16px;">'
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        "  <tr>"
        '    <td align="center">'
        '      <table width="600" cellpadding="0" cellspacing="0" role="presentation"'
        '             style="max-width:600px;width:100%;">'
        # Logo row
        "        <tr>"
        '          <td style="padding:32px 0 24px;">'
        '            <span style="font-size:22px;font-weight:700;color:#22c55e;'
        'letter-spacing:-0.5px;">morgenruf</span>'
        "          </td>"
        "        </tr>"
        # Content card
        "        <tr>"
        '          <td style="background:#141414;border-radius:12px;padding:40px;'
        'border:1px solid #1f1f1f;">'
        + content
        + "          </td>"
        "        </tr>"
        # Footer
        "        <tr>"
        '          <td style="padding:24px 0;font-size:13px;color:#525252;text-align:center;">'
        "            "
        + footer_extra
        + '<br /><a href="https://morgenruf.dev/unsubscribe" '
        'style="color:#525252;">Unsubscribe</a>'
        " &nbsp;·&nbsp; "
        '<a href="https://morgenruf.dev" style="color:#525252;">morgenruf.dev</a>'
        "          </td>"
        "        </tr>"
        "      </table>"
        "    </td>"
        "  </tr>"
        "</table>"
        "</body>"
        "</html>"
    )


def _cta_button(label: str, url: str) -> str:
    return (
        '<a href="' + url + '" '
        'style="display:inline-block;margin-top:28px;padding:12px 28px;'
        'background:#22c55e;color:#0a0a0a;font-weight:600;font-size:15px;'
        'border-radius:8px;text-decoration:none;">'
        + label
        + "</a>"
    )


def _h1(text: str) -> str:
    return (
        '<h1 style="font-size:24px;font-weight:700;color:#e5e5e5;margin-bottom:16px;">'
        + text
        + "</h1>"
    )


def _p(text: str) -> str:
    return (
        '<p style="font-size:15px;line-height:1.7;color:#a3a3a3;margin-bottom:12px;">'
        + text
        + "</p>"
    )


def _stat_row(label: str, value: str) -> str:
    return (
        '<tr>'
        '<td style="padding:10px 0;font-size:14px;color:#a3a3a3;border-bottom:1px solid #1f1f1f;">'
        + label
        + "</td>"
        '<td style="padding:10px 0;font-size:14px;font-weight:600;color:#e5e5e5;'
        'text-align:right;border-bottom:1px solid #1f1f1f;">'
        + value
        + "</td>"
        "</tr>"
    )


# ---------------------------------------------------------------------------
# 1. First standup created
# ---------------------------------------------------------------------------

def send_first_standup_email(
    to_email: str,
    team_name: str,
    standup_name: str,
    first_standup_time: str,
) -> None:
    """Send email after the first standup is created for a workspace."""
    try:
        import resend  # type: ignore[import]
    except ImportError:
        logger.warning("resend package not installed — skipping first-standup email")
        return

    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.debug("RESEND_API_KEY not configured — skipping first-standup email")
        return

    try:
        resend.Emails.send({
            "from": "hello@morgenruf.dev",
            "reply_to": "support@morgenruf.dev",
            "to": to_email,
            "subject": "Your first standup is set up \U0001f389",
            "html": first_standup_email_html(team_name, standup_name, first_standup_time),
        })
        logger.info("Sent first-standup email to %s for team %s", to_email, team_name)
    except Exception as exc:
        logger.error("Failed to send first-standup email to %s: %s", to_email, exc)


def first_standup_email_html(
    team_name: str,
    standup_name: str,
    first_standup_time: str,
) -> str:
    content = (
        _h1("Your first standup is set up \U0001f389")
        + _p(
            "Great news — <strong style='color:#e5e5e5;'>" + team_name + "</strong> is "
            "ready to roll. Here's what you configured:"
        )
        + '<table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">'
        + _stat_row("Standup name", standup_name)
        + _stat_row("First run", first_standup_time)
        + "</table>"
        + _p(
            "Team members will receive a DM in Slack at the scheduled time. "
            "Their responses will be posted as a clean digest to your chosen channel."
        )
        + _cta_button("View in Slack", "https://slack.com/app_redirect?app=morgenruf")
    )
    return _email_wrapper(
        content,
        footer_extra="You're receiving this because you installed Morgenruf in "
        + team_name + ".",
    )


# ---------------------------------------------------------------------------
# 2. Weekly digest
# ---------------------------------------------------------------------------

def send_weekly_digest_email(
    to_email: str,
    team_name: str,
    stats: dict,
) -> None:
    """Send weekly standup summary email.

    Args:
        stats: dict with keys ``total_responses``, ``active_members``,
               ``completion_rate`` (percentage as float/int), ``top_responder``.
    """
    try:
        import resend  # type: ignore[import]
    except ImportError:
        logger.warning("resend package not installed — skipping weekly digest email")
        return

    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.debug("RESEND_API_KEY not configured — skipping weekly digest email")
        return

    try:
        resend.Emails.send({
            "from": "hello@morgenruf.dev",
            "reply_to": "support@morgenruf.dev",
            "to": to_email,
            "subject": "Your week in standups \U0001f4ca",
            "html": weekly_digest_email_html(team_name, stats),
        })
        logger.info("Sent weekly digest email to %s for team %s", to_email, team_name)
    except Exception as exc:
        logger.error("Failed to send weekly digest email to %s: %s", to_email, exc)


def weekly_digest_email_html(team_name: str, stats: dict) -> str:
    completion = str(stats.get("completion_rate", 0)) + "%"
    content = (
        _h1("Your week in standups \U0001f4ca")
        + _p("Here's how <strong style='color:#e5e5e5;'>" + team_name + "</strong> did this week:")
        + '<table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">'
        + _stat_row("Total responses", str(stats.get("total_responses", 0)))
        + _stat_row("Active members", str(stats.get("active_members", 0)))
        + _stat_row("Completion rate", completion)
        + _stat_row("Top responder", str(stats.get("top_responder", "—")))
        + "</table>"
        + _p("Keep the momentum going — consistency is the secret to great async standups.")
        + _cta_button("View in Slack", "https://slack.com/app_redirect?app=morgenruf")
    )
    return _email_wrapper(
        content,
        footer_extra="Weekly digest for " + team_name + ".",
    )


# ---------------------------------------------------------------------------
# 3. Inactive nudge
# ---------------------------------------------------------------------------

def send_inactive_nudge_email(
    to_email: str,
    team_name: str,
    days_inactive: int,
) -> None:
    """Send nudge email when a workspace has had no standup responses for N days."""
    try:
        import resend  # type: ignore[import]
    except ImportError:
        logger.warning("resend package not installed — skipping inactive nudge email")
        return

    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.debug("RESEND_API_KEY not configured — skipping inactive nudge email")
        return

    try:
        resend.Emails.send({
            "from": "hello@morgenruf.dev",
            "reply_to": "support@morgenruf.dev",
            "to": to_email,
            "subject": "Your team hasn't standup'd in " + str(days_inactive) + " days",
            "html": inactive_nudge_email_html(team_name, days_inactive),
        })
        logger.info(
            "Sent inactive nudge email to %s for team %s (%d days)",
            to_email, team_name, days_inactive,
        )
    except Exception as exc:
        logger.error("Failed to send inactive nudge email to %s: %s", to_email, exc)


def inactive_nudge_email_html(team_name: str, days_inactive: int) -> str:
    days_str = str(days_inactive)
    content = (
        _h1("It's been " + days_str + " days \U0001f4ac")
        + _p(
            "<strong style='color:#e5e5e5;'>" + team_name + "</strong> hasn't had any "
            "standup responses in <strong style='color:#22c55e;'>" + days_str
            + " days</strong>."
        )
        + _p(
            "Consistent standups keep teams aligned and unblock work faster. "
            "It only takes a minute — jump back in from Slack."
        )
        + _cta_button("Resume standups in Slack", "https://slack.com/app_redirect?app=morgenruf")
    )
    return _email_wrapper(
        content,
        footer_extra="Sent because there has been no standup activity in " + team_name + ".",
    )


# ---------------------------------------------------------------------------
# 4. Release announcement
# ---------------------------------------------------------------------------

def send_release_announcement_email(
    to_email: str,
    team_name: str,
    version: str,
    changelog_url: str,
) -> None:
    """Send new release notification email."""
    try:
        import resend  # type: ignore[import]
    except ImportError:
        logger.warning("resend package not installed — skipping release announcement email")
        return

    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.debug("RESEND_API_KEY not configured — skipping release announcement email")
        return

    try:
        resend.Emails.send({
            "from": "hello@morgenruf.dev",
            "reply_to": "support@morgenruf.dev",
            "to": to_email,
            "subject": "Morgenruf " + version + " is here \u2728",
            "html": release_announcement_email_html(team_name, version, changelog_url),
        })
        logger.info(
            "Sent release announcement email to %s for team %s (v%s)",
            to_email, team_name, version,
        )
    except Exception as exc:
        logger.error("Failed to send release announcement email to %s: %s", to_email, exc)


def release_announcement_email_html(
    team_name: str,
    version: str,
    changelog_url: str,
) -> str:
    content = (
        _h1("Morgenruf " + version + " is here \u2728")
        + _p(
            "Hi <strong style='color:#e5e5e5;'>" + team_name
            + "</strong> — we just shipped a new version of Morgenruf."
        )
        + _p(
            "This release includes improvements and fixes to make your daily standups "
            "even smoother. Check the full changelog for details."
        )
        + _cta_button("View changelog", changelog_url)
    )
    return _email_wrapper(
        content,
        footer_extra="You're receiving this as an admin of " + team_name + ".",
    )
