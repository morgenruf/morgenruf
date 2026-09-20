"""The two emails the app sends about itself, and the rules around them.

Fourteen of the first twenty workspaces never created a standup, and nothing
ever asked them why. The welcome email told them "team members receive a DM
each morning", which was not true for any of those fourteen.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

for mod in ("psycopg2", "psycopg2.extras", "psycopg2.pool", "slack_sdk", "slack_bolt", "resend"):
    sys.modules.setdefault(mod, MagicMock())

from src.core import mailer  # noqa: E402

from tests.support import patch_modules  # noqa: E402


class TestTheWelcomeSaysWhatIsTrue:
    def test_it_does_not_promise_messages_that_will_not_be_sent(self):
        html = mailer.welcome_html("Northwind", "Priya", "p@example.com")
        assert "Nothing will happen yet" in html, (
            "the old one said team members would get a DM each morning, which is false until somebody creates a standup"
        )

    def test_it_has_one_thing_to_press(self):
        html = mailer.welcome_html("Northwind", "Priya", "p@example.com")
        assert html.count("Create your first standup") == 1
        assert "/dashboard" in html

    def test_it_names_the_workspace_and_the_installer(self):
        html = mailer.welcome_html("Northwind", "Priya Raman", "p@example.com")
        assert "Northwind" in html and "Priya Raman" in html


class TestTheFollowUpAsksTheRightQuestion:
    def test_a_running_workspace_is_asked_what_annoys_them(self):
        html = mailer.followup_running_html("Northwind", "p@example.com", 33, 7)
        assert "most annoying" in html
        assert "33 answers from 7 people" in html

    def test_one_person_is_not_pluralised(self):
        html = mailer.followup_running_html("Solo", "p@example.com", 5, 1)
        assert "from 1 person" in html

    def test_a_stalled_workspace_is_asked_what_stopped_them(self):
        html = mailer.followup_stalled_html("B1", "p@example.com")
        assert "what stopped you" in html.lower()
        assert "Nothing has run" in html

    def test_the_stalled_one_lists_the_real_sticking_points(self):
        html = mailer.followup_stalled_html("B1", "p@example.com")
        for point in ("/invite @Morgenruf", "three extra Slack scopes", "Microsoft Teams"):
            assert point in html


class TestEveryMessageCanBeStopped:
    """A message that asks for something needs a working unsubscribe."""

    @pytest.mark.parametrize(
        "html",
        [
            mailer.welcome_html("T", "P", "p@example.com"),
            mailer.followup_running_html("T", "p@example.com", 3, 2),
            mailer.followup_stalled_html("T", "p@example.com"),
        ],
    )
    def test_it_carries_an_unsubscribe_link(self, html):
        assert "/email/unsubscribe" in html

    @pytest.mark.parametrize(
        "html",
        [
            mailer.welcome_html("T", "P", "p@example.com"),
            mailer.followup_stalled_html("T", "p@example.com"),
        ],
    )
    def test_it_says_who_is_writing_and_gives_a_mailing_address(self, html):
        assert "CloudDrove" in html and "Toronto, Ontario" in html

    def test_the_token_is_tied_to_the_address(self):
        a = mailer.unsubscribe_token("one@example.com")
        b = mailer.unsubscribe_token("two@example.com")
        assert a != b and len(a) == 32

    def test_the_token_ignores_case(self):
        assert mailer.unsubscribe_token("A@Example.com") == mailer.unsubscribe_token("a@example.com")


class TestNothingIsSentToSomebodyWhoAskedNotToBe:
    def test_a_suppressed_address_is_never_sent_to(self):
        db = MagicMock()
        db.email_is_suppressed.return_value = True
        with patch_modules({"src.core.db": db}):
            assert mailer.send("gone@example.com", "subject", "<p>body</p>") is False

    def test_an_unreadable_suppression_list_stops_the_send(self):
        """Failing open would email people who had unsubscribed."""
        db = MagicMock()
        db.email_is_suppressed.side_effect = RuntimeError("database down")
        with patch_modules({"src.core.db": db}):
            assert mailer.send("someone@example.com", "s", "<p>b</p>") is False

    def test_no_address_means_no_send(self):
        assert mailer.send("", "s", "<p>b</p>") is False


class TestTheFollowUpRunsOnce:
    """One message per workspace, and never twice."""

    @staticmethod
    def _rows(**over):
        row = {
            "team_id": "T1",
            "team_name": "Northwind",
            "installed_by_user_id": "U1",
            "schedules": 1,
            "standups": 33,
            "people": 7,
        }
        row.update(over)
        return [row]

    @pytest.fixture()
    def run(self, monkeypatch):
        """Run the pass against a fake database, restoring everything after."""

        def go(rows, *, email="p@example.com", delivers=True):
            db = MagicMock()
            db.workspaces_awaiting_followup.return_value = rows
            db.email_is_suppressed.return_value = False
            db.get_all_members.return_value = [{"user_id": "U1", "email": email}]
            monkeypatch.setattr(mailer, "send", lambda *a, **k: delivers)
            with patch_modules({"src.core.db": db}):
                return mailer.send_install_followups(), db

        return go

    def test_a_workspace_with_standups_gets_the_running_version(self, run):
        (sent, skipped), db = run(self._rows())
        assert (sent, skipped) == (1, 0)
        assert db.record_install_email.call_args[0][1] == "followup:running"

    def test_a_workspace_with_none_gets_the_stalled_version(self, run):
        _, db = run(self._rows(team_name="B1", schedules=0, standups=0, people=0))
        assert db.record_install_email.call_args[0][1] == "followup:stalled"

    def test_a_workspace_with_no_address_is_recorded_not_retried(self, run):
        """Seven workspaces have no address on file. Without a record they
        would be picked up again every single day, for ever."""
        (sent, skipped), db = run(self._rows(standups=0), email="")
        assert (sent, skipped) == (0, 1)
        assert db.record_install_email.call_args[0][1] == "followup:no-address"

    def test_a_failed_send_is_recorded_so_it_does_not_loop(self, run):
        (sent, skipped), db = run(self._rows(), delivers=False)
        assert (sent, skipped) == (0, 1)
        assert "undeliverable" in db.record_install_email.call_args[0][1]

    def test_a_listing_failure_is_survivable(self, monkeypatch):
        db = MagicMock()
        db.workspaces_awaiting_followup.side_effect = RuntimeError("database down")
        with patch_modules({"src.core.db": db}):
            assert mailer.send_install_followups() == (0, 0)


class TestTheUnsubscribeEndpoint:
    """A link in an email, so no session, which makes the token the only guard."""

    @pytest.fixture()
    def client(self, monkeypatch):
        import os

        os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
        import src.core.dashboard as dashboard
        from flask import Flask

        db = MagicMock()
        monkeypatch.setattr(dashboard, "db", db)
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret"
        app.register_blueprint(dashboard.dashboard_bp)
        app.register_blueprint(dashboard.browser_bp)
        return app.test_client(), db

    def test_a_valid_link_suppresses_the_address(self, client):
        c, db = client
        email = "someone@example.com"
        r = c.get(f"/email/unsubscribe?e={email}&t={mailer.unsubscribe_token(email)}")
        assert r.status_code == 303
        assert r.location == "/email/result?status=unsubscribed"
        db.suppress_email.assert_called_once_with(email)

    def test_a_forged_token_changes_nothing(self, client):
        c, db = client
        r = c.get("/email/unsubscribe?e=victim@example.com&t=not-the-right-token")
        assert r.status_code == 303
        assert r.location == "/email/result?status=invalid"
        db.suppress_email.assert_not_called()

    def test_somebody_elses_token_does_not_work_on_your_address(self, client):
        c, db = client
        stolen = mailer.unsubscribe_token("mine@example.com")
        r = c.get(f"/email/unsubscribe?e=victim@example.com&t={stolen}")
        assert r.status_code == 303
        assert r.location == "/email/result?status=invalid"
        db.suppress_email.assert_not_called()

    def test_mail_clients_can_post_to_it(self, client):
        """List-Unsubscribe-Post sends a POST with no body."""
        c, db = client
        email = "someone@example.com"
        r = c.post(f"/email/unsubscribe?e={email}&t={mailer.unsubscribe_token(email)}")
        assert r.status_code == 200
        db.suppress_email.assert_called_once()


class TestTheFarewell:
    """The message that catches the thing nobody has been learning.

    Eleven of the first twenty workspaces removed the app, including companies
    worth listening to, and not one was ever asked why.
    """

    def test_it_confirms_the_deletion_first(self):
        html = mailer.uninstall_html("TUM Venture Labs", "s@example.com", 29, 0)
        assert "has been deleted" in html
        assert html.index("deleted") < html.index("What was wrong")

    def test_it_says_when_nothing_ever_ran(self):
        html = mailer.uninstall_html("B1", "s@example.com", 18, 0)
        assert "never ran a standup" in html

    def test_it_counts_the_standups_when_there_were_some(self):
        html = mailer.uninstall_html("Northwind", "s@example.com", 90, 240)
        assert "240 standups over 90 days" in html

    def test_it_does_not_try_to_win_them_back(self):
        html = mailer.uninstall_html("X", "s@example.com", 10, 0)
        for plea in ("come back", "reconsider", "special offer", "discount"):
            assert plea not in html.lower()

    def test_it_promises_no_further_email(self):
        assert "No follow-up after this one" in mailer.uninstall_html("X", "s@example.com", 3, 0)

    def test_it_is_sent_before_the_data_is_deleted(self):
        """Called after the delete, it has no address and no history to use."""
        import pathlib

        app_root = pathlib.Path(__file__).resolve().parents[1]
        src = (app_root / "src/modules/standup/handlers.py").read_text()
        for handler in ("tokens_revoked", "app_uninstalled"):
            block = src[src.index(f'@app.event("{handler}")') :]
            block = block[: block.index("deleted = db.delete_installation")]
            assert "farewell(team_id)" in block, f"{handler} deletes before it asks"


class TestConsentIsAskedForNotAssumed:
    def test_the_welcome_asks_rather_than_subscribing_them(self):
        html = mailer.welcome_html("T", "P", "p@example.com")
        assert "You are not subscribed to anything yet" in html
        assert "/email/subscribe" in html

    def test_the_link_is_tied_to_the_address(self):
        a = mailer.subscribe_url("one@example.com")
        assert "one%40example.com" in a and mailer.unsubscribe_token("one@example.com") in a

    def test_nothing_is_synced_without_an_audience(self, monkeypatch):
        """A self-hosted install must never post its users to our contact list."""
        monkeypatch.delenv("RESEND_AUDIENCE_ID", raising=False)
        assert mailer.sync_contact("someone@example.com") is False
