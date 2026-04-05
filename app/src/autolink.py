"""Auto-link issue references in standup summaries posted to Slack.

Supported patterns:
  - Jira:   PROJ-123  →  requires jira_base_url config
  - GitHub: #123      →  requires github_repo config (org/repo)
  - Linear: LIN-123 or any TWO-LETTER prefix: AB-123  →  requires linear_team config
"""

from __future__ import annotations

import re

_JIRA_RE = re.compile(r'\b([A-Z][A-Z0-9]+-\d+)\b')
_GH_RE = re.compile(r'(?<!\w)#(\d+)\b')


def autolink(text: str, config: dict) -> str:
    """Replace issue references with Slack mrkdwn hyperlinks.

    config keys:
        jira_base_url  — e.g. "https://yourco.atlassian.net"
        github_repo    — e.g. "org/repo"
        linear_team    — e.g. "ENG" (prefix for Linear tickets)
    """
    jira_base = (config.get("jira_base_url") or "").rstrip("/")
    github_repo = (config.get("github_repo") or "").strip()
    linear_team = (config.get("linear_team") or "").strip().upper()

    # Jira: PROJ-123 → <https://yourco.atlassian.net/browse/PROJ-123|PROJ-123>
    if jira_base:
        text = _JIRA_RE.sub(
            lambda m: f"<{jira_base}/browse/{m.group(1)}|{m.group(1)}>",
            text,
        )

    # GitHub: #123 → <https://github.com/org/repo/issues/123|#123>
    if github_repo:
        text = _GH_RE.sub(
            lambda m: f"<https://github.com/{github_repo}/issues/{m.group(1)}|#{m.group(1)}>",
            text,
        )

    # Linear: ENG-123 (if linear_team set, only match that prefix)
    if linear_team:
        linear_re = re.compile(rf'\b({re.escape(linear_team)}-\d+)\b')
        text = linear_re.sub(
            lambda m: f"<https://linear.app/issue/{m.group(1)}|{m.group(1)}>",
            text,
        )

    return text
