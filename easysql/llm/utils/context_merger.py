from __future__ import annotations

from typing import TYPE_CHECKING

from easysql.context.builder import ContextBuilder
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.llm.state import ContextOutputDict

logger = get_logger(__name__)


class ContextMerger:
    def __init__(self, builder: ContextBuilder | None = None):
        self._builder = builder

    @property
    def builder(self) -> ContextBuilder:
        if self._builder is None:
            self._builder = ContextBuilder.default()
        return self._builder

    def merge(
        self,
        old_context: ContextOutputDict | None,
        new_retrieval_result: dict,
    ) -> set[str]:
        if not old_context:
            return set(new_retrieval_result.get("tables", []))

        old_tables = self._extract_tables_from_context(old_context)
        new_tables = set(new_retrieval_result.get("tables", []))

        merged = old_tables | new_tables
        logger.info(
            f"Merged tables: {len(old_tables)} old + {len(new_tables)} new = {len(merged)} total"
        )

        return merged

    def _extract_tables_from_context(self, context: ContextOutputDict) -> set[str]:
        system_prompt = context.get("system_prompt", "")
        tables = set()

        for line in system_prompt.split("\n"):
            if line.startswith("表名:") or line.startswith("Table:"):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    table_name = parts[1].strip().split()[0]
                    tables.add(table_name)

        return tables


_default_merger: ContextMerger | None = None


def get_context_merger() -> ContextMerger:
    global _default_merger
    if _default_merger is None:
        _default_merger = ContextMerger()
    return _default_merger
