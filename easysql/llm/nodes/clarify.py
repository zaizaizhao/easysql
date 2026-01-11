"""
Clarify Node (HITL).

Asks user for clarification if needed using LangGraph interrupt.
"""

from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.language_models import BaseChatModel
from langgraph.types import interrupt

from easysql.config import get_settings, LLMConfig
from easysql.llm.state import EasySQLState, SchemaHintDict
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode


class ClarifyNode(BaseNode):
    """Node to handle clarification interaction via HITL.

    Uses LangGraph interrupt to pause and collect user responses.
    """

    def __init__(self, llm: Optional[BaseChatModel] = None, config: Optional[LLMConfig] = None):
        self._llm = llm
        self._config = config

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            config = self._config or get_settings().llm
            self._llm = get_llm(config, "planning")
        return self._llm

    def _format_schema_context(self, hint: SchemaHintDict | None) -> str:
        if not hint or not hint.get("tables"):
            return ""

        lines = []
        for t in hint["tables"]:
            table_line = f"- {t['name']}"
            cn = t.get("chinese_name")
            if cn:
                table_line += f"（{cn}）"
            lines.append(table_line)

            for col in t.get("key_columns") or []:
                col_line = f"  • {col['column_name']}"
                col_cn = col.get("chinese_name")
                if col_cn:
                    col_line += f"（{col_cn}）"
                col_line += f" [{col.get('data_type', '')}]"
                lines.append(col_line)

        return "\n".join(lines)

    def __call__(self, state: EasySQLState) -> dict:
        questions = state.get("clarification_questions") or []

        if not questions:
            return {"clarified_query": state["raw_query"]}

        question_text = "\n".join(f"- {q}" for q in questions)

        user_response = interrupt(
            {
                "type": "clarification",
                "question": f"为了更准确地为您生成SQL，请确认以下信息：\n{question_text}",
                "raw_query": state["raw_query"],
            }
        )

        schema_hint = state.get("schema_hint")
        schema_context = self._format_schema_context(schema_hint)

        rewrite_prompt = f"""基于用户反馈完善查询。

原始问题：{state["raw_query"]}

相关表结构：
{schema_context if schema_context else "（无）"}

需澄清的问题：
{question_text}

用户回答：{user_response}

请结合用户回答和表结构，输出完善后的完整问题。
要求：
1. 只输出问题文本，不要有其他内容
2. 使用实际存在的表名和字段名
3. 保持问题的业务语义，只补充澄清的信息"""

        response = self.llm.invoke([HumanMessage(content=rewrite_prompt)])

        return {
            "clarified_query": response.content.strip(),
            "clarification_questions": None,
            "messages": [
                AIMessage(content=f"已确认：{user_response}\n正在为您生成SQL..."),
                HumanMessage(content=str(user_response)),
            ],
        }


def clarify_node(state: EasySQLState) -> dict:
    node = ClarifyNode()
    return node(state)
