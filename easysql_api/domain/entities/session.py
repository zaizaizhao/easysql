"""Session aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from easysql_api.domain.entities.message import Message
from easysql_api.domain.entities.turn import Turn
from easysql_api.domain.value_objects.query_status import QueryStatus


@dataclass
class Session:
    session_id: str
    db_name: str | None = None
    status: QueryStatus = QueryStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_query: str | None = None
    generated_sql: str | None = None
    validation_passed: bool | None = None
    clarification_questions: list[str] | None = None
    state: dict[str, Any] | None = None
    turns: list[Turn] = field(default_factory=list)
    messages: dict[str, Message] = field(default_factory=dict)
    title: str | None = None
    _turn_counter: int = 0

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def create_turn(self, question: str) -> Turn:
        self._turn_counter += 1
        turn = Turn(turn_id=f"turn-{self._turn_counter:03d}", question=question)
        self.turns.append(turn)
        self.touch()
        return turn

    def get_current_turn(self) -> Turn | None:
        return self.turns[-1] if self.turns else None

    def get_turn(self, turn_id: str) -> Turn | None:
        for turn in self.turns:
            if turn.turn_id == turn_id:
                return turn
        return None

    def add_message(self, message: Message) -> None:
        self.messages[message.message_id] = message
        self.touch()
