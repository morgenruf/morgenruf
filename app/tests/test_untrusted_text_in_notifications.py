"""Names, answers and titles typed by people in some workspace end up in
emails and in the operator's alert channel. They are data there, never markup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.core import alerts
from src.core import mailer as core_mailer
from src.modules.standup import mailer as standup_mailer

EVIL = '<img src=x onerror=alert(1)><a href="https://evil.test">login</a>'


def _clean(html: str) -> None:
    assert "<img src=x" not in html
    assert 'href="https://evil.test"' not in html
    assert "&lt;img" in html


@pytest.mark.parametrize(
    "render",
    [
        lambda: core_mailer.welcome_html(EVIL, EVIL, "p@example.com"),
        lambda: core_mailer.followup_running_html(EVIL, "p@example.com", 3, 2),
        lambda: core_mailer.followup_stalled_html(EVIL, "p@example.com"),
        lambda: standup_mailer.welcome_email_html(EVIL, EVIL),
        lambda: standup_mailer.first_standup_email_html(EVIL, EVIL, EVIL),
        lambda: standup_mailer.weekly_digest_email_html(EVIL, {"top_responder": EVIL}),
        lambda: standup_mailer.inactive_nudge_email_html(EVIL, 5),
        lambda: standup_mailer.release_announcement_email_html(EVIL, EVIL, "https://x.test/?a=1&b=2"),
    ],
)
def test_email_templates_escape_names(render):
    _clean(render())


def _sent_html(send, **kwargs):
    with patch.object(standup_mailer, "_send") as fake:
        send(**kwargs)
    return fake.call_args.kwargs.get("html") or fake.call_args.args[2]


def test_manager_digest_escapes_names_and_answers():
    html = _sent_html(
        standup_mailer.send_manager_digest,
        manager_email="m@example.com",
        workspace_name=EVIL,
        standups=[{"user_name": EVIL, "yesterday": EVIL, "today": EVIL, "blockers": EVIL}],
        date_str="2026-09-29",
    )
    _clean(html)


def test_weekly_digest_escapes_member_names():
    html = _sent_html(
        standup_mailer.send_weekly_digest,
        to_email="m@example.com",
        team_name=EVIL,
        stats={},
        participation=[{"real_name": EVIL, "responses": 1}],
    )
    _clean(html)


def test_install_alert_escapes_what_the_installing_workspace_controls(monkeypatch):
    monkeypatch.setenv("MORGENRUF_ALERT_WEBHOOK", "https://hooks.slack.com/services/T000/B000/xxxx")
    client = MagicMock()
    client.team_info.return_value = {"team": {"domain": "acme"}}
    client.users_info.return_value = {"user": {"profile": {"real_name": "<!channel>", "title": "<https://evil|sso>"}}}
    with (
        patch("src.core.db.count_installations", return_value=2),
        patch("slack_sdk.WebClient", return_value=client),
        patch("requests.post") as post,
    ):
        post.return_value = MagicMock(status_code=200)
        alerts.installed("T1", "<!here> Acme", "U1", bot_token="xoxb-1")
    text = post.call_args.kwargs["json"]["text"]
    assert "<!here>" not in text and "<!channel>" not in text and "<https://evil" not in text
    assert "&lt;!here&gt; Acme" in text


def test_uninstall_alert_escapes_the_team_name(monkeypatch):
    monkeypatch.setenv("MORGENRUF_ALERT_WEBHOOK", "https://hooks.slack.com/services/T000/B000/xxxx")
    with patch("requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        alerts.uninstalled("T1", "<!channel>")
    assert "<!channel>" not in post.call_args.kwargs["json"]["text"]
