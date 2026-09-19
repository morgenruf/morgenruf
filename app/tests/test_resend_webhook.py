"""Bounces and complaints, arriving from Resend.

Two things are being protected here. One is that nobody but Resend can post to
this endpoint, because an open webhook is a way to make the app send Slack
messages on a stranger's behalf. The other is that a bounce actually stops the
next send: Resend suppressing an address upstream does nothing for the check
our own send path performs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from src.core import inbound_hooks

SECRET_BYTES = b"0123456789abcdef0123456789abcdef"
SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode()


def sign(body: bytes, msg_id: str = "msg_1", timestamp: str | None = None) -> dict:
    timestamp = timestamp or str(int(time.time()))
    signed = f"{msg_id}.{timestamp}.".encode() + body
    digest = base64.b64encode(hmac.new(SECRET_BYTES, signed, hashlib.sha256).digest()).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{digest}",
    }


def bounce(address: str = "jane@acme.com") -> bytes:
    return json.dumps(
        {
            "type": "email.bounced",
            "data": {
                "to": [address],
                "subject": "Morgenruf is installed",
                "bounce": {"subType": "MailboxDoesNotExist", "message": "mailbox does not exist"},
            },
        }
    ).encode()


def complaint(address: str = "dave@foo.com") -> bytes:
    return json.dumps({"type": "email.complained", "data": {"to": [address], "subject": "One week in"}}).encode()


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)


class TestOnlyResendGetsIn:
    def test_a_correct_signature_verifies(self):
        body = bounce()
        h = sign(body)
        assert inbound_hooks.verify(body, h["svix-id"], h["svix-timestamp"], h["svix-signature"])

    def test_a_tampered_body_does_not_verify(self):
        h = sign(bounce())
        assert not inbound_hooks.verify(
            bounce("someone-else@evil.com"), h["svix-id"], h["svix-timestamp"], h["svix-signature"]
        )

    def test_a_forged_signature_does_not_verify(self):
        body = bounce()
        h = sign(body)
        assert not inbound_hooks.verify(body, h["svix-id"], h["svix-timestamp"], "v1,notarealsignature")

    def test_an_old_delivery_is_a_replay(self):
        body = bounce()
        old = str(int(time.time()) - inbound_hooks.TOLERANCE - 60)
        h = sign(body, timestamp=old)
        assert not inbound_hooks.verify(body, h["svix-id"], h["svix-timestamp"], h["svix-signature"])

    def test_no_configured_secret_verifies_nothing(self, monkeypatch):
        monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
        body = bounce()
        h = sign(body)
        assert not inbound_hooks.verify(body, h["svix-id"], h["svix-timestamp"], h["svix-signature"])

    def test_missing_headers_verify_nothing(self):
        assert not inbound_hooks.verify(bounce(), "", "", "")

    def test_a_rotated_secret_leaves_both_signatures_valid(self):
        """Svix sends several signatures during a rotation; one match is enough."""
        body = bounce()
        h = sign(body)
        header = f"v1,anoldsignature {h['svix-signature']}"
        assert inbound_hooks.verify(body, h["svix-id"], h["svix-timestamp"], header)


class TestTheAlertItSends:
    def test_a_bounce_names_the_address_and_the_reason(self):
        with patch("src.core.alerts.notify", return_value=True) as notify:
            assert inbound_hooks.handle(json.loads(bounce())) is True
        text = notify.call_args[0][0]
        assert "jane@acme.com" in text
        assert "bounced" in text
        assert "mailbox does not exist" in text

    def test_a_complaint_says_who_and_that_they_are_suppressed(self):
        with patch("src.core.alerts.notify", return_value=True) as notify:
            inbound_hooks.handle(json.loads(complaint()))
        text = notify.call_args[0][0]
        assert "dave@foo.com" in text
        assert "spam" in text
        assert "suppressed" in text

    def test_opens_are_ignored_on_purpose(self):
        payload = {"type": "email.opened", "data": {"to": ["jane@acme.com"]}}
        with patch("src.core.alerts.notify") as notify:
            assert inbound_hooks.handle(payload) is False
        notify.assert_not_called()

    def test_deliveries_are_not_worth_a_message(self):
        payload = {"type": "email.delivered", "data": {"to": ["jane@acme.com"]}}
        with patch("src.core.alerts.notify") as notify:
            assert inbound_hooks.handle(payload) is False
        notify.assert_not_called()


class TestABounceStopsTheNextSend:
    def test_a_bounce_suppresses_the_address(self):
        with patch("src.core.db.suppress_email") as suppress:
            inbound_hooks.suppress_after(json.loads(bounce()))
        suppress.assert_called_once_with("jane@acme.com", reason="bounced")

    def test_a_complaint_suppresses_the_address(self):
        with patch("src.core.db.suppress_email") as suppress:
            inbound_hooks.suppress_after(json.loads(complaint()))
        suppress.assert_called_once_with("dave@foo.com", reason="complained")

    def test_an_open_suppresses_nobody(self):
        payload = {"type": "email.opened", "data": {"to": ["jane@acme.com"]}}
        with patch("src.core.db.suppress_email") as suppress:
            inbound_hooks.suppress_after(payload)
        suppress.assert_not_called()

    def test_a_broken_database_does_not_raise(self):
        with patch("src.core.db.suppress_email", side_effect=RuntimeError("no db")):
            inbound_hooks.suppress_after(json.loads(bounce()))


class TestMalformedInput:
    def test_a_body_that_is_not_json_parses_to_none(self):
        assert inbound_hooks.parse(b"not json at all") is None

    def test_a_json_list_is_not_a_payload(self):
        assert inbound_hooks.parse(b"[1, 2, 3]") is None

    def test_a_payload_with_no_recipient_does_not_crash(self):
        payload = {"type": "email.bounced", "data": {}}
        with patch("src.core.alerts.notify", return_value=True) as notify:
            inbound_hooks.handle(payload)
        assert "an address" in notify.call_args[0][0]
