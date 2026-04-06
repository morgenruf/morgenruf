"""Tests for handlers.py — Slack event handler logic with mocked dependencies."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Stub heavy third-party deps before any import of handlers
_slack_bolt_mock = MagicMock()
_requests_mock = MagicMock()
_pytz_mock = MagicMock()
sys.modules.setdefault("slack_bolt", _slack_bolt_mock)
sys.modules.setdefault("requests", _requests_mock)
sys.modules.setdefault("pytz", _pytz_mock)

# Stub session_store before importing state (state.py imports it at module level).
# Save the prior value so we can restore it after the import — this prevents
# test_session_store.py from receiving the mock when it imports session_store.
_prior_session_store = sys.modules.get("session_store")
_ss_mock = MagicMock()
_ss_mock.get_session.return_value = None
_ss_mock.has_session.return_value = False
sys.modules["session_store"] = _ss_mock

import state  # noqa: E402 — must come after session_store stub

# Restore session_store so subsequent test modules see the real one
if _prior_session_store is not None:
    sys.modules["session_store"] = _prior_session_store
else:
    sys.modules.pop("session_store", None)


# ---------------------------------------------------------------------------
# _format_standup
# ---------------------------------------------------------------------------


class TestFormatStandup:
    def test_includes_user_mention(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["Yesterday work", "Today work", "None"])
        assert "<@U1>" in result

    def test_includes_date(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["y", "t", "b"])
        assert datetime.utcnow().strftime("%Y") in result

    def test_blockers_none_text(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["y", "t", "none"])
        assert "_None_ ✅" in result

    def test_blockers_n_a_text(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["y", "t", "n/a"])
        assert "_None_ ✅" in result

    def test_real_blocker_preserved(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["y", "t", "Waiting on PR review"])
        assert "Waiting on PR review" in result

    def test_mood_included_when_provided(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["y", "t", "none"], mood="😊 great")
        assert "😊 great" in result

    def test_mood_omitted_when_none(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["y", "t", "none"], mood=None)
        assert "Mood" not in result

    def test_fewer_than_three_answers_handled(self):
        from handlers import _format_standup

        result = _format_standup("U1", ["only one answer"])
        assert "only one answer" in result
        assert "—" in result  # missing answers show —


# ---------------------------------------------------------------------------
# _persist_standup
# ---------------------------------------------------------------------------


class TestPersistStandup:
    def test_calls_db_save_standup(self):
        db_mock = MagicMock()
        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import _persist_standup

            _persist_standup("T1", "U1", ["y", "t", "b"], mood="😊")

        db_mock.save_standup.assert_called_once()
        call_kwargs = db_mock.save_standup.call_args
        assert call_kwargs.kwargs["team_id"] == "T1"
        assert call_kwargs.kwargs["user_id"] == "U1"

    def test_does_not_raise_on_db_error(self):
        db_mock = MagicMock()
        db_mock.save_standup.side_effect = Exception("DB unavailable")
        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import _persist_standup

            _persist_standup("T1", "U1", ["y", "t", "b"])  # should not raise


# ---------------------------------------------------------------------------
# _send_question_block
# ---------------------------------------------------------------------------


class TestSendQuestionBlock:
    def test_calls_chat_post_message_with_blocks(self):
        client = MagicMock()
        from handlers import _send_question_block

        _send_question_block(client, "U1", "What did you do yesterday?", 0)

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "U1"
        assert "blocks" in call_kwargs
        blocks = call_kwargs["blocks"]
        assert any(b.get("block_id") == "answer_0" for b in blocks)

    def test_block_id_uses_step_number(self):
        client = MagicMock()
        from handlers import _send_question_block

        _send_question_block(client, "U2", "What are blockers?", 2)
        call_kwargs = client.chat_postMessage.call_args.kwargs
        blocks = call_kwargs["blocks"]
        assert any(b.get("block_id") == "answer_2" for b in blocks)


# ---------------------------------------------------------------------------
# _start_standup_session
# ---------------------------------------------------------------------------


class TestStartStandupSession:
    def test_already_active_sends_message_and_returns(self):
        """If a session is already active, sends a warning and does not start a new one."""
        _ss_mock.has_session.return_value = True
        client = MagicMock()
        db_mock = MagicMock()

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import _start_standup_session

            _start_standup_session("U1", "T1", client)

        client.chat_postMessage.assert_called_once()
        assert "already" in client.chat_postMessage.call_args.kwargs.get("text", "").lower()
        _ss_mock.has_session.return_value = False  # reset

    def test_new_session_sends_starting_message(self):
        _ss_mock.has_session.return_value = False
        _ss_mock.get_session.return_value = None
        client = MagicMock()
        db_mock = MagicMock()
        db_mock.get_workspace_config.return_value = {"channel_id": "C1", "questions": ["Q1", "Q2", "Q3"]}

        # Patch state_store.start to return a real UserSession
        fake_session = state.UserSession(
            cache_key="T1:U1",
            team_id="T1",
            channel="C1",
            questions=["Q1", "Q2", "Q3"],
        )

        with patch.dict(sys.modules, {"db": db_mock}):
            with patch.object(state.state_store, "start", return_value=fake_session):
                with patch.object(state.state_store, "is_active", return_value=False):
                    from handlers import _start_standup_session

                    _start_standup_session("U1", "T1", client)

        # Should post the "Starting your standup!" message
        texts = [c.kwargs.get("text", "") for c in client.chat_postMessage.call_args_list]
        assert any("standup" in t.lower() for t in texts)


# ---------------------------------------------------------------------------
# fire_webhooks
# ---------------------------------------------------------------------------


class TestFireWebhooks:
    def test_posts_to_registered_hooks(self):
        import handlers

        db_mock = MagicMock()
        db_mock.get_webhooks.return_value = [
            {"webhook_url": "https://hooks.example.com/standup", "events": ["standup.completed"], "secret": None}
        ]
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)

        with patch.dict(sys.modules, {"db": db_mock}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.fire_webhooks("T1", "standup.completed", {"user": "U1"})

        requests_mock.post.assert_called_once()
        call_kwargs = requests_mock.post.call_args.kwargs
        assert call_kwargs["headers"]["X-Morgenruf-Event"] == "standup.completed"

    def test_skips_hooks_for_different_event(self):
        import handlers

        db_mock = MagicMock()
        db_mock.get_webhooks.return_value = [
            {"webhook_url": "https://hooks.example.com/other", "events": ["member.joined"], "secret": None}
        ]
        requests_mock = MagicMock()

        with patch.dict(sys.modules, {"db": db_mock}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.fire_webhooks("T1", "standup.completed", {"user": "U1"})

        requests_mock.post.assert_not_called()

    def test_no_webhooks_no_requests(self):
        import handlers

        db_mock = MagicMock()
        db_mock.get_webhooks.return_value = []
        requests_mock = MagicMock()

        with patch.dict(sys.modules, {"db": db_mock}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.fire_webhooks("T1", "standup.completed", {})

        requests_mock.post.assert_not_called()

    def test_request_failure_does_not_raise(self):
        import handlers

        db_mock = MagicMock()
        db_mock.get_webhooks.return_value = [
            {"webhook_url": "https://hooks.example.com/standup", "events": ["standup.completed"], "secret": None}
        ]
        requests_mock = MagicMock()
        requests_mock.post.side_effect = Exception("Connection error")

        with patch.dict(sys.modules, {"db": db_mock}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.fire_webhooks("T1", "standup.completed", {})  # should not raise

    def test_adds_hmac_signature_when_secret_set(self):
        import handlers

        db_mock = MagicMock()
        db_mock.get_webhooks.return_value = [
            {
                "webhook_url": "https://hooks.example.com/secret",
                "events": ["standup.completed"],
                "secret": "mysecret",
            }
        ]
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)

        with patch.dict(sys.modules, {"db": db_mock}):
            with patch.object(handlers, "requests", requests_mock):
                handlers.fire_webhooks("T1", "standup.completed", {"user": "U1"})

        headers = requests_mock.post.call_args.kwargs["headers"]
        assert "X-Morgenruf-Signature" in headers
        assert headers["X-Morgenruf-Signature"].startswith("sha256=")


# ---------------------------------------------------------------------------
# can_edit_response
# ---------------------------------------------------------------------------


class TestCanEditResponse:
    def _standup(self, user_id="U1", team_id="T1", hours_ago=1):
        from datetime import timedelta

        return {
            "user_id": user_id,
            "team_id": team_id,
            "submitted_at": datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago),
        }

    def test_within_window_returns_true(self):
        db_mock = MagicMock()
        db_mock.get_standup_by_id.return_value = self._standup(hours_ago=1)
        db_mock.get_workspace_config.return_value = {"edit_window_hours": 4}

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import can_edit_response

            assert can_edit_response("T1", "U1", 1) is True

    def test_outside_window_returns_false(self):
        db_mock = MagicMock()
        db_mock.get_standup_by_id.return_value = self._standup(hours_ago=5)
        db_mock.get_workspace_config.return_value = {"edit_window_hours": 4}

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import can_edit_response

            assert can_edit_response("T1", "U1", 1) is False

    def test_standup_not_found_returns_false(self):
        db_mock = MagicMock()
        db_mock.get_standup_by_id.return_value = None

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import can_edit_response

            assert can_edit_response("T1", "U1", 999) is False

    def test_wrong_user_returns_false(self):
        db_mock = MagicMock()
        db_mock.get_standup_by_id.return_value = self._standup(user_id="U2")
        db_mock.get_workspace_config.return_value = {"edit_window_hours": 4}

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import can_edit_response

            assert can_edit_response("T1", "U1", 1) is False

    def test_none_edit_window_returns_true(self):
        db_mock = MagicMock()
        db_mock.get_standup_by_id.return_value = self._standup(hours_ago=100)
        db_mock.get_workspace_config.return_value = {"edit_window_hours": None}

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import can_edit_response

            assert can_edit_response("T1", "U1", 1) is True

    def test_zero_edit_window_returns_true(self):
        db_mock = MagicMock()
        db_mock.get_standup_by_id.return_value = self._standup(hours_ago=100)
        db_mock.get_workspace_config.return_value = {"edit_window_hours": 0}

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import can_edit_response

            assert can_edit_response("T1", "U1", 1) is True

    def test_db_exception_returns_false(self):
        db_mock = MagicMock()
        db_mock.get_standup_by_id.side_effect = Exception("DB down")

        with patch.dict(sys.modules, {"db": db_mock}):
            from handlers import can_edit_response

            assert can_edit_response("T1", "U1", 1) is False
