"""Conversation state — tracks each user's standup progress in memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock


QUESTIONS = [
    "✅ *What did you complete yesterday?*\n> List by project (e.g. `Proj-Bridj: deployed TF module`)",
    "🎯 *What are you working on today?*\n> List by project",
    "🚧 *Any blockers?*\n> Type `none` if you're clear",
]


@dataclass
class UserSession:
    user_id: str
    team: str
    step: int = 0                        # 0=sent q1, 1=sent q2, 2=sent q3, 3=done
    answers: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)


class StateStore:
    def __init__(self):
        self._sessions: dict[str, UserSession] = {}
        self._lock = Lock()

    def start(self, user_id: str, team: str) -> UserSession:
        with self._lock:
            session = UserSession(user_id=user_id, team=team)
            self._sessions[user_id] = session
            return session

    def get(self, user_id: str) -> UserSession | None:
        return self._sessions.get(user_id)

    def record_answer(self, user_id: str, answer: str) -> UserSession | None:
        with self._lock:
            session = self._sessions.get(user_id)
            if not session:
                return None
            session.answers.append(answer)
            session.step += 1
            return session

    def clear(self, user_id: str) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)

    def is_active(self, user_id: str) -> bool:
        return user_id in self._sessions


state_store = StateStore()
