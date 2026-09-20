"""Product analytics: what workspaces do, counted at the workspace level.

Two rules these tests hold to. The first is the same one the operator alert
keeps: analytics never breaks the thing it is measuring, so every failure is a
log line and a False. The second is specific to this file: a self-hosted
install sends nothing at all unless its operator sets a key, and no event ever
carries a Slack user ID or a line of anyone's standup.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.core import analytics


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    analytics.reset()
    yield
    analytics.reset()


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test_key")
    return "phc_test_key"


@pytest.fixture
def client(key):
    """A configured instance with the SDK stubbed out."""
    with patch("posthog.Posthog") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


class TestAnalyticsIsOptional:
    def test_unset_key_captures_nothing(self):
        with patch("posthog.Posthog") as cls:
            assert analytics.capture("standup_posted", "T123") is False
        cls.assert_not_called()

    def test_blank_key_captures_nothing(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "   ")
        with patch("posthog.Posthog") as cls:
            assert analytics.capture("standup_posted", "T123") is False
        cls.assert_not_called()

    def test_enabled_reports_whether_a_key_is_set(self, monkeypatch):
        assert analytics.enabled() is False
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_test_key")
        assert analytics.enabled() is True


class TestWhereEventsGo:
    def test_the_us_host_is_the_default(self, client):
        analytics.capture("standup_posted", "T123")
        import posthog

        assert posthog.Posthog.call_args.kwargs["host"] == analytics.DEFAULT_HOST
        assert posthog.Posthog.call_args.kwargs["host"].startswith("https://us.")

    def test_the_host_can_be_pointed_elsewhere(self, key, monkeypatch):
        monkeypatch.setenv("POSTHOG_HOST", "https://posthog.internal.example")
        with patch("posthog.Posthog") as cls:
            cls.return_value = MagicMock()
            analytics.capture("standup_posted", "T123")
        assert cls.call_args.kwargs["host"] == "https://posthog.internal.example"

    def test_the_client_is_built_once_and_reused(self, client):
        analytics.capture("standup_posted", "T123")
        analytics.capture("kudos_given", "T123")
        import posthog

        assert posthog.Posthog.call_count == 1
        assert client.capture.call_count == 2


class TestTheEventItself:
    def test_the_workspace_is_the_distinct_id(self, client):
        assert analytics.capture("standup_posted", "T123") is True
        kwargs = client.capture.call_args.kwargs
        assert kwargs["distinct_id"] == "T123"
        assert client.capture.call_args.args[0] == "standup_posted"

    def test_extra_properties_ride_along(self, client):
        analytics.capture("module_enabled", "T123", module="kudos")
        assert client.capture.call_args.kwargs["properties"]["module"] == "kudos"

    def test_the_workspace_is_also_a_group(self, client):
        """Workspace-level events, so PostHog should aggregate them that way."""
        analytics.capture("standup_posted", "T123")
        assert client.capture.call_args.kwargs["groups"] == {"workspace": "T123"}

    def test_an_event_without_a_workspace_is_dropped(self, client):
        assert analytics.capture("standup_posted", "") is False
        client.capture.assert_not_called()


class TestAnalyticsNeverRaises:
    def test_a_broken_client_is_false_not_an_exception(self, key):
        with patch("posthog.Posthog", side_effect=RuntimeError("no network")):
            assert analytics.capture("standup_posted", "T123") is False

    def test_a_failed_capture_is_false_not_an_exception(self, client):
        client.capture.side_effect = OSError("connection refused")
        assert analytics.capture("standup_posted", "T123") is False

    def test_a_missing_sdk_is_false_not_an_exception(self, key):
        with patch.dict("sys.modules", {"posthog": None}):
            assert analytics.capture("standup_posted", "T123") is False


class TestShutdown:
    def test_shutdown_flushes_a_live_client(self, client):
        analytics.capture("standup_posted", "T123")
        analytics.shutdown()
        client.shutdown.assert_called_once()

    def test_shutdown_without_a_client_does_nothing(self):
        analytics.shutdown()
