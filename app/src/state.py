"""Conversation state — tracks each user's active standup session in memory.

Per-workspace persistent data (members, standups) lives in PostgreSQL via db.py.
This module holds only the transient DM conversation state needed during a session.
Cache keys are `team_id:user_id` to support multi-workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Optional


QUESTIONS = [
    "✅ *What did you complete yesterday?*\n> List by project (e.g. `Proj-Bridj: deployed TF module`)",
    "🎯 *What are you working on today?*\n> List by project",
    "🚧 *Any blockers?*\n> Type `none` if you're clear",
]


@dataclass
class UserSession:
    cache_key: str          # "team_id:user_id"
    team_id: str
    channel: str            # target channel for the summary post
    step: int = 0           # 0=sent q1, 1=sent q2, 2=sent q3, 3=done
    answers: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def user_id(self) -> str:
        return self.cache_key.split(":", 1)[-1]


class StateStore:
    """In-memory store for active standup DM conversations."""

    def __init__(self) -> None:
        self._sessions: dict[str, UserSession] = {}
        self._lock = Lock()

    def start(self, cache_key: str, channel: str, *, team_id: str = "") -> UserSession:
        """Begin a new standup session. cache_key should be 'team_id:user_id'."""
        if not team_id:
            # Derive team_id from cache_key when not provided explicitly
            team_id = cache_key.split(":", 1)[0] if ":" in cache_key else ""
        with self._lock:
            session = UserSession(cache_key=cache_key, team_id=team_id, channel=channel)
            self._sessions[cache_key] = session
            return session

    def get(self, cache_key: str) -> Optional[UserSession]:
        return self._sessions.get(cache_key)

    def record_answer(self, cache_key: str, answer: str) -> Optional[UserSession]:
        with self._lock:
            session = self._sessions.get(cache_key)
            if not session:
                return None
            session.answers.append(answer)
            session.step += 1
            return session

    def clear(self, cache_key: str) -> None:
        with self._lock:
            self._sessions.pop(cache_key, None)

    def is_active(self, cache_key: str) -> bool:
        return cache_key in self._sessions


state_store = StateStore()
