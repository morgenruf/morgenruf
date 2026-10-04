"""Feedback from the dashboard, filed as a GitHub issue.

The "Send feedback" dialog posts here and each report becomes one issue in the
repository named by FEEDBACK_GITHUB_REPO, using FEEDBACK_GITHUB_TOKEN (a
fine-grained token with Issues read and write on that one repository).

The issue carries the workspace and the sender so a report can be answered,
which is why the repository should be private. Both settings blank turns the
feature off, which is what a self-hosted install gets by default: the dialog
is hidden rather than sending reports to someone else's tracker.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

TIMEOUT = 10
_API = "https://api.github.com"

# What the person picked in the dialog, and how it reads on GitHub.
KINDS = {
    "bug": {"label": "bug", "heading": "Bug report"},
    "idea": {"label": "enhancement", "heading": "Suggestion"},
    "other": {"label": "question", "heading": "Feedback"},
}

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _settings() -> tuple[str, str]:
    token = os.environ.get("FEEDBACK_GITHUB_TOKEN", "").strip()
    repo = os.environ.get("FEEDBACK_GITHUB_REPO", "").strip()
    return token, repo


def enabled() -> bool:
    token, repo = _settings()
    return bool(token and _REPO.match(repo))


def _quiet(text: str) -> str:
    """Stop an @name in someone's report from notifying that GitHub user."""
    return (text or "").replace("@", "@\u200b")


def _body(kind: str, details: str, context: dict) -> str:
    lines = [f"**{KINDS[kind]['heading']}** sent from the dashboard.", ""]
    lines.append(_quiet(details.strip()) or "_No details given._")
    lines += ["", "| | |", "|---|---|"]
    for label, value in (
        ("Workspace", context.get("workspace")),
        ("Sender", context.get("sender")),
        ("Page", context.get("page")),
        ("Browser", context.get("browser")),
        ("Version", context.get("version")),
    ):
        if value:
            cell = _quiet(str(value)).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {label} | `{cell}` |" if label in ("Page", "Browser") else f"| {label} | {cell} |")
    return "\n".join(lines)


def file_issue(kind: str, title: str, details: str, context: dict) -> str | None:
    """Open the issue and return its URL, or None when it could not be filed.

    Never raises: the caller turns None into a message asking to try again.
    """
    token, repo = _settings()
    if not enabled():
        return None
    try:
        import requests  # noqa: PLC0415

        resp = requests.post(
            f"{_API}/repos/{repo}/issues",
            json={
                "title": _quiet(title.strip()),
                "body": _body(kind, details, context),
                "labels": [KINDS[kind]["label"], "feedback"],
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=TIMEOUT,
        )
    except Exception as exc:
        logger.warning("could not reach GitHub to file feedback: %s", exc)
        return None
    if resp.status_code != 201:
        logger.warning("GitHub refused the feedback issue: %s %s", resp.status_code, resp.text[:300])
        return None
    try:
        return resp.json().get("html_url") or ""
    except Exception:
        return ""
