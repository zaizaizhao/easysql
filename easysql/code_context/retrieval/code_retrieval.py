"""Simplified code retrieval service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.code_context.storage.milvus_reader import CodeMilvusReader

logger = get_logger(__name__)


@dataclass
class CodeRetrievalConfig:
    top_k: int = 5
    score_threshold: float = 0.3
    max_snippets: int = 3


@dataclass
class CodeRetrievalResult:
    snippets: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def format_for_context(self) -> str:
        if not self.snippets:
            return ""

        lines = ["## 相关代码参考", ""]

        for i, snippet in enumerate(self.snippets, 1):
            file_path = snippet.get("file_path", "unknown")
            language = snippet.get("language", "")
            content = snippet.get("content", "")

            file_name = Path(file_path).name
            lines.append(f"### {file_name}")
            lines.append(f"**路径**: {file_path}")
            lines.append(f"```{language}")
            lines.append(content)
            lines.append("```")
            lines.append("")

        return "\n".join(lines)


class CodeRetrievalService:
    def __init__(
        self,
        milvus_reader: "CodeMilvusReader",
        config: CodeRetrievalConfig | None = None,
    ):
        self._reader = milvus_reader
        self._config = config or CodeRetrievalConfig()

    def retrieve(
        self,
        question: str,
        relevant_tables: list[str] | None = None,
    ) -> CodeRetrievalResult:
        results = self._reader.search_with_tables(
            query=question,
            table_names=relevant_tables,
            top_k=self._config.top_k,
            score_threshold=self._config.score_threshold,
        )

        snippets = results[: self._config.max_snippets]

        return CodeRetrievalResult(
            snippets=snippets,
            stats={
                "question": question[:100],
                "table_filter": relevant_tables,
                "total_found": len(results),
                "returned": len(snippets),
            },
        )

    def retrieve_formatted(
        self,
        question: str,
        relevant_tables: list[str] | None = None,
    ) -> str:
        result = self.retrieve(question, relevant_tables)
        return result.format_for_context()
