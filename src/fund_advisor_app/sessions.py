"""Bounded in-memory chat sessions for temporary multi-turn context."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fund_advisor_agent.state import AgentResponse, Intent

from .schemas import ConversationTurn, SessionView


@dataclass
class SessionRecord:
    session_id: str
    created_at: datetime
    updated_at: datetime
    turns: list[ConversationTurn] = field(default_factory=list)
    last_entities: list[str] = field(default_factory=list)
    last_intent: Intent | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class InMemorySessionStore:
    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_sessions: int,
        max_turns_per_session: int,
    ) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_sessions = max_sessions
        self._max_turns = max_turns_per_session
        self._sessions: OrderedDict[str, SessionRecord] = OrderedDict()
        self._lock = asyncio.Lock()

    async def create(self) -> SessionRecord:
        async with self._lock:
            self._prune_expired()
            while len(self._sessions) >= self._max_sessions:
                self._sessions.popitem(last=False)
            now = _now()
            record = SessionRecord(
                session_id=uuid4().hex,
                created_at=now,
                updated_at=now,
            )
            self._sessions[record.session_id] = record
            return record

    async def get_or_create(self, session_id: str | None) -> SessionRecord:
        if session_id is None:
            return await self.create()
        async with self._lock:
            self._prune_expired()
            record = self._sessions.get(session_id)
            if record is None:
                now = _now()
                record = SessionRecord(
                    session_id=uuid4().hex,
                    created_at=now,
                    updated_at=now,
                )
                while len(self._sessions) >= self._max_sessions:
                    self._sessions.popitem(last=False)
                self._sessions[record.session_id] = record
                return record
            record.updated_at = _now()
            self._sessions.move_to_end(session_id)
            return record

    async def get(self, session_id: str) -> SessionRecord | None:
        async with self._lock:
            self._prune_expired()
            record = self._sessions.get(session_id)
            if record is not None:
                record.updated_at = _now()
                self._sessions.move_to_end(session_id)
            return record

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    async def record_exchange(
        self,
        record: SessionRecord,
        message: str,
        response: AgentResponse,
    ) -> None:
        now = _now()
        record.turns.extend(
            [
                ConversationTurn(
                    role="user",
                    content=message,
                    created_at=now,
                ),
                ConversationTurn(
                    role="assistant",
                    content=response.answer,
                    created_at=_now(),
                ),
            ]
        )
        record.turns = record.turns[-self._max_turns :]
        if response.entities:
            record.last_entities = list(response.entities)
        if response.intent is not None:
            record.last_intent = response.intent
        record.updated_at = _now()

    @staticmethod
    def view(record: SessionRecord) -> SessionView:
        return SessionView(
            session_id=record.session_id,
            turns=list(record.turns),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _prune_expired(self) -> None:
        cutoff = _now() - self._ttl
        expired = [
            session_id
            for session_id, record in self._sessions.items()
            if record.updated_at < cutoff
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)


def _now() -> datetime:
    return datetime.now(timezone.utc)
