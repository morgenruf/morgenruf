"""The checks Slack's reviewers make, run on every commit.

Marketplace review tests endpoints for request signing, and reviews that "the
data access requested is only what is required for the app to function". Both
have been wrong here before: coffee chats shipped with three scopes missing
from the install URL, and reactions:write sat in the manifest for months with
no caller.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
import yaml

APP = pathlib.Path(__file__).resolve().parent.parent
REPO = APP.parent
MANIFEST_YAML = REPO / "slack-manifest.yaml"
MANIFEST_JSON = REPO / "slack-manifest.json"

from src.core.scopes import BOT_SCOPES  # noqa: E402


def manifest():
    return yaml.safe_load(MANIFEST_YAML.read_text())


class TestTheManifestAndTheInstallUrlAgree:
    """They disagreed twice, and both times a feature silently did nothing."""

    def test_manifest_scopes_match_the_source_of_truth(self):
        declared = manifest()["oauth_config"]["scopes"]["bot"]
        assert sorted(declared) == sorted(BOT_SCOPES), (
            "slack-manifest.yaml is out of step with src/core/scopes.py; regenerate it rather than editing by hand"
        )

    def test_the_json_manifest_matches_too(self):
        if not MANIFEST_JSON.exists():
            pytest.skip("no JSON manifest")
        declared = json.loads(MANIFEST_JSON.read_text())["oauth_config"]["scopes"]["bot"]
        assert sorted(declared) == sorted(BOT_SCOPES)

    def test_the_install_url_requests_exactly_those_scopes(self):
        src = (APP / "src/core/oauth.py").read_text()
        assert "BOT_SCOPES" in src, "the install URL must read the shared list"
        assert not re.search(r'_SCOPES\s*=\s*\[\s*"', src), "no hand-kept copy of the scopes"

    def test_the_dashboard_reauthorise_link_uses_them(self):
        src = (APP / "src/core/dashboard.py").read_text()
        assert "SCOPE_STRING" in src


class TestEveryScopeIsUsed:
    """Slack reviews that the data access requested is only what is required."""

    # The API call, or code marker, that justifies each scope.
    EVIDENCE = {
        "commands": [r"@app\.command"],
        "app_mentions:read": [r'@app\.event\("app_mention"\)'],
        "chat:write": [r"chat_postMessage", r"client\.chat_"],
        "channels:read": [r"conversations_members", r"conversations_list"],
        "groups:read": [r"conversations_members", r"conversations_list"],
        "im:write": [r"conversations_open"],
        "im:history": [r'@app\.event\("message', r"message\.im"],
        "im:read": [r"conversations_open", r"conversations_list"],
        "mpim:write": [r"conversations_open"],
        "mpim:history": [r"conversations_history"],
        "users:read": [r"users_list", r"users_info"],
        "users:read.email": [r"users_list", r"users_info"],
        "users.profile:read": [r"users_profile_get", r"users_info"],
        "emoji:read": [r"emoji_list"],
        "team:read": [r"team_info"],
    }

    @staticmethod
    @pytest.fixture(scope="class")
    def source():
        return "\n".join(p.read_text(errors="ignore") for p in (APP / "src").rglob("*.py"))

    @pytest.mark.parametrize("scope", sorted(BOT_SCOPES))
    def test_scope_has_a_caller(self, scope, source):
        patterns = self.EVIDENCE.get(scope)
        assert patterns, f"{scope} has no documented justification"
        assert any(re.search(p, source) for p in patterns), (
            f"{scope} is requested but nothing in src/ uses it. Either wire it up or "
            f"drop it: Slack rejects apps asking for data they do not need."
        )

    def test_every_scope_says_why_it_exists(self):
        empty = [s for s, why in BOT_SCOPES.items() if len(why) < 20]
        assert not empty, f"scopes with no stated reason: {empty}"

    def test_no_scope_slack_rejects(self):
        forbidden = ("admin.", "identity.", "search:read", "workflow.steps:execute", "triggers:")
        bad = [s for s in BOT_SCOPES if s.startswith(forbidden)]
        assert not bad, f"Slack does not approve these for non-partners: {bad}"

    def test_no_channel_history_scope(self):
        """The app reads its own DMs and group DMs, never a channel's history."""
        assert "channels:history" not in BOT_SCOPES
        assert "groups:history" not in BOT_SCOPES


class TestSlashCommands:
    """Slack asks for app-prefixed names. /help collides with every other app."""

    def test_commands_are_prefixed(self):
        commands = [c["command"] for c in manifest()["features"]["slash_commands"]]
        prefixed = [c for c in commands if c.startswith("/morgenruf")]
        assert len(prefixed) >= 4, f"expected app-prefixed commands, got {commands}"

    def test_generic_help_is_not_registered(self):
        commands = [c["command"] for c in manifest()["features"]["slash_commands"]]
        assert "/help" not in commands, "/help collides with other apps in the workspace"

    def test_every_manifest_command_has_a_handler(self):
        source = "\n".join(p.read_text(errors="ignore") for p in (APP / "src").rglob("*.py"))
        missing = [
            c["command"]
            for c in manifest()["features"]["slash_commands"]
            if f'@app.command("{c["command"]}")' not in source
        ]
        assert not missing, f"commands offered in Slack with nothing behind them: {missing}"

    def test_the_old_names_still_work(self):
        """Nine workspaces use these today; renaming without an alias breaks them."""
        commands = [c["command"] for c in manifest()["features"]["slash_commands"]]
        for legacy in ("/standup", "/skip", "/kudos"):
            assert legacy in commands


class TestTheSecurityBasics:
    def test_requests_are_verified(self):
        assert "SLACK_SIGNING_SECRET" in (APP / "src/main.py").read_text()

    def test_oauth_state_is_signed_and_checked(self):
        src = (APP / "src/core/oauth.py").read_text()
        assert "hmac" in src and "_verify_state" in src

    def test_uninstall_deletes_the_workspace(self):
        src = (APP / "src/modules/standup/handlers.py").read_text()
        assert '@app.event("app_uninstalled")' in src
        assert '@app.event("tokens_revoked")' in src
