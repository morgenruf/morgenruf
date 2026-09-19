"""The operator alert: a line in Slack when a workspace arrives or leaves.

The rule these tests hold to is that an alert never breaks the thing it is
reporting on. A missing webhook, a dead webhook, an unreachable database: all
of them are a False and a log line, never an exception into the install flow.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.core import alerts


@pytest.fixture(autouse=True)
def _no_webhook(monkeypatch):
    monkeypatch.delenv("MORGENRUF_ALERT_WEBHOOK", raising=False)


@pytest.fixture
def webhook(monkeypatch):
    url = "https://hooks.slack.com/services/T000/B000/xxxx"
    monkeypatch.setenv("MORGENRUF_ALERT_WEBHOOK", url)
    return url


class TestNotifyIsOptional:
    def test_unset_webhook_sends_nothing(self):
        with patch("requests.post") as post:
            assert alerts.notify("hello") is False
        post.assert_not_called()

    def test_blank_webhook_sends_nothing(self, monkeypatch):
        monkeypatch.setenv("MORGENRUF_ALERT_WEBHOOK", "   ")
        with patch("requests.post") as post:
            assert alerts.notify("hello") is False
        post.assert_not_called()

    def test_configured_webhook_posts_the_text(self, webhook):
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200)
            assert alerts.notify("hello") is True
        args, kwargs = post.call_args
        assert args[0] == webhook
        assert kwargs["json"] == {"text": "hello"}
        assert kwargs["timeout"] == alerts.TIMEOUT


class TestNotifyNeverRaises:
    def test_a_dead_webhook_is_false_not_an_exception(self, webhook):
        with patch("requests.post", side_effect=OSError("connection refused")):
            assert alerts.notify("hello") is False

    def test_an_error_status_is_false(self, webhook):
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=404)
            assert alerts.notify("hello") is False

    def test_an_internal_url_is_refused(self, monkeypatch):
        """The webhook is operator-set, but SSRF protection is not optional."""
        monkeypatch.setenv("MORGENRUF_ALERT_WEBHOOK", "http://169.254.169.254/latest/meta-data/")
        with patch("requests.post") as post:
            assert alerts.notify("hello") is False
        post.assert_not_called()


class TestTheInstallAlert:
    def test_names_the_workspace_and_the_running_total(self, webhook):
        with patch("src.core.db.count_installations", return_value=21), patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200)
            alerts.installed("T123", "Acme Inc", "U999")
        text = post.call_args.kwargs["json"]["text"]
        assert "Acme Inc" in text
        assert "U999" in text
        assert "21 workspaces now." in text

    def test_falls_back_to_team_id_when_the_name_is_missing(self, webhook):
        with patch("src.core.db.count_installations", return_value=1), patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200)
            alerts.installed("T123", "")
        assert "T123" in post.call_args.kwargs["json"]["text"]

    def test_a_broken_database_still_sends_the_alert(self, webhook):
        with (
            patch("src.core.db.count_installations", side_effect=RuntimeError("no db")),
            patch("requests.post") as post,
        ):
            post.return_value = MagicMock(status_code=200)
            assert alerts.installed("T123", "Acme Inc") is True


class TestTheUninstallAlert:
    def test_zero_standups_is_called_out(self, webhook):
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200)
            alerts.uninstalled("T123", "Acme Inc", days=29, standups=0)
        text = post.call_args.kwargs["json"]["text"]
        assert "29 days" in text
        assert "Never got set up." in text

    def test_a_used_workspace_is_not_called_out(self, webhook):
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200)
            alerts.uninstalled("T123", "Acme Inc", days=90, standups=40)
        text = post.call_args.kwargs["json"]["text"]
        assert "40 standups" in text
        assert "Never got set up." not in text

    def test_singular_day_reads_correctly(self, webhook):
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200)
            alerts.uninstalled("T123", "Acme Inc", days=1, standups=1)
        text = post.call_args.kwargs["json"]["text"]
        assert "after 1 day" in text
        assert "1 standup run." in text


class TestDepartedReadsBeforeTheDelete:
    def test_it_gathers_stats_from_the_row_about_to_go(self, webhook):
        from datetime import datetime, timedelta, timezone

        install = {
            "team_name": "Acme Inc",
            "installed_at": datetime.now(timezone.utc) - timedelta(days=29),
        }
        with (
            patch("src.core.db.get_installation", return_value=install),
            patch("src.core.db.count_standups", return_value=0),
            patch("requests.post") as post,
        ):
            post.return_value = MagicMock(status_code=200)
            assert alerts.departed("T123") is True
        text = post.call_args.kwargs["json"]["text"]
        assert "Acme Inc" in text
        assert "29 days" in text
        assert "Never got set up." in text

    def test_a_missing_installation_is_silent(self, webhook):
        with patch("src.core.db.get_installation", return_value=None), patch("requests.post") as post:
            assert alerts.departed("T123") is False
        post.assert_not_called()

    def test_a_broken_database_does_not_raise(self, webhook):
        with patch("src.core.db.get_installation", side_effect=RuntimeError("no db")):
            assert alerts.departed("T123") is False


class TestTheAlertRunsBeforeDeletion:
    """Same constraint as the farewell email: the data is in the doomed rows."""

    def test_departed_is_called_before_delete_installation(self):
        import inspect

        from src.modules.standup import handlers

        source = inspect.getsource(handlers)
        for handler in ("handle_tokens_revoked", "handle_app_uninstalled"):
            start = source.index(f"def {handler}")
            body = source[start : start + 1200]
            assert body.index("departed(team_id)") < body.index("db.delete_installation")
