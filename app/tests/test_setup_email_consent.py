"""No email to a Slack-sourced address until the installer asks for it.

Slack's marketplace guidelines: an app that reads addresses through
users:read.email must get explicit consent before contacting anybody, during
install or onboarding. The welcome email went out the moment the OAuth
callback finished, the day-seven follow-up a week later, a weekly digest every
Sunday and a farewell on uninstall, all to the installer's Slack address and
none of them asked for.

The ask is now a button in the install DM and on the App Home. Pressing it is
the consent, stored per workspace with who pressed it and when.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.support import patch_modules

APP = pathlib.Path(__file__).resolve().parents[1]


def _consent_module():
    return importlib.import_module("src.core.email_consent")


class FakeBolt:
    def __init__(self):
        self.actions = {}

    def action(self, name):
        return lambda fn: self.actions.setdefault(name, fn)


@pytest.fixture
def db():
    fake = MagicMock()
    fake.get_installation.return_value = {"team_id": "T1", "team_name": "Northwind", "installed_by_user_id": "U_INST"}
    fake.setup_email_consent.return_value = None
    fake.install_email_sent.return_value = False
    fake.email_is_suppressed.return_value = False
    with patch_modules({"src.core.db": fake}):
        yield fake


def _click(action_id, user="U_INST", container=None):
    bolt = FakeBolt()
    _consent_module().register_slack(bolt)
    client = MagicMock()
    client.users_info.return_value = {"user": {"profile": {"email": "priya@example.com", "real_name": "Priya"}}}
    body = {"user": {"id": user, "team_id": "T1"}, "team": {"id": "T1"}}
    if container:
        body["container"] = container
    ack = MagicMock()
    bolt.actions[action_id](ack=ack, body=body, client=client)
    ack.assert_called_once()
    return client


class TestTheMigration:
    def test_consent_is_stored_per_workspace_and_deleted_with_it(self):
        sql = (APP / "src/core/migrations/061_setup_email_consent.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS setup_email_consents" in sql
        assert "REFERENCES installations(team_id) ON DELETE CASCADE" in sql
        for column in ("user_id", "granted_at", "revoked_at"):
            assert column in sql


class TestInstallSendsNoEmail:
    def test_the_oauth_callback_does_not_email_anybody(self):
        src = (APP / "src/core/oauth.py").read_text()
        assert "mailer.send(" not in src
        assert "welcome_html" not in src

    def test_the_install_dm_offers_the_button(self):
        blocks = _consent_module().offer_blocks()
        text = json.dumps(blocks)
        buttons = [e for b in blocks if b["type"] == "actions" for e in b["elements"]]
        assert [b["action_id"] for b in buttons] == ["email:opt_in"]
        assert "Email me setup tips" in text
        # Plain about what they get, and that it stops.
        assert "welcome email" in text and "any time" in text

    def test_the_callback_puts_the_offer_in_the_welcome_dm(self):
        src = (APP / "src/core/oauth.py").read_text()
        assert "offer_blocks()" in src


class TestOptingIn:
    def test_the_installer_pressing_it_records_consent_and_sends_the_welcome(self, db):
        with patch("src.core.mailer.send", return_value=True) as send:
            client = _click("email:opt_in")
        db.grant_setup_email_consent.assert_called_once_with("T1", "U_INST")
        assert send.call_args.args[0] == "priya@example.com"
        db.record_install_email.assert_any_call("T1", "welcome", "priya@example.com")
        confirmation = client.chat_postMessage.call_args.kwargs["text"]
        assert "Home tab" in confirmation

    def test_somebody_else_cannot_opt_the_installer_in(self, db):
        with patch("src.core.mailer.send", return_value=True) as send:
            client = _click("email:opt_in", user="U_OTHER")
        db.grant_setup_email_consent.assert_not_called()
        send.assert_not_called()
        client.users_info.assert_not_called()
        assert "installed" in client.chat_postMessage.call_args.kwargs["text"]

    def test_pressing_it_twice_sends_one_welcome(self, db):
        db.install_email_sent.return_value = True
        with patch("src.core.mailer.send", return_value=True) as send:
            _click("email:opt_in")
        db.grant_setup_email_consent.assert_called_once()
        send.assert_not_called()

    def test_the_button_in_the_dm_is_replaced_once_pressed(self, db):
        container = {"type": "message", "channel_id": "D1", "message_ts": "1.2"}
        with patch("src.core.mailer.send", return_value=True):
            client = _click("email:opt_in", container=container)
        update = client.chat_update.call_args.kwargs
        assert update["channel"] == "D1" and update["ts"] == "1.2"
        assert "email:opt_in" not in json.dumps(update["blocks"])


class TestOptingOut:
    def test_stop_withdraws_consent(self, db):
        db.setup_email_consent.return_value = {"user_id": "U_INST"}
        client = _click("email:opt_out")
        db.revoke_setup_email_consent.assert_called_once_with("T1")
        assert "stopped" in client.chat_postMessage.call_args.kwargs["text"].lower()

    def test_only_the_person_who_opted_in_can_stop_it(self, db):
        db.setup_email_consent.return_value = {"user_id": "U_INST"}
        _click("email:opt_out", user="U_OTHER")
        db.revoke_setup_email_consent.assert_not_called()


class TestTheAppHome:
    def test_the_installer_is_offered_the_button(self, db):
        blocks = _consent_module().home_blocks("T1", "U_INST")
        assert "email:opt_in" in json.dumps(blocks)

    def test_once_on_it_offers_a_way_to_stop(self, db):
        db.setup_email_consent.return_value = {"user_id": "U_INST"}
        text = json.dumps(_consent_module().home_blocks("T1", "U_INST"))
        assert "email:opt_out" in text and "email:opt_in" not in text

    def test_other_members_see_nothing(self, db):
        assert _consent_module().home_blocks("T1", "U_OTHER") == []

    def test_core_adds_it_to_the_home_tab(self):
        src = (APP / "src/core/home.py").read_text()
        assert "email_consent" in src

    def test_core_registers_the_buttons(self):
        src = (APP / "src/main.py").read_text()
        assert "email_consent import register_slack" in src


class TestEveryInstallerEmailNeedsConsent:
    @pytest.fixture
    def mailer(self):
        for name in ("resend",):
            sys.modules.setdefault(name, MagicMock())
        return importlib.import_module("src.core.mailer")

    def _followups(self, mailer, db, consent):
        db.workspaces_awaiting_followup.return_value = [
            {"team_id": "T1", "team_name": "Northwind", "installed_by_user_id": "U_INST", "standups": 3, "people": 2}
        ]
        db.setup_email_consent.return_value = consent
        db.get_all_members.return_value = [{"user_id": "U_INST", "email": "priya@example.com"}]
        with patch.object(mailer, "send", return_value=True) as send:
            result = mailer.send_install_followups()
        return result, send

    def test_the_follow_up_skips_a_workspace_that_never_opted_in(self, mailer, db):
        (sent, _), send = self._followups(mailer, db, None)
        assert sent == 0
        send.assert_not_called()
        # Not recorded, so it can still go out if they opt in later.
        db.record_install_email.assert_not_called()

    def test_the_follow_up_goes_to_the_person_who_opted_in(self, mailer, db):
        (sent, _), send = self._followups(mailer, db, {"user_id": "U_INST"})
        assert sent == 1
        assert send.call_args.args[0] == "priya@example.com"

    def test_the_farewell_needs_consent(self, mailer, db):
        db.get_all_members.return_value = [{"user_id": "U_INST", "email": "priya@example.com"}]
        with patch.object(mailer, "send", return_value=True) as send:
            mailer.farewell("T1")
        send.assert_not_called()

    def test_the_farewell_goes_out_with_consent(self, mailer, db):
        db.setup_email_consent.return_value = {"user_id": "U_INST"}
        db.get_all_members.return_value = [{"user_id": "U_INST", "email": "priya@example.com"}]
        db.count_standups.return_value = 0
        with patch.object(mailer, "send", return_value=True) as send:
            mailer.farewell("T1")
        assert send.call_args.args[0] == "priya@example.com"

    def test_the_footer_says_why_and_where_to_stop(self, mailer):
        html = mailer.followup_stalled_html("T", "p@example.com")
        assert "Home tab" in html


class TestTheWeeklyDigest:
    """Sent every Sunday to the installer's Slack address, never asked for."""

    def _run(self, db):
        import src.core.scheduler as sched

        db.get_dashboard_stats.return_value = {}
        db.get_participation_stats.return_value = []
        db.get_member_email.return_value = "priya@example.com"
        with patch("src.modules.standup.mailer.send_weekly_digest") as send:
            sched._send_weekly_digest("T1", "xoxb")
        return send

    def test_it_is_not_sent_without_consent(self, db):
        self._run(db).assert_not_called()

    def test_it_goes_to_the_person_who_opted_in(self, db):
        db.setup_email_consent.return_value = {"user_id": "U_INST"}
        send = self._run(db)
        db.get_member_email.assert_called_with("T1", "U_INST")
        assert send.call_args.kwargs["to_email"] == "priya@example.com"

    def test_an_unsubscribed_address_is_not_sent_to(self, db):
        db.setup_email_consent.return_value = {"user_id": "U_INST"}
        db.email_is_suppressed.return_value = True
        self._run(db).assert_not_called()

    def test_it_carries_an_unsubscribe_link_and_says_where_to_stop(self):
        from src.modules.standup import mailer as standup_mailer

        with patch.object(standup_mailer, "_send") as fake:
            standup_mailer.send_weekly_digest("p@example.com", "Northwind", {}, [])
        html = fake.call_args.args[2]
        assert "/email/unsubscribe" in html and "Home tab" in html


class TestReplyTo:
    """Replies go to the address the site and the Marketplace listing show."""

    def test_app_email_replies_go_to_hello(self):
        for path in ("src/core/mailer.py", "src/modules/standup/mailer.py"):
            src = (APP / path).read_text()
            assert "support@morgenruf.dev" not in src, path
            assert "hello@morgenruf.dev" in src, path
