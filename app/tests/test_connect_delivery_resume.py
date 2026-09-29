"""An interrupted coffee round resumes, and rate limiting never drops a pair.

A pod killed partway through delivering a round (a rollout) left the rest of
the pairs unintroduced for good: delivery only ran from run_round, and the
same-day guard stopped the catch-up from starting that round again. And three
rate limited responses in a row counted as a permanent failure, which marked
the match delivered with no channel.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from slack_sdk.errors import SlackApiError


@pytest.fixture
def jobs():
    import src.modules.connect.jobs as jobs

    return jobs


@pytest.fixture
def api():
    import src.modules.connect.slack_api as api

    return api


def _ratelimited(retry_after="1"):
    resp = MagicMock()
    resp.get.side_effect = lambda k, d=None: "ratelimited" if k == "error" else d
    resp.headers = {"Retry-After": retry_after}
    return SlackApiError("ratelimited", resp)


def _error(code):
    resp = MagicMock()
    resp.get.side_effect = lambda k, d=None: code if k == "error" else d
    resp.headers = {}
    return SlackApiError(code, resp)


class TestCall:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch, api):
        self.slept: list[float] = []
        monkeypatch.setattr(api.time, "sleep", self.slept.append)

    def test_rate_limit_waits_do_not_use_up_attempts(self, api):
        fn = MagicMock(side_effect=[_ratelimited(), _ratelimited(), _ratelimited(), _ratelimited(), {"ok": True}])
        assert api._call(fn) == {"ok": True}
        assert self.slept == [1, 1, 1, 1]

    def test_endless_rate_limit_is_retryable_not_permanent(self, api):
        fn = MagicMock(side_effect=_ratelimited("30"))
        with pytest.raises(api.RetryableSlackError):
            api._call(fn)
        assert sum(self.slept) <= api._MAX_RATE_LIMIT_WAIT_SECONDS

    def test_network_errors_are_retried(self, api):
        fn = MagicMock(side_effect=[ConnectionError("reset"), {"ok": True}])
        assert api._call(fn) == {"ok": True}

    def test_repeated_transient_errors_are_retryable(self, api):
        fn = MagicMock(side_effect=_error("internal_error"))
        with pytest.raises(api.RetryableSlackError):
            api._call(fn)
        assert fn.call_count == api._MAX_RETRIES

    def test_permanent_errors_stay_permanent(self, api):
        fn = MagicMock(side_effect=_error("channel_not_found"))
        with pytest.raises(api.PermanentSlackError):
            api._call(fn)
        assert fn.call_count == 1


@pytest.fixture
def cdb(monkeypatch, jobs):
    import src.modules.connect.db as cdb

    state = {"undelivered": [{"id": 1, "member_ids": ["U1", "U2"]}, {"id": 2, "member_ids": ["U3", "U4"]}]}
    fake = MagicMock()
    fake.get_program.return_value = {"video_mode": "none", "suggest_times": False}
    fake.claim_round_delivery.return_value = True
    fake.undelivered_matches.side_effect = lambda rid: list(state["undelivered"])

    def mark(match_id, channel):
        state["undelivered"] = [m for m in state["undelivered"] if m["id"] != match_id]

    fake.mark_delivered.side_effect = mark
    for name in (
        "get_program",
        "claim_round_delivery",
        "renew_round_delivery",
        "release_round_delivery",
        "undelivered_matches",
        "mark_delivered",
        "set_round_state",
        "rounds_with_undelivered",
    ):
        monkeypatch.setattr(cdb, name, getattr(fake, name))
    monkeypatch.setattr(jobs, "_client", lambda *_: object())
    monkeypatch.setattr(jobs.api, "throttle", lambda: None)
    monkeypatch.setattr(jobs.cblocks, "intro_message", lambda *a, **k: ("hi", []))
    return fake, state


class TestDeliverRound:
    def test_all_delivered_marks_the_round(self, jobs, cdb, monkeypatch):
        fake, _ = cdb
        monkeypatch.setattr(jobs.api, "open_group_dm", lambda c, m: "G" + m[0])
        monkeypatch.setattr(jobs.api, "post", lambda *a: None)
        assert jobs.deliver_round(10, "", "T1", 5) is True
        fake.set_round_state.assert_called_once_with(10, "delivered")
        fake.release_round_delivery.assert_called_once_with(10)

    def test_a_retryable_failure_leaves_the_round_resumable(self, jobs, cdb, monkeypatch):
        fake, state = cdb

        def post(client, channel, text, blocks):
            if channel == "GU3":
                raise jobs.api.RetryableSlackError("still rate limited")

        monkeypatch.setattr(jobs.api, "open_group_dm", lambda c, m: "G" + m[0])
        monkeypatch.setattr(jobs.api, "post", post)
        assert jobs.deliver_round(10, "", "T1", 5) is False
        assert [m["id"] for m in state["undelivered"]] == [2]
        fake.set_round_state.assert_not_called()

    def test_another_pod_delivering_is_left_alone(self, jobs, cdb, monkeypatch):
        fake, _ = cdb
        fake.claim_round_delivery.return_value = False
        opened = MagicMock()
        monkeypatch.setattr(jobs.api, "open_group_dm", opened)
        assert jobs.deliver_round(10, "", "T1", 5) is False
        opened.assert_not_called()
        fake.release_round_delivery.assert_not_called()

    def test_lease_is_renewed_after_every_match(self, jobs, cdb, monkeypatch):
        fake, _ = cdb
        monkeypatch.setattr(jobs.api, "open_group_dm", lambda c, m: "G")
        monkeypatch.setattr(jobs.api, "post", lambda *a: None)
        jobs.deliver_round(10, "", "T1", 5)
        assert fake.renew_round_delivery.call_count == 2


class TestResume:
    def test_sweep_resumes_interrupted_rounds(self, jobs, cdb, monkeypatch):
        fake, _ = cdb
        fake.rounds_with_undelivered.return_value = [{"id": 10, "program_id": 5}]
        delivered = []
        monkeypatch.setattr(jobs, "deliver_round", lambda rid, tok, team, pid: delivered.append((rid, pid)) or True)
        assert jobs.resume_undelivered_rounds("T1") == 1
        assert delivered == [(10, 5)]
        fake.rounds_with_undelivered.assert_called_once_with("T1", jobs.RESUME_DELIVERY_WITHIN_HOURS)

    def test_followup_sweep_runs_the_resume(self, jobs, monkeypatch):
        import src.modules.connect.db as cdb

        called = []
        monkeypatch.setattr(jobs, "resume_undelivered_rounds", called.append)
        monkeypatch.setattr(cdb, "queue_followups", lambda *a: 0)
        monkeypatch.setattr(cdb, "claim_due_followups", lambda *a: [])
        jobs.send_due_followups("T1")
        assert called == ["T1"]

    def test_a_lookup_failure_does_not_break_the_sweep(self, jobs, cdb):
        fake, _ = cdb
        fake.rounds_with_undelivered.side_effect = RuntimeError("db down")
        assert jobs.resume_undelivered_rounds("T1") == 0
