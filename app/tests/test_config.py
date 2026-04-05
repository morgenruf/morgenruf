"""Tests for config.py — environment variable loading and teams.yaml parsing."""

import os
import sys
import tempfile

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


class TestGetSlackTokens:
    def test_returns_tokens_from_env(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "secret123")
        from config import get_slack_tokens
        bot, signing = get_slack_tokens()
        assert bot == "xoxb-test"
        assert signing == "secret123"

    def test_raises_when_bot_token_missing(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "secret123")
        from config import get_slack_tokens
        with pytest.raises(KeyError):
            get_slack_tokens()

    def test_raises_when_signing_secret_missing(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
        from config import get_slack_tokens
        with pytest.raises(KeyError):
            get_slack_tokens()


class TestGetPort:
    def test_default_port(self, monkeypatch):
        monkeypatch.delenv("PORT", raising=False)
        from config import get_port
        assert get_port() == 3000

    def test_custom_port(self, monkeypatch):
        monkeypatch.setenv("PORT", "8080")
        from config import get_port
        assert get_port() == 8080

    def test_returns_int(self, monkeypatch):
        monkeypatch.setenv("PORT", "5000")
        from config import get_port
        assert isinstance(get_port(), int)


class TestLoadTeams:
    def test_load_valid_teams_yaml(self, tmp_path):
        teams_file = tmp_path / "teams.yaml"
        teams_file.write_text(yaml.dump({
            "teams": [
                {"name": "Engineering", "channel": "C123"},
                {"name": "Design", "channel": "C456"},
            ]
        }))
        from config import load_teams
        teams = load_teams(str(teams_file))
        assert len(teams) == 2
        assert teams[0]["name"] == "Engineering"
        assert teams[1]["channel"] == "C456"

    def test_empty_teams_yaml(self, tmp_path):
        teams_file = tmp_path / "teams.yaml"
        teams_file.write_text(yaml.dump({"teams": []}))
        from config import load_teams
        teams = load_teams(str(teams_file))
        assert teams == []

    def test_missing_file_raises(self, tmp_path):
        from config import load_teams
        with pytest.raises(FileNotFoundError):
            load_teams(str(tmp_path / "nonexistent.yaml"))

    def test_no_teams_key_returns_empty(self, tmp_path):
        teams_file = tmp_path / "teams.yaml"
        teams_file.write_text(yaml.dump({"other_key": "value"}))
        from config import load_teams
        teams = load_teams(str(teams_file))
        assert teams == []
