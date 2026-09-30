"""A standup session lasts the working day.

With a 4 hour TTL someone who opened the standup at 09:00 and answered after
13:00 lost everything they had typed. The longer lifetime must not let an
abandoned session from one standup swallow the DM for another.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import src.core.session_store as real_session_store
import src.core.state as state

T0 = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    real_session_store._redis = None
    real_session_store._memory.clear()
    with patch.object(state, "session_store", real_session_store):
        yield state.StateStore()
    real_session_store._memory.clear()


def test_ttl_covers_a_working_day_but_not_a_whole_day():
    assert real_session_store.SESSION_TTL >= 9 * 3600
    # Yesterday's abandoned session of a daily standup is gone when it fires again.
    assert real_session_store.SESSION_TTL < 24 * 3600


def test_redis_is_given_the_long_ttl(monkeypatch):
    from unittest.mock import MagicMock

    fake = MagicMock()
    monkeypatch.setattr(real_session_store, "_redis", fake)
    real_session_store.set_session("T1:U1", {"step": 1})
    assert fake.setex.call_args.args[1] == real_session_store.SESSION_TTL
    monkeypatch.setattr(real_session_store, "_redis", None)


def test_start_time_survives_a_round_trip(store):
    with patch.object(state, "datetime") as fake_dt:
        fake_dt.now.return_value = T0
        fake_dt.fromisoformat = datetime.fromisoformat
        store.start("T1:U1", "C1", schedule_id=1)
    assert store.get("T1:U1").started_at == T0


class TestScheduledDmBlocking:
    def _started(self, store, schedule_id, at):
        store.start("T1:U1", "C1", schedule_id=schedule_id)
        session = store.get("T1:U1")
        session.started_at = at
        real_session_store.set_session("T1:U1", state._serialize(session))

    def test_no_session_does_not_block(self, store):
        assert store.blocks_scheduled_dm("T1:U1", 1, now=T0) is False

    def test_same_standup_in_progress_blocks(self, store):
        self._started(store, 1, T0)
        assert store.blocks_scheduled_dm("T1:U1", 1, now=T0 + timedelta(hours=6)) is True

    def test_recent_session_for_another_standup_blocks(self, store):
        self._started(store, 1, T0)
        assert store.blocks_scheduled_dm("T1:U1", 2, now=T0 + timedelta(hours=1)) is True

    def test_abandoned_morning_session_does_not_block_the_evening_standup(self, store):
        self._started(store, 1, T0)
        assert store.blocks_scheduled_dm("T1:U1", 2, now=T0 + timedelta(hours=8)) is False
