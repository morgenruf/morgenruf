"""Config loader — reads teams.yaml and environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


def get_slack_tokens() -> tuple[str, str]:
    bot_token = os.environ["SLACK_BOT_TOKEN"]
    signing_secret = os.environ["SLACK_SIGNING_SECRET"]
    return bot_token, signing_secret


def load_teams(path: str = "teams.yaml") -> list[dict]:
    """Load team definitions from teams.yaml."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"teams.yaml not found at {p.absolute()}")
    with open(p) as f:
        data = yaml.safe_load(f)
    return data.get("teams", [])


def get_port() -> int:
    return int(os.environ.get("PORT", "3000"))
