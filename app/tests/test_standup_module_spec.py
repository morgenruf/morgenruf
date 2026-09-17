"""Standup exposes itself through the module contract.

The claim_dm tests are net-new coverage: the catch-all listener they replace
(handlers.py:804) had no test at all, and sits in the uncovered 71% of that
file.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.core.dm_router import DMContext
from src.core.modules import ModuleSpec
from src.modules import REGISTRY
from src.modules.standup import MODULE


def test_standup_is_a_module_spec():
    assert isinstance(MODULE, ModuleSpec)
    assert MODULE.name == "standup"


def test_standup_is_enabled_by_default():
    assert MODULE.default_enabled is True


def test_standup_requires_no_new_scopes():
    """Existing installs must keep working without re-authorising."""
    assert MODULE.required_scopes == ()


def test_standup_is_in_the_registry():
    assert MODULE in REGISTRY


def test_registry_names_are_unique():
    names = [s.name for s in REGISTRY]
    assert len(names) == len(set(names))


def _ctx(text="finished the migration", event=None):
    return DMContext(
        team_id="T1",
        user_id="U1",
        channel_id="D1",
        text=text,
        event=event if event is not None else {"channel_type": "im", "user": "U1", "team": "T1"},
        client=MagicMock(),
    )


def test_claim_dm_claims_a_message_when_a_session_is_in_progress():
    """Mirrors the original listener: it only acts on an in-progress session."""
    session = MagicMock()
    session.questions = ["q1", "q2"]
    session.step = 0
    with patch("src.modules.standup.handlers.state_store") as store:
        store.get.return_value = session
        store.record_answer.return_value = session
        with patch("src.modules.standup.handlers._send_question_block") as send:
            assert MODULE.claim_dm(_ctx()) is True
            send.assert_called_once()


def test_claim_dm_declines_when_no_session_is_in_progress():
    """Matches the early return at the original handlers.py:818.

    Declining is what lets the DM router offer the message to the next module
    instead of standup swallowing it.
    """
    with patch("src.modules.standup.handlers.state_store") as store:
        store.get.return_value = None
        assert MODULE.claim_dm(_ctx()) is False


def test_claim_dm_declines_messages_with_a_subtype():
    """Matches the early return at the original handlers.py:809."""
    event = {"channel_type": "im", "user": "U1", "team": "T1", "subtype": "message_changed"}
    assert MODULE.claim_dm(_ctx(event=event)) is False


def test_claim_dm_declines_non_im_channels():
    event = {"channel_type": "channel", "user": "U1", "team": "T1"}
    assert MODULE.claim_dm(_ctx(event=event)) is False


def test_claim_dm_asks_for_mood_once_every_question_is_answered():
    session = MagicMock()
    session.questions = ["q1", "q2"]
    session.step = 2
    with patch("src.modules.standup.handlers.state_store") as store:
        store.get.return_value = session
        store.record_answer.return_value = session
        with patch("src.modules.standup.handlers._send_mood_block") as mood:
            assert MODULE.claim_dm(_ctx()) is True
            mood.assert_called_once()


def test_claim_dm_completes_the_standup_after_mood():
    session = MagicMock()
    session.questions = ["q1", "q2"]
    session.step = 3
    with patch("src.modules.standup.handlers.state_store") as store:
        store.get.return_value = session
        store.record_answer.return_value = session
        with patch("src.modules.standup.handlers._complete_standup") as complete:
            assert MODULE.claim_dm(_ctx()) is True
            complete.assert_called_once()
