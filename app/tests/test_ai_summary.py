"""Tests for ai_summary.py — summary generation and fallback."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
from ai_summary import _plain_summary, generate_summary

# ---------------------------------------------------------------------------
# Plain summary (no AI key)
# ---------------------------------------------------------------------------

class TestPlainSummary:
    def test_single_standup_no_blockers(self):
        standups = [{"user_id": "U1", "yesterday": "shipped feature", "today": "review PRs", "has_blockers": False}]
        result = _plain_summary(standups, "Acme")
        assert "1 standup submitted" in result
        assert "Acme" in result
        assert "blocker" not in result

    def test_multiple_standups_plural(self):
        standups = [
            {"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False},
            {"user_id": "U2", "yesterday": "c", "today": "d", "has_blockers": False},
        ]
        result = _plain_summary(standups, "Team")
        assert "2 standups submitted" in result

    def test_blockers_shown(self):
        standups = [
            {"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": True},
            {"user_id": "U2", "yesterday": "c", "today": "d", "has_blockers": False},
        ]
        result = _plain_summary(standups, "Team")
        assert "1 team member" in result
        assert "blocker" in result

    def test_multiple_blockers_plural(self):
        standups = [
            {"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": True},
            {"user_id": "U2", "yesterday": "c", "today": "d", "has_blockers": True},
        ]
        result = _plain_summary(standups, "Team")
        assert "2 team members" in result

    def test_no_team_name(self):
        standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
        result = _plain_summary(standups, "")
        assert "Team Summary" in result

    def test_with_team_name(self):
        standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
        result = _plain_summary(standups, "Engineering")
        assert "Engineering Summary" in result


# ---------------------------------------------------------------------------
# generate_summary — routing and fallbacks
# ---------------------------------------------------------------------------

class TestGenerateSummary:
    def test_empty_standups_returns_empty(self):
        assert generate_summary([]) == ""

    def test_falls_back_to_plain_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
        result = generate_summary(standups, "Team")
        assert "standup" in result.lower()

    def test_uses_openai_when_key_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Great work by the team today!"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
            result = generate_summary(standups, "Team")
        assert result == "Great work by the team today!"

    def test_uses_anthropic_when_key_set(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"text": "The team made solid progress."}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
            result = generate_summary(standups, "Team")
        assert result == "The team made solid progress."

    def test_openai_failure_returns_empty_string(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with patch("httpx.post", side_effect=Exception("timeout")):
            standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
            result = generate_summary(standups, "Team")
        assert result == ""

    def test_anthropic_failure_returns_empty_string(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        with patch("httpx.post", side_effect=Exception("connection error")):
            standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
            result = generate_summary(standups, "Team")
        assert result == ""

    def test_prefers_openai_over_anthropic(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "OpenAI response"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            standups = [{"user_id": "U1", "yesterday": "a", "today": "b", "has_blockers": False}]
            result = generate_summary(standups, "Team")

        # Should have called OpenAI endpoint
        call_url = mock_post.call_args[0][0]
        assert "openai.com" in call_url
        assert result == "OpenAI response"
