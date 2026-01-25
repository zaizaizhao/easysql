"""
Base Node Class.

Provides a base class for all LangGraph nodes with common utilities.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from easysql.llm.state import EasySQLState

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter


class SQLResponse(BaseModel):
    """Structured output schema for SQL generation.

    Used with LLM's with_structured_output() to directly extract SQL
    without manual regex parsing.
    """

    sql: str = Field(description="生成的 SQL 语句，不包含 markdown 代码块标记")
    explanation: str | None = Field(default=None, description="SQL 逻辑的简要说明（可选）")


class BaseNode(ABC):
    """Abstract base class for all EasySQL LangGraph nodes."""

    @abstractmethod
    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any] | Coroutine[Any, Any, dict[Any, Any]]:
        """Process state and return updates."""
        pass

    @staticmethod
    def get_structured_llm(llm: BaseChatModel) -> Runnable[Any, Any]:
        """Wrap LLM with structured output for SQL extraction."""
        return llm.with_structured_output(SQLResponse)

    # SQL 关键字，用于验证提取的内容是否为有效 SQL
    SQL_KEYWORDS = (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "WITH",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "MERGE",
        "EXPLAIN",
        "SHOW",
        "DESCRIBE",
        "DESC",
    )

    @classmethod
    def _is_valid_sql(cls, text: str) -> bool:
        """Check if text starts with a valid SQL keyword.

        This is a basic validation to prevent non-SQL text from being
        executed as SQL (e.g., error messages like "Sorry, need more steps").
        """
        if not text:
            return False
        # 去除前导空白和注释，获取第一个有效词
        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("--"):
                continue
            # 检查是否以 SQL 关键字开头
            first_word = line.split()[0].upper() if line.split() else ""
            return first_word in cls.SQL_KEYWORDS
        return False

    @classmethod
    def extract_sql(cls, content: str) -> str:
        """Fallback: Extract SQL from markdown code blocks via regex.

        Only used when structured output is not available.

        Returns:
            Extracted SQL string, or empty string if no valid SQL found.
        """
        # ```sql ... ``` pattern (优先级最高)
        match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if match:
            sql = match.group(1).strip()
            if cls._is_valid_sql(sql):
                return sql

        # ``` ... ``` pattern (通用代码块)
        match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            sql = match.group(1).strip()
            if cls._is_valid_sql(sql):
                return sql

        # Fallback: 检查原始内容是否是有效 SQL
        stripped = content.strip()
        if cls._is_valid_sql(stripped):
            return stripped

        # 未找到有效 SQL，返回空字符串而非原始内容
        return ""
