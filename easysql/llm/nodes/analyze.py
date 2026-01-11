"""
Analyze Query Node.

Analyzes the user query to determine ambiguity and need for HITL clarification.
Uses schema hints (from retrieve_hint node) for schema-aware clarification.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from easysql.config import get_settings, LLMConfig
from easysql.llm.state import EasySQLState, SchemaHintDict, SchemaHintColumn
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode


class AnalysisResult(BaseModel):
    """Structured output for query analysis."""

    is_clear: bool = Field(description="Whether the query is clear enough for SQL generation")
    clarification_questions: List[str] = Field(
        default_factory=list, description="List of clarifying questions if the query is unclear"
    )
    reasoning: str = Field(description="Reasoning behind the clarity judgment")


ANALYZE_SYSTEM_PROMPT = """你是一个SQL数据分析专家。分析用户问题，判断是否需要进一步澄清。

## 核心原则：尽量不问，只在真正歧义时才澄清

### 不需要澄清的情况（直接生成SQL）：
1. 时间范围已明确（如"今天"、"本月"、"最近30天"、"2024年"）
2. 只涉及一张主表，没有相似表的歧义
3. 聚合方式已明确（如"总数"、"平均值"、"最大"、"列表"）
4. 常见的业务查询，可以用合理的默认值

### 需要澄清的情况（真正的歧义）：
1. 有多个时间字段（如 create_time vs visit_date），用户未指定
2. 有多个相似含义的表/字段，无法判断用户意图
3. 缺少关键业务状态筛选（如"有效"、"已完成"），且表中确实有这类字段
4. 用户问题过于模糊，无法映射到任何表

### 澄清问题的要求：
- 最多问 1-2 个问题，优先问时间字段歧义
- 必须引用实际存在的表名和字段名
- 提供选项让用户选择，而不是开放式提问
- 如果可以用合理默认值，就不要问"""


ANALYZE_USER_PROMPT_WITH_SCHEMA = """用户问题：{query}

可能相关的数据表及字段：
{schema_hint}

语义相关的字段：
{semantic_columns}

请判断：这个问题是否存在【真正的歧义】需要用户澄清？

记住：
- 如果时间范围已明确（今天/本月/最近X天等）→ 不需要问
- 如果能用合理默认值解决 → 不需要问
- 只有当存在多个时间字段或相似表/字段导致无法判断用户意图时，才需要澄清

如果确实需要澄清，请基于上述【实际存在】的字段生成 1-2 个选择式问题。"""


ANALYZE_USER_PROMPT_NO_SCHEMA = """用户问题：{query}

请判断：这个问题是否存在【真正的歧义】需要用户澄清？

记住：尽量不问，只有当问题过于模糊、无法生成任何有意义的SQL时，才需要澄清。
如果确实需要澄清，请生成 1-2 个具体问题。"""


class AnalyzeQueryNode(BaseNode):
    """Node to analyze query ambiguity with schema-aware context.

    In plan mode, uses schema_hint from retrieve_hint node to generate
    more targeted clarification questions based on actual table structure.
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

    @property
    def config(self) -> LLMConfig:
        if self._config is None:
            self._config = get_settings().llm
        return self._config

    def _format_schema_hint(self, hint: SchemaHintDict | None) -> str:
        if not hint or not hint.get("tables"):
            return "（无相关表信息）"

        lines = []
        for t in hint["tables"]:
            name = t["name"]
            cn = t.get("chinese_name") or ""
            desc = t.get("description") or ""
            score = t.get("score", 0.0)

            table_header = f"- {name}"
            if cn:
                table_header += f"（{cn}）"
            if desc:
                table_header += f": {desc}"
            table_header += f" [相关度: {score:.2f}]"
            lines.append(table_header)

            key_cols = t.get("key_columns") or []
            if key_cols:
                for col in key_cols:
                    col_line = f"    • {col['column_name']}"
                    col_cn = col.get("chinese_name")
                    if col_cn:
                        col_line += f"（{col_cn}）"
                    col_line += f" [{col.get('data_type', 'unknown')}"
                    tags = []
                    if col.get("is_pk"):
                        tags.append("PK")
                    if col.get("is_fk"):
                        tags.append("FK")
                    if col.get("is_time"):
                        tags.append("时间")
                    if tags:
                        col_line += ", " + "/".join(tags)
                    col_line += "]"
                    lines.append(col_line)

        return "\n".join(lines)

    def _format_semantic_columns(self, hint: SchemaHintDict | None) -> str:
        if not hint:
            return "（无）"

        semantic_cols = hint.get("semantic_columns") or []
        if not semantic_cols:
            return "（无）"

        lines = []
        for col in semantic_cols:
            line = f"- {col['table_name']}.{col['column_name']}"
            col_cn = col.get("chinese_name")
            if col_cn:
                line += f"（{col_cn}）"
            line += f" [{col.get('data_type', 'unknown')}]"
            lines.append(line)

        return "\n".join(lines)

    def __call__(self, state: EasySQLState) -> dict:
        """Analyze query with schema context and determine if clarification is needed."""
        if self.config.query_mode == "fast":
            return {
                "clarified_query": state["raw_query"],
                "clarification_questions": None,
            }

        schema_hint = state.get("schema_hint")
        schema_text = self._format_schema_hint(schema_hint)
        semantic_text = self._format_semantic_columns(schema_hint)

        if schema_hint and schema_hint.get("tables"):
            user_prompt = ANALYZE_USER_PROMPT_WITH_SCHEMA.format(
                query=state["raw_query"],
                schema_hint=schema_text,
                semantic_columns=semantic_text,
            )
        else:
            user_prompt = ANALYZE_USER_PROMPT_NO_SCHEMA.format(query=state["raw_query"])

        structured_llm = self.llm.with_structured_output(AnalysisResult)

        try:
            result: AnalysisResult = structured_llm.invoke(
                [SystemMessage(content=ANALYZE_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
            )

            is_clear = result.is_clear
            questions = result.clarification_questions

            if not is_clear and not questions:
                is_clear = True

            return {
                "clarified_query": state["raw_query"] if is_clear else None,
                "clarification_questions": questions if not is_clear else None,
            }
        except Exception:
            return {
                "clarified_query": state["raw_query"],
                "clarification_questions": None,
            }


def analyze_query_node(state: EasySQLState) -> dict:
    """Factory function for AnalyzeQueryNode."""
    node = AnalyzeQueryNode()
    return node(state)
