"""Tests for webhook signing secrets, event naming and the delivery log.

This module deliberately sorts last so the modules it imports (db, dashboard,
handlers) cannot leak stubs into any other test file. It also has to pass on
its own, so every stub it needs is set up here rather than inherited.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Earlier modules leave MagicMocks behind under these names. schedule_validation
# needs the real pytz to tell a valid timezone from a typo, and importing the
# real db/dashboard/handlers needs real packages underneath them.
for _name in ("pytz", "psycopg2", "psycopg2.extras", "psycopg2.pool", "requests"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

# Another module may have parked a MagicMock under "db" or "handlers".
for _name in ("db", "dashboard", "handlers", "state"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

import dashboard  # noqa: E402
import db  # noqa: E402
import handlers  # noqa: E402
from flask import Flask  # noqa: E402

CANONICAL = ("standup.completed", "blocker.detected", "participation.low")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _fake_db_conn(fetchone=None, fetchall=None):
    """Return (patch target value, conn, cursor) emulating db.db_conn()."""
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    cur.rowcount = 1

    conn = MagicMock()
    conn.cursor.return_value = cur

    ctx = MagicMock()
    ctx.__enter__ = lambda s: conn
    ctx.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=ctx), conn, cur


def _stored_row(hook_id=7, team_id="T123", url="https://hooks.example.com/standup", secret=None, events=None):
    return {
        "id": hook_id,
        "team_id": team_id,
        "webhook_url": url,
        "secret": secret,
        "events": list(events or ["standup.completed"]),
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def _dashboard_db_mock():
    """A db double for dashboard that emulates storage for add_webhook/rotate.

    Constants and pure helpers come from the real db module so this double
    cannot drift away from it.
    """
    m = MagicMock()
    m.WEBHOOK_EVENTS = db.WEBHOOK_EVENTS
    m.DEFAULT_WEBHOOK_EVENTS = db.DEFAULT_WEBHOOK_EVENTS
    m.normalize_webhook_event = db.normalize_webhook_event
    m.normalize_webhook_events = db.normalize_webhook_events

    def _add(team_id, url, secret=None, events=None):
        return _stored_row(team_id=team_id, url=url, secret=secret, events=db.normalize_webhook_events(events))

    def _rotate(team_id, webhook_id, secret):
        return _stored_row(hook_id=webhook_id, team_id=team_id, secret=secret)

    m.add_webhook.side_effect = _add
    m.rotate_webhook_secret.side_effect = _rotate
    return m


@pytest.fixture()
def app():
    flask_app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "../src/templates"))
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.register_blueprint(dashboard.dashboard_bp)
    return flask_app


@pytest.fixture()
def db_mock():
    m = _dashboard_db_mock()
    with patch.object(dashboard, "db", m):
        yield m


@pytest.fixture()
def authed_client(app, db_mock):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["team_id"] = "T123"
        sess["user_id"] = "U456"
    return client


# ---------------------------------------------------------------------------
# Event naming convention
# ---------------------------------------------------------------------------


class TestEventNaming:
    def test_canonical_set_is_dotted(self):
        assert db.WEBHOOK_EVENTS == CANONICAL

    def test_underscore_spellings_are_normalised(self):
        got = db.normalize_webhook_events(["standup_complete", "blocker_detected", "low_participation"])
        assert got == list(CANONICAL)

    def test_unknown_events_are_dropped(self):
        assert db.normalize_webhook_events(["nope.at.all", "standup.completed"]) == ["standup.completed"]

    def test_duplicates_collapse(self):
        assert db.normalize_webhook_events(["standup_complete", "standup.completed"]) == ["standup.completed"]

    def test_empty_falls_back_to_default(self):
        assert db.normalize_webhook_events([]) == db.DEFAULT_WEBHOOK_EVENTS
        assert db.normalize_webhook_events(None) == db.DEFAULT_WEBHOOK_EVENTS

    def test_handlers_alias_table_matches_db(self):
        # handlers keeps a local copy so subscription matching never needs db.
        assert handlers._WEBHOOK_EVENT_ALIASES == db.WEBHOOK_EVENT_ALIASES


# ---------------------------------------------------------------------------
# db helpers
# ---------------------------------------------------------------------------


class TestDbWebhookHelpers:
    def test_add_webhook_persists_secret_and_events(self):
        conn_ctx, _conn, cur = _fake_db_conn(fetchone=_stored_row(secret="s3cr3t"))
        with patch.object(db, "db_conn", conn_ctx):
            db.add_webhook("T1", "https://x.example.com/h", secret="s3cr3t", events=["standup_complete"])
        params = cur.execute.call_args.args[1]
        assert params[2] == "s3cr3t"
        assert params[3] == ["standup.completed"]

    def test_rotate_stores_new_secret_scoped_to_team(self):
        conn_ctx, _conn, cur = _fake_db_conn(fetchone=_stored_row(secret="new"))
        with patch.object(db, "db_conn", conn_ctx):
            row = db.rotate_webhook_secret("T1", 7, "new")
        sql, params = cur.execute.call_args.args
        assert "team_id = %s" in sql
        assert params == ("new", 7, "T1")
        assert row["secret"] == "new"

    def test_rotate_missing_webhook_returns_none(self):
        conn_ctx, _conn, _cur = _fake_db_conn(fetchone=None)
        with patch.object(db, "db_conn", conn_ctx):
            assert db.rotate_webhook_secret("T1", 999, "new") is None

    def test_rotate_does_not_log_the_secret(self, caplog):
        conn_ctx, _conn, _cur = _fake_db_conn(fetchone=_stored_row(secret="topsecretvalue"))
        with caplog.at_level("DEBUG"), patch.object(db, "db_conn", conn_ctx):
            db.rotate_webhook_secret("T1", 7, "topsecretvalue")
        assert "topsecretvalue" not in caplog.text

    def test_update_webhook_sets_only_supplied_fields(self):
        conn_ctx, _conn, cur = _fake_db_conn(fetchone=_stored_row())
        with patch.object(db, "db_conn", conn_ctx):
            db.update_webhook("T1", 7, events=["blocker_detected"])
        sql, params = cur.execute.call_args.args
        assert "events = %s" in sql
        assert "webhook_url" not in sql
        assert params == (["blocker.detected"], 7, "T1")

    def test_update_webhook_with_nothing_reads_back_current_row(self):
        conn_ctx, _conn, cur = _fake_db_conn(fetchone=_stored_row())
        with patch.object(db, "db_conn", conn_ctx):
            db.update_webhook("T1", 7)
        assert cur.execute.call_args.args[0].strip().startswith("SELECT")

    def test_record_delivery_inserts_then_prunes(self):
        conn_ctx, _conn, cur = _fake_db_conn()
        with patch.object(db, "db_conn", conn_ctx):
            db.record_webhook_delivery(
                team_id="T1",
                webhook_id=7,
                event_type="standup.completed",
                status_code=200,
                ok=True,
                signed=True,
                duration_ms=42,
            )
        assert cur.execute.call_count == 2
        insert_sql, insert_params = cur.execute.call_args_list[0].args
        assert "INSERT INTO webhook_deliveries" in insert_sql
        assert insert_params == (7, "T1", "standup.completed", 200, True, True, None, 42)

        prune_sql, prune_params = cur.execute.call_args_list[1].args
        assert "DELETE FROM webhook_deliveries" in prune_sql
        assert prune_params == (7, 7, db.WEBHOOK_DELIVERY_RETENTION)

    def test_record_delivery_truncates_long_errors(self):
        conn_ctx, _conn, cur = _fake_db_conn()
        with patch.object(db, "db_conn", conn_ctx):
            db.record_webhook_delivery("T1", 7, "standup.completed", error="x" * 5000)
        assert len(cur.execute.call_args_list[0].args[1][6]) == 500

    def test_get_deliveries_scopes_to_one_webhook(self):
        conn_ctx, _conn, cur = _fake_db_conn(fetchall=[{"id": 1}])
        with patch.object(db, "db_conn", conn_ctx):
            db.get_webhook_deliveries("T1", webhook_id=7, limit=5)
        sql, params = cur.execute.call_args.args
        assert "webhook_id = %s" in sql
        assert params == ("T1", 7, 5)

    def test_get_deliveries_caps_the_limit(self):
        conn_ctx, _conn, cur = _fake_db_conn()
        with patch.object(db, "db_conn", conn_ctx):
            db.get_webhook_deliveries("T1", limit=100000)
        assert cur.execute.call_args.args[1] == ("T1", 200)


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


class TestSigning:
    def _fire(self, hook, event="standup.completed", payload=None, db_double=None):
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)
        with patch.dict(sys.modules, {"db": db_double or MagicMock()}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.deliver_webhook(hook, event, payload or {"user": "U1"}, team_id="T123")
        return requests_mock

    def test_signature_verifies_with_compare_digest_over_the_raw_body(self):
        secret = "0FgqHrLd0OLZuqQ8vGZk0Q7v2QFRhL5nSVJZaN5nPTA"
        requests_mock = self._fire(_stored_row(secret=secret))

        kwargs = requests_mock.post.call_args.kwargs
        sent_body = kwargs["data"]
        assert isinstance(sent_body, bytes)

        # Exactly what a receiver does: HMAC the raw bytes off the wire and
        # compare in constant time.
        expected = "sha256=" + hmac.new(secret.encode(), sent_body, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, kwargs["headers"]["X-Morgenruf-Signature"])

    def test_signature_is_over_the_bytes_sent_not_a_reserialised_copy(self):
        secret = "another-secret-value-for-the-test"
        requests_mock = self._fire(_stored_row(secret=secret), payload={"b": 1, "a": 2})

        kwargs = requests_mock.post.call_args.kwargs
        sent_body = kwargs["data"]
        sig = kwargs["headers"]["X-Morgenruf-Signature"]

        # Re-serialising with different key order changes the bytes, so the
        # digest must not match. This is what catches a receiver that hashes
        # json.dumps(request.json) instead of the raw body.
        reserialised = json.dumps({"a": 2, "b": 1}).encode()
        assert reserialised != sent_body
        wrong = "sha256=" + hmac.new(secret.encode(), reserialised, hashlib.sha256).hexdigest()
        assert not hmac.compare_digest(wrong, sig)

    def test_null_secret_delivers_unsigned(self):
        requests_mock = self._fire(_stored_row(secret=None))
        headers = requests_mock.post.call_args.kwargs["headers"]
        assert "X-Morgenruf-Signature" not in headers
        assert headers["X-Morgenruf-Event"] == "standup.completed"

    def test_secret_is_never_logged(self, caplog):
        secret = "do-not-log-this-value"
        with caplog.at_level("DEBUG"):
            self._fire(_stored_row(secret=secret))
        assert secret not in caplog.text

    def test_underscore_subscription_matches_dotted_event(self):
        """A row written before the naming was settled still receives events."""
        db_double = MagicMock()
        db_double.get_webhooks.return_value = [_stored_row(secret="s", events=["standup_complete"])]
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)
        with patch.dict(sys.modules, {"db": db_double}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.fire_webhooks("T123", "standup.completed", {"user": "U1"})
        requests_mock.post.assert_called_once()


# ---------------------------------------------------------------------------
# Delivery log
# ---------------------------------------------------------------------------


class TestDeliveryLog:
    def test_success_is_recorded(self):
        db_double = MagicMock()
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=202)
        with patch.dict(sys.modules, {"db": db_double}):
            with patch.object(handlers, "requests", requests_mock):
                result = handlers.deliver_webhook(_stored_row(secret="s"), "standup.completed", {}, team_id="T123")

        kwargs = db_double.record_webhook_delivery.call_args.kwargs
        assert kwargs["webhook_id"] == 7
        assert kwargs["team_id"] == "T123"
        assert kwargs["status_code"] == 202
        assert kwargs["ok"] is True
        assert kwargs["signed"] is True
        assert kwargs["error"] is None
        assert isinstance(kwargs["duration_ms"], int)
        assert result["ok"] is True

    def test_non_2xx_is_recorded_as_a_failure(self):
        db_double = MagicMock()
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=500)
        with patch.dict(sys.modules, {"db": db_double}):
            with patch.object(handlers, "requests", requests_mock):
                result = handlers.deliver_webhook(_stored_row(), "standup.completed", {}, team_id="T123")

        kwargs = db_double.record_webhook_delivery.call_args.kwargs
        assert kwargs["status_code"] == 500
        assert kwargs["ok"] is False
        assert kwargs["error"] == "HTTP 500"
        assert result["signed"] is False

    def test_connection_failure_records_null_status_and_a_reason(self):
        db_double = MagicMock()
        requests_mock = MagicMock()
        requests_mock.post.side_effect = OSError("Connection refused")
        with patch.dict(sys.modules, {"db": db_double}):
            with patch.object(handlers, "requests", requests_mock):
                result = handlers.deliver_webhook(_stored_row(), "standup.completed", {}, team_id="T123")

        kwargs = db_double.record_webhook_delivery.call_args.kwargs
        assert kwargs["status_code"] is None
        assert kwargs["ok"] is False
        assert "Connection refused" in kwargs["error"]
        assert result["status_code"] is None

    def test_a_broken_log_never_breaks_delivery(self):
        db_double = MagicMock()
        db_double.record_webhook_delivery.side_effect = RuntimeError("log table gone")
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)
        with patch.dict(sys.modules, {"db": db_double}):
            with patch.object(handlers, "requests", requests_mock):
                result = handlers.deliver_webhook(_stored_row(), "standup.completed", {}, team_id="T123")
        requests_mock.post.assert_called_once()
        assert result["ok"] is True

    def test_hook_without_an_id_is_not_logged(self):
        db_double = MagicMock()
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)
        hook = {"webhook_url": "https://hooks.example.com/x", "events": ["standup.completed"], "secret": None}
        with patch.dict(sys.modules, {"db": db_double}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.deliver_webhook(hook, "standup.completed", {}, team_id="T123")
        db_double.record_webhook_delivery.assert_not_called()


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------


class TestCreateWebhook:
    def test_create_generates_a_secret_and_returns_it_once(self, authed_client, db_mock):
        resp = authed_client.post("/dashboard/api/webhooks", json={"url": "https://hooks.example.com/standup"})
        assert resp.status_code == 201
        body = resp.get_json()

        stored = db_mock.add_webhook.call_args.kwargs["secret"]
        assert isinstance(stored, str) and len(stored) >= 32
        assert body["secret"] == stored
        assert body["secret_shown_once"] is True
        assert body["has_secret"] is True

    def test_two_webhooks_get_different_secrets(self, authed_client):
        a = authed_client.post("/dashboard/api/webhooks", json={"url": "https://a.example.com/h"}).get_json()
        b = authed_client.post("/dashboard/api/webhooks", json={"url": "https://b.example.com/h"}).get_json()
        assert a["secret"] != b["secret"]

    def test_create_accepts_and_normalises_events(self, authed_client, db_mock):
        resp = authed_client.post(
            "/dashboard/api/webhooks",
            json={"url": "https://hooks.example.com/h", "events": ["blocker_detected"]},
        )
        assert resp.status_code == 201
        assert db_mock.add_webhook.call_args.kwargs["events"] == ["blocker.detected"]
        assert resp.get_json()["events"] == ["blocker.detected"]

    def test_create_rejects_an_unknown_event(self, authed_client):
        resp = authed_client.post(
            "/dashboard/api/webhooks",
            json={"url": "https://hooks.example.com/h", "events": ["standup.exploded"]},
        )
        assert resp.status_code == 400
        assert "Unknown event" in resp.get_json()["error"]

    def test_create_still_rejects_an_unsafe_url(self, authed_client, db_mock):
        resp = authed_client.post("/dashboard/api/webhooks", json={"url": "http://127.0.0.1/hook"})
        assert resp.status_code == 400
        db_mock.add_webhook.assert_not_called()


class TestListWebhooks:
    def test_list_never_returns_the_raw_secret(self, authed_client, db_mock):
        db_mock.get_webhooks.return_value = [_stored_row(secret="super-secret-value")]
        resp = authed_client.get("/dashboard/api/webhooks")
        assert resp.status_code == 200
        assert "super-secret-value" not in resp.get_data(as_text=True)
        row = resp.get_json()[0]
        assert row["has_secret"] is True
        assert row["secret_prefix"] == "super-"
        assert "secret" not in row

    def test_a_null_secret_row_is_reported_as_unsigned(self, authed_client, db_mock):
        db_mock.get_webhooks.return_value = [_stored_row(secret=None)]
        row = authed_client.get("/dashboard/api/webhooks").get_json()[0]
        assert row["has_secret"] is False
        assert row["signed"] is False
        assert row["secret_prefix"] is None

    def test_events_endpoint_lists_the_canonical_names(self, authed_client):
        body = authed_client.get("/dashboard/api/webhooks/events").get_json()
        assert body["events"] == list(CANONICAL)
        assert body["default"] == ["standup.completed"]


class TestRotateSecret:
    def test_rotate_returns_a_new_secret_once(self, authed_client, db_mock):
        resp = authed_client.post("/dashboard/api/webhooks/7/rotate")
        assert resp.status_code == 200
        body = resp.get_json()
        passed = db_mock.rotate_webhook_secret.call_args.args[2]
        assert body["secret"] == passed
        assert body["secret_shown_once"] is True

    def test_rotate_is_scoped_to_the_session_team(self, authed_client, db_mock):
        authed_client.post("/dashboard/api/webhooks/7/rotate")
        assert db_mock.rotate_webhook_secret.call_args.args[0] == "T123"

    def test_rotate_unknown_webhook_is_404(self, authed_client, db_mock):
        db_mock.rotate_webhook_secret.side_effect = None
        db_mock.rotate_webhook_secret.return_value = None
        assert authed_client.post("/dashboard/api/webhooks/999/rotate").status_code == 404

    def test_rotate_requires_login(self, app, db_mock):
        assert app.test_client().post("/dashboard/api/webhooks/7/rotate").status_code == 401


class TestUpdateWebhook:
    def test_update_events(self, authed_client, db_mock):
        db_mock.update_webhook.return_value = _stored_row(events=["blocker.detected"])
        resp = authed_client.patch("/dashboard/api/webhooks/7", json={"events": ["blocker_detected"]})
        assert resp.status_code == 200
        assert db_mock.update_webhook.call_args.kwargs["events"] == ["blocker.detected"]

    def test_update_url_is_safety_checked(self, authed_client, db_mock):
        resp = authed_client.patch("/dashboard/api/webhooks/7", json={"url": "http://192.168.0.5/hook"})
        assert resp.status_code == 400
        db_mock.update_webhook.assert_not_called()

    def test_update_with_no_fields_is_rejected(self, authed_client):
        assert authed_client.patch("/dashboard/api/webhooks/7", json={}).status_code == 400

    def test_update_cannot_set_a_secret(self, authed_client, db_mock):
        db_mock.update_webhook.return_value = _stored_row(secret="unchanged")
        authed_client.patch("/dashboard/api/webhooks/7", json={"url": "https://new.example.com/h"})
        assert "secret" not in db_mock.update_webhook.call_args.kwargs

    def test_update_unknown_webhook_is_404(self, authed_client, db_mock):
        db_mock.update_webhook.return_value = None
        resp = authed_client.patch("/dashboard/api/webhooks/7", json={"url": "https://new.example.com/h"})
        assert resp.status_code == 404


class TestTestSend:
    def test_test_send_signs_with_the_stored_secret(self, authed_client, db_mock):
        secret = "stored-signing-secret-for-test-send"
        db_mock.get_webhook.return_value = _stored_row(secret=secret)
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=204)

        with patch.dict(sys.modules, {"db": MagicMock()}):
            with patch.object(handlers, "requests", requests_mock):
                resp = authed_client.post("/dashboard/api/webhooks/7/test")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["status_code"] == 204
        assert body["signed"] is True

        kwargs = requests_mock.post.call_args.kwargs
        expected = "sha256=" + hmac.new(secret.encode(), kwargs["data"], hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, kwargs["headers"]["X-Morgenruf-Signature"])
        assert json.loads(kwargs["data"])["test"] is True

    def test_test_send_reports_a_failure_without_raising(self, authed_client, db_mock):
        db_mock.get_webhook.return_value = _stored_row(secret="s")
        requests_mock = MagicMock()
        requests_mock.post.side_effect = OSError("nope")

        with patch.dict(sys.modules, {"db": MagicMock()}):
            with patch.object(handlers, "requests", requests_mock):
                resp = authed_client.post("/dashboard/api/webhooks/7/test")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is False
        assert body["status_code"] is None
        assert "nope" in body["error"]

    def test_test_send_unknown_webhook_is_404(self, authed_client, db_mock):
        db_mock.get_webhook.return_value = None
        assert authed_client.post("/dashboard/api/webhooks/7/test").status_code == 404

    def test_test_send_requires_login(self, app, db_mock):
        assert app.test_client().post("/dashboard/api/webhooks/7/test").status_code == 401


class TestDeliveriesEndpoint:
    def test_returns_rows_with_serialised_timestamps(self, authed_client, db_mock):
        db_mock.get_webhook_deliveries.return_value = [
            {
                "id": 1,
                "webhook_id": 7,
                "event_type": "standup.completed",
                "status_code": 200,
                "ok": True,
                "signed": True,
                "error": None,
                "duration_ms": 12,
                "created_at": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            }
        ]
        resp = authed_client.get("/dashboard/api/webhooks/deliveries")
        assert resp.status_code == 200
        assert resp.get_json()[0]["created_at"].startswith("2026-01-02T03:04")

    def test_per_webhook_route_scopes_the_query(self, authed_client, db_mock):
        db_mock.get_webhook_deliveries.return_value = []
        authed_client.get("/dashboard/api/webhooks/7/deliveries?limit=5")
        kwargs = db_mock.get_webhook_deliveries.call_args.kwargs
        assert kwargs["webhook_id"] == 7
        assert kwargs["limit"] == 5

    def test_requires_login(self, app, db_mock):
        assert app.test_client().get("/dashboard/api/webhooks/deliveries").status_code == 401


# ---------------------------------------------------------------------------
# The bug in #73, end to end
# ---------------------------------------------------------------------------


class TestCreatedWebhookDeliversSigned:
    def test_a_webhook_created_through_the_api_delivers_a_verifiable_signature(self, authed_client, db_mock):
        """The whole point of #73: create then deliver, and the delivery is signed.

        Before the fix api_add_webhook called db.add_webhook without a secret,
        so the stored row had secret NULL and every delivery went out bare.
        """
        resp = authed_client.post("/dashboard/api/webhooks", json={"url": "https://hooks.example.com/standup"})
        assert resp.status_code == 201
        shown_secret = resp.get_json()["secret"]

        # The row as the database now holds it.
        stored = db_mock.add_webhook.side_effect(
            "T123",
            "https://hooks.example.com/standup",
            secret=db_mock.add_webhook.call_args.kwargs["secret"],
            events=None,
        )
        assert stored["secret"] is not None, "webhook was stored without a signing secret"

        db_double = MagicMock()
        db_double.get_webhooks.return_value = [stored]
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)
        with patch.dict(sys.modules, {"db": db_double}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.fire_webhooks("T123", "standup.completed", {"user": "U1"})

        kwargs = requests_mock.post.call_args.kwargs
        sig = kwargs["headers"].get("X-Morgenruf-Signature")
        assert sig is not None, "delivery went out unsigned"

        # A receiver holding only the secret it was shown at creation can verify.
        expected = "sha256=" + hmac.new(shown_secret.encode(), kwargs["data"], hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, sig)
