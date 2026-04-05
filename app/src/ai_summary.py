"""AI-powered standup summary generator.

Uses OpenAI (gpt-4o-mini) or Anthropic (claude-haiku) to generate
a concise paragraph summarising the team's standup responses.

Requires: OPENAI_API_KEY or ANTHROPIC_API_KEY env var.
Falls back to a plain bullet-point summary if no key is set.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a team standup summariser. Given a list of standup updates from team members, write a single cohesive paragraph (3-5 sentences) that:
1. Highlights the key themes of what the team worked on yesterday
2. Notes what the team is focused on today  
3. Calls out any blockers or risks

Be concise, professional, and use "the team" language. Do not list every person individually."""


def generate_summary(standups: list[dict], team_name: str = "") -> str:
    """Generate an AI summary paragraph from standup data.

    Falls back to plain list summary if no API key configured.
    """
    if not standups:
        return ""

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # Build the standup text
    lines = []
    for s in standups:
        name = s.get("user_id", "Unknown")
        lines.append(
            f"{name}:\n"
            f"  Yesterday: {s.get('yesterday','')}\n"
            f"  Today: {s.get('today','')}\n"
            f"  Blockers: {s.get('blockers','')}"
        )
    standup_text = "\n\n".join(lines)

    if openai_key:
        return _openai_summary(standup_text, team_name, openai_key)
    if anthropic_key:
        return _anthropic_summary(standup_text, team_name, anthropic_key)

    # Fallback: plain summary
    return _plain_summary(standups, team_name)


def _openai_summary(text: str, team_name: str, api_key: str) -> str:
    try:
        import httpx
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Team: {team_name}\n\nStandups:\n{text}"},
                ],
                "max_tokens": 300,
                "temperature": 0.4,
            },
            timeout=15,
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("OpenAI summary failed: %s", exc)
        return ""


def _anthropic_summary(text: str, team_name: str, api_key: str) -> str:
    try:
        import httpx
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-20240307",
                "max_tokens": 300,
                "system": _SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": f"Team: {team_name}\n\nStandups:\n{text}"},
                ],
            },
            timeout=15,
        )
        return response.json()["content"][0]["text"].strip()
    except Exception as exc:
        logger.warning("Anthropic summary failed: %s", exc)
        return ""


def _plain_summary(standups: list[dict], team_name: str) -> str:
    """Plain text summary — no AI needed."""
    total = len(standups)
    with_blockers = sum(1 for s in standups if s.get("has_blockers"))

    summary = f"📊 *Team Summary* — {total} standup{'s' if total != 1 else ''} submitted"
    if team_name:
        summary = f"📊 *{team_name} Summary* — {total} standup{'s' if total != 1 else ''} submitted"

    if with_blockers:
        summary += f"\n⚠️ {with_blockers} team member{'s' if with_blockers != 1 else ''} reported blockers"

    return summary
