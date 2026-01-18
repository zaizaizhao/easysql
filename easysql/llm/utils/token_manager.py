from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately

from easysql.config import get_settings
from easysql.llm.models import get_llm

if TYPE_CHECKING:
    from easysql.llm.state import ConversationTurn


class TokenManager:
    MAX_CONTEXT_TOKENS = 12000
    MAX_HISTORY_TURNS = 10
    TOKENS_RESERVED_FOR_RESPONSE = 2000

    SUMMARIZE_PROMPT = """请将以下对话历史压缩成简洁的摘要，保留关键信息：
- 用户询问的主要问题
- 涉及的数据库表
- 生成的 SQL 的核心逻辑

对话历史：
{history}

摘要（不超过200字）："""

    def __init__(self, max_tokens: int | None = None):
        self._max_tokens = max_tokens or self.MAX_CONTEXT_TOKENS

    def prepare_history(
        self,
        history: list[ConversationTurn],
        schema_context_tokens: int,
    ) -> tuple[str | None, list[ConversationTurn]]:
        available_tokens = (
            self._max_tokens - schema_context_tokens - self.TOKENS_RESERVED_FOR_RESPONSE
        )

        if available_tokens <= 0:
            return None, []

        recent_history: list[ConversationTurn] = []
        total_tokens = 0

        for turn in reversed(history[-self.MAX_HISTORY_TURNS :]):
            turn_tokens = turn.get("token_count", 0) or self._estimate_turn_tokens(turn)
            if total_tokens + turn_tokens > available_tokens:
                break
            recent_history.insert(0, turn)
            total_tokens += turn_tokens

        if len(recent_history) == len(history):
            return None, recent_history

        early_history = history[: -len(recent_history)] if recent_history else history
        if not early_history:
            return None, recent_history

        summary = self._summarize_history(early_history)
        return summary, recent_history

    def _estimate_turn_tokens(self, turn: ConversationTurn) -> int:
        text = turn.get("question", "") + (turn.get("sql") or "")
        return count_tokens_approximately([HumanMessage(content=text)])

    def _summarize_history(self, turns: list[ConversationTurn]) -> str:
        history_text = "\n".join(f"Q: {t['question']}\nSQL: {t.get('sql', 'N/A')}" for t in turns)

        try:
            settings = get_settings()
            llm = get_llm(settings.llm, "generation")
            response = llm.invoke(
                [
                    SystemMessage(content="你是一个对话摘要助手。"),
                    HumanMessage(content=self.SUMMARIZE_PROMPT.format(history=history_text)),
                ]
            )
            content = response.content
            if isinstance(content, str):
                return content
            return str(content)
        except Exception:
            return f"[历史摘要: {len(turns)} 轮对话]"

    def build_history_messages(
        self,
        summary: str | None,
        recent_history: list[ConversationTurn],
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = []

        if summary:
            messages.append(SystemMessage(content=f"历史对话摘要:\n{summary}"))

        for turn in recent_history:
            messages.append(HumanMessage(content=turn["question"]))
            if turn.get("sql"):
                messages.append(AIMessage(content=f"```sql\n{turn['sql']}\n```"))

        return messages


_default_manager: TokenManager | None = None


def get_token_manager() -> TokenManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = TokenManager()
    return _default_manager
