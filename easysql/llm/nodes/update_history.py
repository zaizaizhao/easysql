"""
Update History Node.

Appends the latest turn into conversation_history for multi-turn memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter


class UpdateHistoryNode(BaseNode):
    """Append the current turn to conversation history."""

    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        question = state.get("raw_query") or ""
        sql = state.get("generated_sql")
        error = state.get("error")

        if not question or (sql is None and error is None):
            return {}

        history = list(state.get("conversation_history") or [])
        retrieval = state.get("retrieval_result") or {}

        token_count = self._estimate_turn_tokens(question, sql)

        history.append(
            {
                "message_id": state.get("current_message_id") or str(uuid4()),
                "question": question,
                "sql": sql,
                "tables_used": retrieval.get("tables", []),
                "token_count": token_count,
                "clarification_questions": state.get("clarification_questions"),
                "clarification_answer": None,
                "validation_passed": state.get("validation_passed"),
                "error": error,
                "db_name": state.get("db_name"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        return {"conversation_history": history}

    @staticmethod
    def _estimate_turn_tokens(question: str, sql: str | None) -> int:
        text = question + (sql or "")
        return count_tokens_approximately([HumanMessage(content=text)])


def update_history_node(
    state: EasySQLState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[Any, Any]:
    node = UpdateHistoryNode()
    return node(state, config, writer=writer)
