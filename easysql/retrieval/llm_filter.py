"""
LLM Filter

Uses an LLM to intelligently select the most relevant tables for a query.
This provides the highest precision but adds latency and API costs.
"""

import json
from typing import TYPE_CHECKING

from .base import FilterContext, FilterResult, TableFilter

if TYPE_CHECKING:
    pass

# Try to import OpenAI client
try:
    from openai import OpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


LLM_SYSTEM_PROMPT = """你是一个数据库专家，负责帮助确定回答用户问题需要哪些数据库表。

你的任务是从候选表列表中选择真正需要的表，以便生成正确的 SQL 查询。

选择原则：
1. 只选择直接相关的表
2. 确保选择的表之间可以通过 JOIN 连接
3. 优先选择包含用户问题中提到的字段的表
4. 不要选择无关的表

请返回 JSON 格式的表名列表，例如：["table1", "table2", "table3"]
只返回 JSON，不要有其他文字。"""

LLM_USER_PROMPT_TEMPLATE = """用户问题：{question}

候选表列表（按相关性排序）：
{tables_info}

请选择回答这个问题真正需要的表（最多 {max_tables} 张）。
返回 JSON 格式的表名列表。"""


class LLMFilter(TableFilter):
    """
    Uses LLM to select the most relevant tables.

    This filter typically runs last in the chain, after semantic and bridge
    filters have done preliminary filtering.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str = "deepseek-chat",
        max_tables: int = 8,
        timeout: float = 30.0,
    ):
        """
        Initialize the LLM filter.

        Args:
            api_key: API key for the LLM service.
            api_base: Base URL for the API (for OpenAI-compatible services).
            model: Model name to use.
            max_tables: Maximum number of tables to select.
            timeout: Request timeout in seconds.
        """
        if not HAS_OPENAI:
            raise ImportError(
                "openai package is required for LLMFilter. Install it with: pip install openai"
            )

        self._api_key = api_key
        self._api_base = api_base or "https://api.deepseek.com/v1"
        self._model = model
        self._max_tables = max_tables
        self._timeout = timeout

        # Initialize client
        self._client: OpenAI | None = None

    @property
    def name(self) -> str:
        return "llm"

    def _get_client(self) -> "OpenAI":
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._api_base,
                timeout=self._timeout,
            )
        return self._client

    def _format_tables_info(self, tables: list[str], context: FilterContext) -> str:
        """Format table information for the prompt."""
        lines = []
        for i, table in enumerate(tables, 1):
            score = context.table_scores.get(table, 0)
            meta = context.table_metadata.get(table, {})
            chinese_name = meta.get("chinese_name") or ""

            if chinese_name:
                lines.append(f"{i}. {table} ({chinese_name}) - 相关度: {score:.2f}")
            else:
                lines.append(f"{i}. {table} - 相关度: {score:.2f}")

        return "\n".join(lines)

    def filter(
        self,
        tables: list[str],
        context: FilterContext,
    ) -> FilterResult:
        """
        Use LLM to select the most relevant tables.
        """
        if not self._api_key:
            return FilterResult(tables=tables, stats={"action": "skipped", "reason": "no API key"})

        if len(tables) <= self._max_tables:
            return FilterResult(
                tables=tables,
                stats={"action": "skipped", "reason": f"already <= {self._max_tables} tables"},
            )

        try:
            client = self._get_client()

            # Format prompt
            tables_info = self._format_tables_info(tables, context)
            user_prompt = LLM_USER_PROMPT_TEMPLATE.format(
                question=context.question,
                tables_info=tables_info,
                max_tables=self._max_tables,
            )

            # Call LLM
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,  # Low temperature for consistent results
                max_tokens=1024,
            )

            # Parse response
            content = response.choices[0].message.content
            if content is None:
                return FilterResult(
                    tables=tables, stats={"action": "error", "error": "Empty LLM response"}
                )
            content = content.strip()

            # Try to extract JSON from the response
            try:
                # Handle markdown code blocks
                if "```" in content:
                    # Extract content between code blocks
                    import re

                    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                    if match:
                        content = match.group(1)

                selected_tables = json.loads(content)

                # Validate the response
                if not isinstance(selected_tables, list):
                    raise ValueError("Response is not a list")

                # Filter to only valid table names
                valid_tables = [t for t in selected_tables if t in tables]

                # Ensure we don't exceed max_tables
                valid_tables = valid_tables[: self._max_tables]

                # IMPORTANT: Always include original_tables (Milvus results + bridge tables)
                # These are critical for the query and should never be filtered out
                must_keep = set(context.original_tables)

                final_tables = []
                # First add must-keep tables that LLM selected
                for t in valid_tables:
                    if t not in final_tables:
                        final_tables.append(t)

                # Then add must-keep tables that LLM didn't select (but we need to keep)
                kept_by_must_keep = []
                for t in context.original_tables:
                    if t not in final_tables and t in tables:
                        final_tables.append(t)
                        kept_by_must_keep.append(t)

                return FilterResult(
                    tables=final_tables,
                    stats={
                        "action": "llm_filter",
                        "model": self._model,
                        "before": len(tables),
                        "after": len(final_tables),
                        "selected_by_llm": valid_tables,
                        "kept_by_must_keep": kept_by_must_keep,
                        "raw_response": content,
                    },
                )

            except (json.JSONDecodeError, ValueError) as e:
                # If parsing fails, return all tables
                return FilterResult(
                    tables=tables,
                    stats={
                        "action": "parse_error",
                        "error": str(e),
                        "raw_response": content,
                    },
                )

        except Exception as e:
            # On any error, return all tables (fail-safe)
            return FilterResult(tables=tables, stats={"action": "error", "error": str(e)})
