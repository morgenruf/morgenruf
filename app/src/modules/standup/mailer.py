"""Standup digest emails, sent through the Resend API."""

from __future__ import annotations

import html as _html
import logging
import os

logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, html: str) -> None:
    """Send an email via the Resend API."""
    try:
        import resend  # type: ignore[import]
    except ImportError:
        logger.warning("resend package not installed, skipping email")
        return
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.debug("RESEND_API_KEY not configured, skipping email")
        return
    try:
        resend.Emails.send(
            {
                "from": "hello@morgenruf.dev",
                "reply_to": "hello@morgenruf.dev",
                "to": to_email,
                "subject": subject,
                "html": html,
            }
        )
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
        logger.warning("No email for weekly digest, skipping")
        return
    from src.core.links import dashboard_url  # noqa: PLC0415
    from src.core.mailer import unsubscribe_url  # noqa: PLC0415

    total = stats.get("total_responses", 0)
    total_members = stats.get("total_members", 0)
    rate = stats.get("completion_rate", 0)

    rows_html = ""
    for p in participation:
        name = _html.escape(p.get("real_name") or p.get("user_id", ""))
        responses = p.get("responses", 0)
        blockers = p.get("days_with_blockers", 0)
        last = str(p.get("last_standup", ""))[:10] if p.get("last_standup") else "n/a"
        bar = "🟢" * min(responses, 5) + "⬜" * max(0, 5 - min(responses, 5))
        rows_html += (
            f"<tr>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;'>{name}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:center;'>{bar} {responses}/5</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:center;'>{'🚧 ' + str(blockers) if blockers else 'None'}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f0f0f0;color:#999;'>{last}</td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 8px rgba(0,0,0,.06);">
<tr><td style="background:linear-gradient(135deg,#6366f1,#4f46e5);padding:32px 40px;">
  <h1 style="margin:0;color:#fff;font-size:22px;">☀️ Weekly standup digest</h1>
  <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:14px;">{_html.escape(team_name or "")} · This week's summary</p>
</td></tr>
<tr><td style="padding:32px 40px;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="text-align:center;padding:16px;background:#f5f3ff;border-radius:8px;">
        <div style="font-size:28px;font-weight:700;color:#4f46e5;">{total}</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">Total responses</div>
      </td>
      <td width="16"></td>
      <td style="text-align:center;padding:16px;background:#f0fdf4;border-radius:8px;">
        <div style="font-size:28px;font-weight:700;color:#16a34a;">{rate}%</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">Participation rate</div>
      </td>
      <td width="16"></td>
      <td style="text-align:center;padding:16px;background:#fef3c7;border-radius:8px;">
        <div style="font-size:28px;font-weight:700;color:#d97706;">{total_members}</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">Active members</div>
      </td>
    </tr>
  </table>
  <h2 style="font-size:15px;color:#111;margin:28px 0 12px;">Member breakdown</h2>
  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #f0f0f0;border-radius:8px;overflow:hidden;">
    <tr style="background:#f9fafb;">
      <th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600;">Member</th>
      <th style="padding:8px 12px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Responses</th>
      <th style="padding:8px 12px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Blockers</th>
      <th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600;">Last standup</th>
    </tr>
    {rows_html}
  </table>
  <p style="margin:28px 0 0;text-align:center;">
    <a href="{dashboard_url()}" style="display:inline-block;background:#6366f1;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600;">Open the dashboard →</a>
  </p>
</td></tr>
<tr><td style="background:#f9fafb;padding:20px 40px;text-align:center;font-size:12px;color:#9ca3af;">
  You are getting this because you pressed &ldquo;Email me setup tips&rdquo; in Morgenruf's Home tab in Slack.
  Turn it off there at any time, or <a href="{_html.escape(unsubscribe_url(to_email))}" style="color:#6366f1;">unsubscribe</a>.<br/>
  Morgenruf · Self-hosted standup bot · <a href="https://morgenruf.dev" style="color:#6366f1;text-decoration:none;">morgenruf.dev</a>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""

    _send(to_email, f"📊 Weekly standup digest for {team_name}", html)


def send_manager_digest(
    manager_email: str,
    workspace_name: str,
    standups: list,
    date_str: str,
    scope_label: str = "",
) -> None:
    """Send a daily standup digest by email.

    scope_label names the standup when the digest covers one rather than the
    whole workspace, so a lead subscribed to several can tell them apart.
    """
    if not manager_email:
        logger.warning("No manager_email, skipping manager digest")
        return

    blockers = [s for s in standups if s.get("blockers", "").strip().lower() not in ("", "none", "n/a", "no", "-")]
    participation = len(standups)

    rows = ""
    for s in standups:
        has_blocker = s.get("blockers", "").strip().lower() not in ("", "none", "n/a", "no", "-")
        blocker_style = "background:#fff3cd;padding:4px 8px;border-radius:4px;" if has_blocker else ""
        rows += (
            "<tr>"
            f"<td style='padding:12px;border-bottom:1px solid #eee;font-weight:600'>{_html.escape(s.get('user_name') or s.get('user_id', ''))}</td>"
            f"<td style='padding:12px;border-bottom:1px solid #eee'>{_html.escape(s.get('yesterday') or '')}</td>"
            f"<td style='padding:12px;border-bottom:1px solid #eee'>{_html.escape(s.get('today') or '')}</td>"
            f"<td style='padding:12px;border-bottom:1px solid #eee;{blocker_style}'>{_html.escape(s.get('blockers') or '') or 'None'}</td>"
            "</tr>"
        )

    blocker_word = "blocker" if len(blockers) == 1 else "blockers"
    blocker_notice = f" · <span style='color:#e67e22'>⚠️ {len(blockers)} {blocker_word}</span>" if blockers else ""
    response_word = "response" if participation == 1 else "responses"

    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,sans-serif;max-width:800px;margin:0 auto;padding:20px">
<h2 style="color:#1a1a2e">📋 Daily standup digest for {_html.escape(str(date_str))}</h2>
<p style="color:#666">{_html.escape(workspace_name or "")} · {participation} {response_word}{blocker_notice}</p>
<table style="width:100%;border-collapse:collapse;margin-top:20px">
  <thead><tr style="background:#f8f9fa">
    <th style="padding:12px;text-align:left">Member</th>
    <th style="padding:12px;text-align:left">Yesterday</th>
    <th style="padding:12px;text-align:left">Today</th>
    <th style="padding:12px;text-align:left">Blockers</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
<p style="margin-top:30px;color:#999;font-size:12px">Sent by <a href="https://morgenruf.dev">Morgenruf</a> · <a href="https://morgenruf.dev">Manage settings</a></p>
</body></html>"""

    _send(
        to_email=manager_email,
        subject=f"[{scope_label or workspace_name}] Standup digest for {date_str}",
        html=html,
    )
