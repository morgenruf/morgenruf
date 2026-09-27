"""A standup whose token check fails must not be retried forever.

A workspace with a revoked token was re-queued every 60 seconds for as long as
the pod stayed up (537 times in three hours). Permanent Slack auth errors now
stop at once, and anything else gets three spaced retries.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

from tests.support import patch_modules

for _name in ("pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

_had_scheduler = "scheduler" in sys.modules
import src.core.scheduler as sched_mod  # noqa: E402

if _had_scheduler:
    sched_mod = importlib.reload(sched_mod)


class _SlackError(Exception):
    def __init__(self, code):
        super().__init__(f"The request to the Slack API failed. The server responded with: {{'error': '{code}'}}")
        self.response = {"ok": False, "error": code}


def _db():
    db = MagicMock()
    db.get_standup_schedule.return_value = {
        "id": 32,
        "active": True,
        "channel_id": "C1",
        "questions": [],
        "participants": [],
        "name": "Daily",
    }
    db.get_active_members.return_value = [{"user_id": "U1"}]
    return db


def _run(error, attempt=0):
    retry = MagicMock()
    with (
        patch_modules({"src.core.db": _db()}),
        patch.object(sched_mod, "_fresh_bot_token", side_effect=lambda team, token: token),
        patch.object(sched_mod, "_call_with_auth_retry", side_effect=error),
        patch.object(sched_mod, "_schedule_standup_retry", retry),
    ):
        sched_mod._send_standup_to_workspace("T1", "xoxb-test", "C1", 32, retry_attempt=attempt)
    return retry


class TestPermanentErrorsStop:
    def test_revoked_token_is_not_retried(self):
        assert not _run(_SlackError("token_revoked")).called

    def test_inactive_workspace_is_not_retried(self):
        assert not _run(_SlackError("account_inactive")).called

    def test_invalid_auth_is_not_retried(self):
        assert not _run(_SlackError("invalid_auth")).called


class TestTransientErrorsRetryWithACap:
    def test_first_failure_retries_after_a_minute(self):
        retry = _run(ConnectionError("network down"))
        retry.assert_called_once()
        assert retry.call_args.kwargs["delay_seconds"] == 60
        assert retry.call_args.kwargs["attempt"] == 1

    def test_later_retries_back_off(self):
        retry = _run(ConnectionError("network down"), attempt=2)
        assert retry.call_args.kwargs["delay_seconds"] == 900
        assert retry.call_args.kwargs["attempt"] == 3

    def test_gives_up_after_three_retries(self):
        assert not _run(ConnectionError("network down"), attempt=3).called


class TestRetryCarriesItsAttempt:
    def test_queued_job_passes_the_attempt_number(self):
        fake = MagicMock()
        with patch.object(sched_mod, "_scheduler", fake):
            sched_mod._schedule_standup_retry("T1", "xoxb", "C1", 32, delay_seconds=300, attempt=2)
        assert fake.add_job.call_args.kwargs["kwargs"] == {"retry_attempt": 2}


def test_error_code_is_read_from_the_slack_response():
    assert sched_mod._slack_error_code(_SlackError("account_inactive")) == "account_inactive"
    assert sched_mod._slack_error_code(ValueError("boom")) == ""
