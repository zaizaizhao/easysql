from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from easysql.config import get_settings
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.llm.state import EasySQLState

logger = get_logger(__name__)


class ShiftDetectResult(BaseModel):
    needs_new_tables: bool = Field(description="是否需要新的数据库表")
    reason: str = Field(description="判断理由")
    suggested_tables: list[str] = Field(default_factory=list, description="建议检索的表")


class ShiftDetectNode(BaseNode):
    PROMPT = """你是一个语义分析助手。判断用户的追问是否超出了当前已检索的数据库表范围。

已检索的表: {tables}

历史对话摘要: {history}

用户当前追问: {question}

请判断：
1. 这个追问是否需要新的数据库表才能回答？
2. 如果需要，可能需要哪些表？

注意：如果追问只是对已有结果的修改（如排序、分组、筛选条件变化），不需要新表。

输出 JSON 格式：
{{"needs_new_tables": true/false, "reason": "判断理由", "suggested_tables": ["表名"]}}"""

    def __call__(self, state: EasySQLState) -> dict:
        cached_context = state.get("cached_context")
        if not cached_context:
            logger.info("No cached context, requires full retrieval")
            return {"needs_new_retrieval": True, "shift_reason": "no_cached_context"}

        retrieval_result = state.get("retrieval_result")
        tables = retrieval_result.get("tables", []) if retrieval_result else []

        if not tables:
            logger.info("No tables in retrieval result, requires full retrieval")
            return {"needs_new_retrieval": True, "shift_reason": "no_tables_in_cache"}

        history = state.get("conversation_history") or []
        history_summary = self._format_history(history)

        try:
            settings = get_settings()
            llm = get_llm(settings.llm, "generation")
            structured_llm = llm.with_structured_output(ShiftDetectResult)

            response = structured_llm.invoke(
                [
                    SystemMessage(
                        content="你是一个语义分析助手，负责判断追问是否需要检索新的数据库表。"
                    ),
                    HumanMessage(
                        content=self.PROMPT.format(
                            tables=", ".join(tables),
                            history=history_summary,
                            question=state["raw_query"],
                        )
                    ),
                ]
            )

            result = cast(ShiftDetectResult, response)
            needs_new = result.needs_new_tables
            reason = result.reason

            logger.info(f"Shift detection result: needs_new={needs_new}, reason={reason}")

            return {
                "needs_new_retrieval": needs_new,
                "shift_reason": reason,
            }

        except Exception as e:
            logger.warning(f"Shift detection failed: {e}, defaulting to new retrieval")
            return {"needs_new_retrieval": True, "shift_reason": f"detection_error: {e}"}

    def _format_history(self, history: list[Any]) -> str:
        if not history:
            return "无历史对话"

        summaries = []
        for turn in history[-3:]:
            q = turn.get("question", "")
            sql = turn.get("sql", "")
            tables = turn.get("tables_used", [])
            summaries.append(f"Q: {q}\n表: {', '.join(tables)}\nSQL: {sql[:100]}...")

        return "\n---\n".join(summaries)


def shift_detect_node(state: EasySQLState) -> dict:
    node = ShiftDetectNode()
    return node(state)
