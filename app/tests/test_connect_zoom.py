"""Zoom linking: the token lifecycle, the signed link, and meeting creation.

Two Zoom behaviours make this easy to get silently wrong:

  * An access token lasts an hour, so it has to be refreshed on use.
  * Refreshing ROTATES the refresh token. Zoom's response carries a new one and
    the old one is dead immediately, so failing to persist it breaks the link
    permanently, and only an hour after linking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from src.modules.connect import zoom
from src.modules.connect.zoom_routes import mint_link_token, read_link_token

from tests.support import patch_modules

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def creds(monkeypatch):
    monkeypatch.setenv("ZOOM_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "secret")
    monkeypatch.setenv("APP_URL", "https://api.example.dev")


class TestConfiguration:
    def test_absent_credentials_disable_the_feature(self, monkeypatch):
        monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
        assert zoom.configured() is False

    def test_the_redirect_uri_follows_app_url(self, creds):
        assert zoom.redirect_uri() == "https://api.example.dev/connect/zoom/callback"

    def test_the_authorize_url_carries_state_and_redirect(self, creds):
        url = zoom.authorize_url("STATE123")
        assert url.startswith("https://zoom.us/oauth/authorize?")
        assert "state=STATE123" in url
        assert "client_id=cid" in url


class TestRefreshTokenRotation:
    """The trap. Zoom returns a NEW refresh token on every refresh."""

    def _link(self, expired=True):
        # Relative to the real clock, not to the fixed NOW used for meeting
        # bodies: access_token_for compares against datetime.now.
        real_now = datetime.now(timezone.utc)
        return {
            "access_token": "old-access",
            "refresh_token": "refresh-1",
            "access_expires_at": real_now - timedelta(minutes=5) if expired else real_now + timedelta(hours=1),
        }

    def test_a_live_token_is_used_without_refreshing(self, creds):
        db = MagicMock()
        db.zoom_link.return_value = self._link(expired=False)
        with patch_modules({"src.modules.connect.db": db}), patch.object(zoom, "_token_request") as req:
            assert zoom.access_token_for("T1", "U1") == "old-access"
            req.assert_not_called()

    def test_the_rotated_refresh_token_is_persisted(self, creds):
        db = MagicMock()
        db.zoom_link.return_value = self._link()
        with patch_modules({"src.modules.connect.db": db}), patch.object(zoom, "_token_request") as req:
            req.return_value = {
                "access_token": "new-access",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
            }
            assert zoom.access_token_for("T1", "U1") == "new-access"
        # The new refresh token must reach the database, or the link dies.
        saved = db.save_zoom_link.call_args.kwargs
        assert saved["refresh_token"] == "refresh-2"
        assert saved["access_token"] == "new-access"

    def test_the_store_is_written_before_the_token_is_returned(self, creds):
        # Ordering matters: Zoom has already invalidated refresh-1 by the time
        # it answers, so a caller that uses the token and crashes must not be
        # the reason the rotation was lost.
        order = []
        db = MagicMock()
        db.zoom_link.return_value = self._link()
        db.save_zoom_link.side_effect = lambda **kw: order.append("saved")
        with patch_modules({"src.modules.connect.db": db}), patch.object(zoom, "_token_request") as req:
            req.return_value = {"access_token": "a", "refresh_token": "r2", "expires_in": 3600}
            zoom.access_token_for("T1", "U1")
            order.append("returned")
        assert order == ["saved", "returned"]

    def test_a_dead_refresh_token_revokes_the_link(self, creds):
        db = MagicMock()
        db.zoom_link.return_value = self._link()
        with (
            patch_modules({"src.modules.connect.db": db}),
            patch.object(zoom, "_token_request", return_value=None),
        ):
            assert zoom.access_token_for("T1", "U1") is None
        db.revoke_zoom_link.assert_called_once_with("T1", "U1")

    def test_no_link_is_not_an_error(self, creds):
        db = MagicMock()
        db.zoom_link.return_value = None
        with patch_modules({"src.modules.connect.db": db}):
            assert zoom.access_token_for("T1", "U1") is None


class TestSignedLink:
    """The link is pressed from Slack, so it carries who it is for."""

    def _app(self):
        app = Flask(__name__)
        app.secret_key = "a-test-secret-that-is-long-enough-to-sign"
        return app

    def test_a_token_round_trips(self):
        with self._app().app_context():
            assert read_link_token(mint_link_token("T1", "U1")) == ("T1", "U1")

    def test_a_tampered_token_is_rejected(self):
        with self._app().app_context():
            token = mint_link_token("T1", "U1")
            assert read_link_token(token[:-3] + "xyz") is None

    def test_a_token_from_another_secret_is_rejected(self):
        with self._app().app_context():
            token = mint_link_token("T1", "U1")
        other = Flask(__name__)
        other.secret_key = "a-completely-different-signing-secret-x"
        with other.app_context():
            assert read_link_token(token) is None

    def test_an_expired_token_is_rejected(self):
        import time

        with self._app().app_context():
            token = mint_link_token("T1", "U1")
            with patch("time.time", return_value=time.time() + 4000):
                assert read_link_token(token) is None


class TestMeetingCreation:
    def test_a_scheduled_meeting_is_requested_not_an_instant_one(self, creds):
        with patch.object(zoom.requests, "post") as post:
            post.return_value = MagicMock(status_code=201, json=lambda: {"join_url": "https://z/1", "id": 9})
            out = zoom.create_meeting("tok", NOW, 30)
            body = post.call_args.kwargs["json"]
        assert out["join_url"] == "https://z/1"
        assert body["type"] == 2  # 2 is scheduled; 1 would be instant
        assert body["start_time"] == "2026-09-18T12:00:00Z"
        assert body["timezone"] == "UTC"
        assert body["duration"] == 30

    def test_neither_person_is_locked_out_waiting_for_a_host(self, creds):
        with patch.object(zoom.requests, "post") as post:
            post.return_value = MagicMock(status_code=201, json=lambda: {"join_url": "u", "id": 1})
            zoom.create_meeting("tok", NOW, 15)
            settings = post.call_args.kwargs["json"]["settings"]
        assert settings["join_before_host"] is True
        assert settings["waiting_room"] is False

    def test_a_naive_start_is_treated_as_utc(self, creds):
        with patch.object(zoom.requests, "post") as post:
            post.return_value = MagicMock(status_code=201, json=lambda: {"join_url": "u", "id": 1})
            zoom.create_meeting("tok", NOW.replace(tzinfo=None), 15)
            assert post.call_args.kwargs["json"]["start_time"] == "2026-09-18T12:00:00Z"

    def test_a_zoom_failure_returns_none_rather_than_raising(self, creds):
        with patch.object(zoom.requests, "post") as post:
            post.return_value = MagicMock(status_code=429, text="rate limited")
            assert zoom.create_meeting("tok", NOW, 15) is None

    def test_a_network_failure_returns_none_rather_than_raising(self, creds):
        with patch.object(zoom.requests, "post", side_effect=OSError("boom")):
            assert zoom.create_meeting("tok", NOW, 15) is None


class TestMeetingIsCreatedOnce:
    """A retry or a second delivery must not leave two meetings on an account."""

    def _match(self, join=None):
        return {"id": 5, "team_id": "T1", "round_id": 3, "member_ids": ["U1", "U2"], "zoom_join_url": join}

    def _run(self, db, creds_on=True):
        from src.modules.connect.handlers import _zoom_room

        with (
            patch_modules({"src.modules.connect.db": db}),
            patch.object(zoom, "configured", return_value=creds_on),
            patch.object(zoom, "access_token_for", return_value="tok"),
            patch.object(zoom, "create_meeting", return_value={"join_url": "https://z/new", "id": 42}),
        ):
            return _zoom_room(self._match(db.__dict__.get("_join")), ["U1", "U2"], NOW)

    def _db(self, linked=("U1",), claim=True, join=None):
        db = MagicMock()
        db._join = join
        db.zoom_linked_user_ids.return_value = list(linked)
        db.program_for_round.return_value = {"meeting_minutes": 20}
        db.set_match_meeting.return_value = claim
        db.match_by_id.return_value = {"zoom_join_url": "https://z/existing"}
        return db

    def test_a_meeting_is_created_and_claimed(self):
        db = self._db()
        assert self._run(db) == "https://z/new"
        db.set_match_meeting.assert_called_once()

    def test_an_existing_meeting_is_reused_not_recreated(self):
        db = self._db(join="https://z/already")
        with (
            patch.object(zoom, "create_meeting") as mk,
            patch.object(zoom, "configured", return_value=True),
            patch_modules({"src.modules.connect.db": db}),
        ):
            from src.modules.connect.handlers import _zoom_room

            out = _zoom_room(self._match("https://z/already"), ["U1", "U2"], NOW)
        assert out == "https://z/already"
        mk.assert_not_called()

    def test_losing_the_claim_race_returns_the_winners_url(self):
        # Two simultaneous final taps: whoever loses must hand back the URL the
        # winner stored, never its own orphan meeting.
        db = self._db(claim=False)
        assert self._run(db) == "https://z/existing"

    def test_nobody_linked_means_no_zoom_and_no_error(self):
        db = self._db(linked=())
        assert self._run(db) == ""

    def test_an_unconfigured_deployment_does_nothing(self):
        db = self._db()
        assert self._run(db, creds_on=False) == ""

    def test_a_dead_link_falls_through_to_the_other_person(self):
        from src.modules.connect.handlers import _zoom_room

        db = self._db(linked=("U1", "U2"))
        tokens = {"U1": None, "U2": "tok2"}
        with (
            patch_modules({"src.modules.connect.db": db}),
            patch.object(zoom, "configured", return_value=True),
            patch.object(zoom, "access_token_for", side_effect=lambda t, u: tokens[u]),
            patch.object(zoom, "create_meeting", return_value={"join_url": "https://z/u2", "id": 7}),
        ):
            assert _zoom_room(self._match(), ["U1", "U2"], NOW) == "https://z/u2"


class TestZoomOfferIsEphemeralAndTargeted:
    def test_only_the_unlinked_person_is_offered(self, creds):
        from src.modules.connect.jobs import _offer_zoom

        db = MagicMock()
        db.zoom_linked_user_ids.return_value = ["U1"]  # U1 already linked
        client = MagicMock()
        app = Flask(__name__)
        app.secret_key = "a-test-secret-that-is-long-enough-to-sign"
        with (
            app.app_context(),
            patch_modules({"src.modules.connect.db": db}),
            patch.object(zoom, "configured", return_value=True),
        ):
            _offer_zoom(client, "D1", "T1", ["U1", "U2"])
        users = [c.kwargs["user"] for c in client.chat_postEphemeral.call_args_list]
        assert users == ["U2"]

    def test_it_is_ephemeral_never_posted_to_the_dm(self, creds):
        from src.modules.connect.jobs import _offer_zoom

        db = MagicMock()
        db.zoom_linked_user_ids.return_value = []
        client = MagicMock()
        app = Flask(__name__)
        app.secret_key = "a-test-secret-that-is-long-enough-to-sign"
        with (
            app.app_context(),
            patch_modules({"src.modules.connect.db": db}),
            patch.object(zoom, "configured", return_value=True),
        ):
            _offer_zoom(client, "D1", "T1", ["U1"])
        assert client.chat_postEphemeral.called
        assert not client.chat_postMessage.called

    def test_an_unconfigured_deployment_offers_nothing(self, monkeypatch):
        from src.modules.connect.jobs import _offer_zoom

        monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
        client = MagicMock()
        _offer_zoom(client, "D1", "T1", ["U1"])
        assert not client.chat_postEphemeral.called
