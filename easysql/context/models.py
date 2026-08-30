"""
Context Builder Data Models.

Defines input/output data structures for context construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from easysql.retrieval.schema_retrieval import RetrievalResult


@dataclass
class FewShotExample:
    """
    Few-shot example for in-context learning.

    Attributes:
        question: Natural language question.
        sql: Corresponding SQL query.
        explanation: Optional explanation of the SQL.
        tables_used: Tables used in the query.
    """

    question: str
    sql: str
    explanation: str | None = None
    tables_used: list[str] = field(default_factory=list)


@dataclass
class ContextInput:
    """
    Input for context building.

    Contains all data needed to construct LLM context.

    Attributes:
        question: User's natural language question.
        retrieval_result: Schema retrieval result with tables, columns, join paths.
        db_name: Optional database name for context.
        few_shot_examples: Optional few-shot examples for in-context learning.
        code_context: Optional pre-formatted code snippets related to the query.
        custom_context: Optional custom context data.
    """

    question: str
    retrieval_result: RetrievalResult
    db_name: str | None = None
    db_names: list[str] = field(default_factory=list)
    database_context: str | None = None

    # Extension points for future features
    few_shot_examples: list[FewShotExample] = field(default_factory=list)
    code_context: str | None = None
    custom_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionContent:
    """
    Result of rendering a context section.

    Attributes:
        name: Section name for identification.
        content: Rendered content string.
        token_count: Estimated token count.
        metadata: Additional metadata about the section.
    """

    name: str
    content: str
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextOutput:
    """
    Output of context building.

    Contains the final prompts ready for LLM consumption.

    Attributes:
        system_prompt: System prompt for the LLM.
        user_prompt: User prompt containing the question and context.
        sections: Individual section contents for debugging.
        total_tokens: Estimated total token count.
        metadata: Additional metadata about the context.
    """

    system_prompt: str
    user_prompt: str
    sections: list[SectionContent] = field(default_factory=list)
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
