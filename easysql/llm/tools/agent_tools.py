"""
Agent Tools for SQL Agent Node.

Provides LangChain-compatible tools for the SQL Agent.
Uses local SQLAlchemy-based tools for database operations.
"""

from __future__ import annotations

import asyncio
import fnmatch
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool
from pydantic import Field

from easysql.llm.tools.executors.base import BaseSqlExecutor
from easysql.llm.tools.factory import create_sql_executor
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = get_logger(__name__)

# Global executor instance (lazy initialized)
_executor: BaseSqlExecutor | None = None


def _get_executor() -> BaseSqlExecutor:
    """Get or create the global SQL executor instance."""
    global _executor
    if _executor is None:
        _executor = create_sql_executor()
    return _executor


class ExecuteSqlTool(BaseTool):
    """Tool for validating SQL statements by executing them."""

    name: str = "validate_sql"
    description: str = (
        "Validate a SQL statement by executing it with LIMIT 1. "
        "Returns SUCCESS if the SQL is valid and can be executed, "
        "or ERROR with details if the SQL has syntax/semantic errors. "
        "Use this to verify your generated SQL before returning the final answer."
    )
    db_name: str = Field(default="default")

    def _run(self, sql: str) -> str:
        logger.info(f"[ValidateSqlTool] START - db={self.db_name}")
        logger.debug(f"[ValidateSqlTool] SQL:\n{sql}")

        # Auto-add LIMIT 1 for validation if not present
        sql_upper = sql.upper().strip()
        if "LIMIT" not in sql_upper and sql_upper.startswith("SELECT"):
            sql_to_run = sql.rstrip(";").strip() + " LIMIT 1"
        else:
            sql_to_run = sql

        executor = _get_executor()
        result = executor.execute_sql(sql_to_run, self.db_name)

        if result.success:
            logger.info("[ValidateSqlTool] SUCCESS - SQL is valid")
            return "SUCCESS: SQL is valid and can be executed."

        logger.warning(f"[ValidateSqlTool] ERROR - {result.error}")
        return f"ERROR: {result.error}"

    async def _arun(self, sql: str) -> str:
        return await asyncio.to_thread(self._run, sql)


class SearchObjectsTool(BaseTool):
    """Tool for searching database objects."""

    name: str = "search_objects"
    description: str = (
        "Search database objects using pattern matching. "
        "object_type: 'table', 'column', or 'index'. "
        "pattern: SQL LIKE pattern (e.g., 'user%' matches user, users, user_profile). "
        "detail_level: 'names' (minimal), 'summary', or 'full' (with columns)."
    )
    db_name: str = Field(default="default")

    def _run(
        self,
        object_type: str,
        pattern: str = "%",
        detail_level: str = "names",
    ) -> str:
        logger.info(
            f"[SearchObjectsTool] START - type={object_type}, pattern={pattern}, "
            f"detail={detail_level}, db={self.db_name}"
        )
        try:
            from sqlalchemy import inspect

            executor = _get_executor()
            if not hasattr(executor, "_get_engine"):
                logger.warning("[SearchObjectsTool] ERROR - requires SQLAlchemy executor")
                return "ERROR: search_objects requires SQLAlchemy executor"

            engine: Engine = executor._get_engine(self.db_name)
            insp = inspect(engine)
            result = self._search_with_inspector(insp, object_type, pattern, detail_level)
            logger.info(f"[SearchObjectsTool] SUCCESS - result_length={len(result)}")
            logger.debug(f"[SearchObjectsTool] Result:\n{result[:500]}...")
            return result
        except Exception as e:
            logger.error(f"[SearchObjectsTool] FAILED - {e}")
            return f"ERROR: {e}"

    async def _arun(
        self,
        object_type: str,
        pattern: str = "%",
        detail_level: str = "names",
    ) -> str:
        return await asyncio.to_thread(self._run, object_type, pattern, detail_level)

    def _search_with_inspector(
        self,
        insp: Any,
        object_type: str,
        pattern: str,
        detail_level: str,
    ) -> str:
        pattern_glob = pattern.replace("%", "*").replace("_", "?")

        if object_type == "table":
            return self._search_tables(insp, pattern_glob, detail_level)
        elif object_type == "column":
            return self._search_columns(insp, pattern_glob)
        elif object_type == "index":
            return self._search_indexes(insp, pattern_glob)
        return f"ERROR: Unsupported object_type: {object_type}"

    def _search_tables(self, insp: Any, pattern_glob: str, detail_level: str) -> str:
        tables = insp.get_table_names()
        matched = [t for t in tables if fnmatch.fnmatch(t.lower(), pattern_glob.lower())]

        if detail_level == "names":
            return f"Found {len(matched)} tables: {matched[:20]}"
        elif detail_level == "summary":
            result = []
            for t in matched[:10]:
                cols = insp.get_columns(t)
                pks = insp.get_pk_constraint(t).get("constrained_columns", [])
                result.append(f"{t}: {len(cols)} columns, PK: {pks}")
            return "\n".join(result)
        else:
            result = []
            for t in matched[:5]:
                cols = insp.get_columns(t)
                col_info = [f"  - {c['name']}: {c['type']}" for c in cols]
                result.append(f"{t}:\n" + "\n".join(col_info))
            return "\n\n".join(result)

    def _search_columns(self, insp: Any, pattern_glob: str) -> str:
        all_cols = []
        for table in insp.get_table_names()[:50]:
            cols = insp.get_columns(table)
            for col in cols:
                if fnmatch.fnmatch(col["name"].lower(), pattern_glob.lower()):
                    all_cols.append(f"{table}.{col['name']}: {col['type']}")
        return f"Found {len(all_cols)} columns:\n" + "\n".join(all_cols[:30])

    def _search_indexes(self, insp: Any, pattern_glob: str) -> str:
        all_indexes = []
        for table in insp.get_table_names()[:50]:
            indexes = insp.get_indexes(table)
            for idx in indexes:
                if fnmatch.fnmatch(idx["name"].lower(), pattern_glob.lower()):
                    all_indexes.append(f"{table}.{idx['name']}: {idx['column_names']}")
        return f"Found {len(all_indexes)} indexes:\n" + "\n".join(all_indexes[:30])


def create_agent_tools(db_name: str) -> list[BaseTool]:
    """Create SQL Agent tools for the specified database.

    Args:
        db_name: Target database name

    Returns:
        List of LangChain BaseTool instances
    """
    return [
        ExecuteSqlTool(db_name=db_name),
        SearchObjectsTool(db_name=db_name),
    ]


def get_agent_tools(db_name: str) -> list[BaseTool]:
    """Get tools for the SQL Agent.

    Args:
        db_name: Target database name

    Returns:
        List of LangChain BaseTool instances
    """
    logger.info(f"Creating SQLAlchemy tools for db={db_name}")
    return create_agent_tools(db_name)
