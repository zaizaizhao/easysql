"""
Context Builder Data Models.

Defines input/output data structures for context construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING

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
    explanation: Optional[str] = None
    tables_used: List[str] = field(default_factory=list)


@dataclass
class CodeSnippet:
    """
    Code context snippet for RAG enhancement.
    
    Used to provide business logic context from actual codebase.
    
    Attributes:
        file_path: Path to the source file.
        class_name: Optional class name.
        method_name: Optional method name.
        code: The actual code snippet.
        description: Optional description of what the code does.
        relevance_score: Relevance score from RAG retrieval.
    """
    file_path: str
    code: str
    class_name: Optional[str] = None
    method_name: Optional[str] = None
    description: Optional[str] = None
    relevance_score: float = 0.0


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
        code_context: Optional code snippets for RAG enhancement.
        custom_context: Optional custom context data.
    """
    question: str
    retrieval_result: "RetrievalResult"
    db_name: Optional[str] = None
    
    # Extension points for future features
    few_shot_examples: List[FewShotExample] = field(default_factory=list)
    code_context: List[CodeSnippet] = field(default_factory=list)
    custom_context: Dict[str, Any] = field(default_factory=dict)


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
    metadata: Dict[str, Any] = field(default_factory=dict)


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
    sections: List[SectionContent] = field(default_factory=list)
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
