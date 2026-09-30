"""Conversation state — tracks each user's active standup session.

Per-workspace persistent data (members, standups) lives in PostgreSQL via db.py.
Active DM conversation state is stored in Redis (with in-memory fallback) via
session_store so sessions survive pod restarts.
Cache keys are `team_id:user_id` to support multi-workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Optional

import src.core.session_store as session_store

QUESTIONS = [
    "✅ *What did you complete yesterday?*\n> List by project (e.g. `Proj-Bridj: deployed TF module`)",
    "🎯 *What are you working on today?*\n> List by project",
    "🚧 *Any blockers?*\n> Type `none` if you're clear",
]


@dataclass
class UserSession:
    cache_key: str  # "team_id:user_id"
    team_id: str
    channel: str  # target channel for the summary post
    step: int = 0  # 0=sent q1, 1=sent q2, 2=sent q3, 3=mood, 4=done
    answers: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    questions: list[str] = field(default_factory=lambda: list(QUESTIONS))
    standup_name: str = "Team Standup"
    schedule_id: Optional[int] = None  # source schedule — avoids channel-based lookup ambiguity
    editing_standup_id: Optional[int] = None  # set when user is editing an existing submission
    edit_initial_answers: list[str] = field(default_factory=list)  # pre-fill text for each question

    @property
    def user_id(self) -> str:
        return self.cache_key.split(":", 1)[-1]


def _serialize(session: "UserSession") -> dict:
    return {
        "cache_key": session.cache_key,
        "team_id": session.team_id,
        "channel": session.channel,
        "step": session.step,
        "answers": session.answers,
        "questions": session.questions,
        "standup_name": session.standup_name,
        "schedule_id": session.schedule_id,
        "editing_standup_id": session.editing_standup_id,
        "edit_initial_answers": session.edit_initial_answers,
        "started_at": session.started_at.isoformat(),
    }


def _parse_started_at(value: object) -> datetime:
    """The stored start time. A session written before it was stored reads as now."""
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _deserialize(data: dict) -> "UserSession":
    return UserSession(
        cache_key=data["cache_key"],
        team_id=data.get("team_id", ""),
        channel=data.get("channel", ""),
        step=data.get("step", 0),
        answers=data.get("answers", []),
        questions=data.get("questions", list(QUESTIONS)),
        standup_name=data.get("standup_name", "Team Standup"),
        schedule_id=data.get("schedule_id"),
        editing_standup_id=data.get("editing_standup_id"),
        edit_initial_answers=data.get("edit_initial_answers") or [],
        started_at=_parse_started_at(data.get("started_at")),
    )


# How long an open session for one standup holds off the DM for another.
OTHER_STANDUP_BLOCK = timedelta(hours=4)


class StateStore:
    """Redis-backed store for active standup DM conversations (in-memory fallback)."""

    def __init__(self) -> None:
        self._lock = Lock()

    def start(
        self,
        cache_key: str,
        channel: str,
        *,
        team_id: str = "",
        questions: list[str] | None = None,
        standup_name: str = "Team Standup",
        schedule_id: Optional[int] = None,
        editing_standup_id: Optional[int] = None,
        edit_initial_answers: Optional[list[str]] = None,
    ) -> UserSession:
        """Begin a new standup session. cache_key should be 'team_id:user_id'."""
        if not team_id:
            # Derive team_id from cache_key when not provided explicitly
            team_id = cache_key.split(":", 1)[0] if ":" in cache_key else ""
        with self._lock:
            session = UserSession(
                cache_key=cache_key,
                team_id=team_id,
                channel=channel,
                questions=list(questions) if questions is not None else list(QUESTIONS),
                standup_name=standup_name,
                schedule_id=schedule_id,
                editing_standup_id=editing_standup_id,
                edit_initial_answers=list(edit_initial_answers) if edit_initial_answers else [],
            )
            session_store.set_session(cache_key, _serialize(session))
            return session

    def get(self, cache_key: str) -> Optional[UserSession]:
        data = session_store.get_session(cache_key)
        return _deserialize(data) if data else None

    def record_answer(self, cache_key: str, answer: str) -> Optional[UserSession]:
        with self._lock:
            data = session_store.get_session(cache_key)
            if not data:
                return None
            session = _deserialize(data)
            session.answers.append(answer)
            session.step += 1
            session_store.set_session(cache_key, _serialize(session))
            return session

    def clear(self, cache_key: str) -> None:
        session_store.delete_session(cache_key)

    def is_active(self, cache_key: str) -> bool:
        return session_store.has_session(cache_key)

    def blocks_scheduled_dm(self, cache_key: str, schedule_id: Optional[int], now: datetime | None = None) -> bool:
        """Whether an open session should stop a scheduled standup DM.

        A session for the same standup is still in progress, so it is left
        alone (the DM job's own retries hit this). A session for another
        standup blocks only while it is recent, which is what the old 4 hour
        TTL gave. Sessions now live for a working day, and without this an
        abandoned morning standup would have swallowed the evening one.
        """
        session = self.get(cache_key)
        if session is None:
            return False
        if schedule_id is not None and session.schedule_id == schedule_id:
            return True
        now = now or datetime.now(timezone.utc)
        return now - session.started_at < OTHER_STANDUP_BLOCK


state_store = StateStore()
