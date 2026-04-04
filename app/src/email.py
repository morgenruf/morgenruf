"""Welcome email via Resend API."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


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
    return f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
      <h2>Good morning! ☀️</h2>
      <p>Morgenruf has been successfully installed in <strong>{team_name}</strong> by {installed_by}.</p>
      <h3>What happens next?</h3>
      <ul>
        <li>Each morning, team members will receive a DM with 3 standup questions</li>
        <li>Answers are posted as a clean summary to your configured channel</li>
        <li>Tag responses with <code>Proj-X:</code> for per-project tracking</li>
      </ul>
      <p><a href="https://morgenruf.dev/docs" style="color: #e8a838;">Read the docs →</a></p>
      <p>— The Morgenruf team</p>
    </div>
    """
