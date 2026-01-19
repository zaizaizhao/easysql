"""
Base Node Class.

Provides a base class for all LangGraph nodes with common utilities.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Coroutine
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from easysql.llm.state import EasySQLState


class SQLResponse(BaseModel):
    """Structured output schema for SQL generation.

    Used with LLM's with_structured_output() to directly extract SQL
    without manual regex parsing.
    """

    sql: str = Field(description="生成的 SQL 语句，不包含 markdown 代码块标记")
    explanation: str | None = Field(default=None, description="SQL 逻辑的简要说明（可选）")


class BaseNode(ABC):
    """Abstract base class for all EasySQL LangGraph nodes.

    Provides common utilities and enforces the callable interface.
    Supports both sync and async implementations.
    """

    @abstractmethod
    def __call__(self, state: EasySQLState) -> dict[Any, Any] | Coroutine[Any, Any, dict[Any, Any]]:
        """Process state and return updates.

        Args:
            state: Current graph state.

        Returns:
            Dictionary of state updates (sync or async).
        """
        pass

    @staticmethod
    def get_structured_llm(llm: BaseChatModel) -> Runnable[Any, Any]:
        """Wrap LLM with structured output for SQL extraction."""
        return llm.with_structured_output(SQLResponse)

    @staticmethod
    def extract_sql(content: str) -> str:
        """Fallback: Extract SQL from markdown code blocks via regex.

        Only used when structured output is not available.
        """
        # ```sql ... ``` pattern
        match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # ``` ... ``` pattern
        match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1).strip()

        return content.strip()
