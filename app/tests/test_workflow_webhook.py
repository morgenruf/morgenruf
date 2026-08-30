"""Tests for the workflow fire_webhook action (#81).

The rule action used to POST straight to `action_target` with no URL check and
no signature. These cover both halves of that fix.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

for _name in ("pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

import workflow  # noqa: E402
from url_guard import is_safe_webhook_url  # noqa: E402


def _rule(target, rule_id=7):
    return {
        "id": rule_id,
        "team_id": "T1",
        "name": "Alert",
        "trigger": "standup_complete",
        "action": "fire_webhook",
        "action_target": target,
        "action_message": None,
    }


def _run(rule, webhooks=None, deliver=None):
    """Fire one rule and return the deliver_webhook mock."""
    deliver = deliver or MagicMock(return_value={"signed": True, "status_code": 200, "ok": True})
    db = MagicMock()
    db.get_webhooks.return_value = webhooks if webhooks is not None else []
    handlers = MagicMock()
    handlers.deliver_webhook = deliver
    with patch.dict(sys.modules, {"db": db, "handlers": handlers}):
        workflow._fire_rule("T1", rule, "standup_complete", {"team": "T1"}, MagicMock())
    return deliver


class TestUrlGuard:
    """The SSRF half. These are the targets that must never be reached."""

    def test_metadata_endpoint_is_refused(self):
        assert is_safe_webhook_url("http://169.254.169.254/latest/meta-data/") is False

    def test_loopback_is_refused(self):
        for url in ("http://localhost:5432", "http://127.0.0.1", "http://[::1]/x"):
            assert is_safe_webhook_url(url) is False, url

    def test_private_ranges_are_refused(self):
        for url in ("http://10.0.0.5", "http://192.168.1.1", "http://172.16.0.1"):
            assert is_safe_webhook_url(url) is False, url

    def test_non_http_schemes_are_refused(self):
        for url in ("file:///etc/passwd", "ftp://example.com", "gopher://x"):
            assert is_safe_webhook_url(url) is False, url

    def test_ordinary_https_is_allowed(self):
        assert is_safe_webhook_url("https://hooks.example.com/abc") is True


class TestRuleWebhookRefusesUnsafeTargets:
    def test_metadata_endpoint_is_not_delivered(self):
        deliver = _run(_rule("http://169.254.169.254/latest/meta-data/"))
        deliver.assert_not_called()

    def test_internal_port_is_not_delivered(self):
        deliver = _run(_rule("http://127.0.0.1:5432/"))
        deliver.assert_not_called()

    def test_empty_target_is_not_delivered(self):
        deliver = _run(_rule(""))
        deliver.assert_not_called()


class TestRuleWebhookSigns:
    def test_matching_registered_webhook_supplies_the_secret(self):
        registered = {"id": 3, "webhook_url": "https://hooks.example.com/abc", "secret": "sh"}
        deliver = _run(_rule("https://hooks.example.com/abc"), webhooks=[registered])
        deliver.assert_called_once()
        hook = deliver.call_args.args[0]
        assert hook["secret"] == "sh"
        assert hook["id"] == 3

    def test_unregistered_target_still_delivers_but_unsigned(self):
        deliver = _run(_rule("https://elsewhere.example.com/x"), webhooks=[])
        deliver.assert_called_once()
        hook = deliver.call_args.args[0]
        assert hook["secret"] is None

    def test_event_name_identifies_the_trigger(self):
        deliver = _run(_rule("https://hooks.example.com/abc"))
        assert deliver.call_args.args[1] == "rule.standup_complete"

    def test_lookup_failure_still_delivers(self):
        """A DB hiccup should cost the signature, not the delivery."""
        deliver = MagicMock(return_value={"signed": False, "status_code": 200})
        db = MagicMock()
        db.get_webhooks.side_effect = Exception("db down")
        handlers = MagicMock()
        handlers.deliver_webhook = deliver
        with patch.dict(sys.modules, {"db": db, "handlers": handlers}):
            workflow._fire_rule("T1", _rule("https://hooks.example.com/abc"), "standup_complete", {}, MagicMock())
        deliver.assert_called_once()


class TestLowParticipationCountsEnrolledOnly:
    """#82: the trigger divided by every member, so it fired every day.

    These exercise the shipped `scheduler.participation_pct`, not a copy of the
    expression, so the test cannot pass while the real code is wrong.
    """

    @staticmethod
    def _pct(stats):
        import scheduler  # noqa: PLC0415

        return scheduler.participation_pct(stats)

    def test_unenrolled_members_no_longer_drag_the_number_down(self):
        # 6 enrolled, 4 of them responded. 12 more are in no standup at all.
        stats = [{"user_id": f"E{i}", "enrolled": True, "responses": 1 if i < 4 else 0} for i in range(6)]
        stats += [{"user_id": f"U{i}", "enrolled": False, "responses": 0} for i in range(12)]
        assert self._pct(stats) == 66
        # The old formula divided by all 18 and reported 22, which would trip
        # any sane threshold every single day.
        assert int(4 / len(stats) * 100) == 22

    def test_rows_without_the_flag_are_treated_as_enrolled(self):
        stats = [{"user_id": "A", "responses": 1}, {"user_id": "B", "responses": 0}]
        assert self._pct(stats) == 50

    def test_no_enrolled_members_does_not_divide_by_zero(self):
        assert self._pct([{"user_id": "U", "enrolled": False, "responses": 0}]) == 100
        assert self._pct([]) == 100
        assert self._pct(None) == 100

    def test_everyone_responded(self):
        assert self._pct([{"enrolled": True, "responses": 2}, {"enrolled": True, "responses": 1}]) == 100
