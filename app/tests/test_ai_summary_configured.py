"""Whether this deployment can write an AI summary at all.

The hosted instance has no OpenAI or Anthropic key, yet the standup form
offered "Enable AI-generated daily summary". Switched on, the report thread got
a plain count of answers labelled "AI Summary". The form now asks the backend
whether a key exists, the same way the Zoom settings ask about Zoom, and the
scheduler ignores the switch when there is none.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import src.core.scheduler as sched_mod
from src.modules.standup import ai_summary

from tests.support import patch_modules


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class TestConfigured:
    def test_no_key_means_not_configured(self, no_keys):
        assert ai_summary.configured() is False

    @pytest.mark.parametrize("key", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
    def test_either_key_is_enough(self, no_keys, monkeypatch, key):
        monkeypatch.setenv(key, "sk-test")
        assert ai_summary.configured() is True

    def test_a_blank_key_does_not_count(self, no_keys, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "  ")
        assert ai_summary.configured() is False


def _db():
    db = MagicMock()
    db.get_today_standups.return_value = [
        {"user_id": "U1", "yesterday": "a", "today": "b", "blockers": "", "has_blockers": False}
    ]
    db.get_standup_schedule.return_value = {
        "id": 1,
        "name": "Daily standup",
        "participants": ["U1"],
        "questions": [],
        "post_summary": True,
        "group_by": "member",
        "report_channel": "",
    }
    db.get_workspace_config.return_value = {"questions": [], "ai_summary_enabled": True}
    db.get_daily_thread_ts.return_value = None
    db.get_installation.return_value = {"team_name": "Acme", "bot_token": "xoxb-test"}
    return db


def test_the_switch_is_ignored_without_a_key(no_keys):
    """The fallback text was posted under an "AI Summary" heading."""
    client = MagicMock()
    client.token = "xoxb-test"
    client.chat_postMessage.return_value = {"ts": "111.222"}
    with (
        patch_modules({"src.core.db": _db()}),
        patch.object(sched_mod, "WebClient", return_value=client),
        patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb-test"),
        patch.object(sched_mod, "_call_with_auth_retry", return_value=None),
    ):
        sched_mod._post_scheduled_report("T1", "xoxb-test", "C_STANDUP", 1)
    posted = [c.kwargs.get("text", "") for c in client.chat_postMessage.call_args_list]
    assert posted, "the report itself should still post"
    assert not any("AI Summary" in text for text in posted)


class TestTheEndpoint:
    @pytest.fixture
    def client(self, monkeypatch):
        from tests.browser_fixtures import create_test_app

        app = create_test_app(monkeypatch)
        client = app.test_client()
        client.post("/__test__/session?role=member")
        return client

    def test_it_reports_no_key(self, client, monkeypatch):
        monkeypatch.setattr(ai_summary, "configured", lambda: False)
        assert client.get("/dashboard/api/ai-summary").json == {"configured": False}

    def test_it_reports_a_key(self, client, monkeypatch):
        monkeypatch.setattr(ai_summary, "configured", lambda: True)
        assert client.get("/dashboard/api/ai-summary").json == {"configured": True}
