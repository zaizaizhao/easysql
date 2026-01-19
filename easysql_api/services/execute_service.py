"""
SQL Execution Service.

Provides standalone SQL execution with safety checks, timeout handling,
and result limiting. Decoupled from the Text2SQL agent workflow.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from easysql.config import get_settings
from easysql.llm.tools.base import BaseSqlExecutor, ExecutionResult
from easysql.llm.tools.factory import create_sql_executor
from easysql.utils.logger import get_logger
from easysql_api.models.execute import (
    ExecuteRequest,
    ExecuteResponse,
    ExecuteStatus,
    SqlCheckResult,
)

logger = get_logger(__name__)

MUTATION_PATTERNS = [
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bDELETE\s+FROM\b",
    r"\bTRUNCATE\s+",
    r"\bDROP\s+",
    r"\bALTER\s+",
    r"\bCREATE\s+",
    r"\bGRANT\s+",
    r"\bREVOKE\s+",
]

DANGEROUS_PATTERNS = [
    (r"\bDROP\s+DATABASE\b", "DROP DATABASE detected"),
    (r"\bDROP\s+TABLE\b", "DROP TABLE detected"),
    (r"\bTRUNCATE\s+TABLE\b", "TRUNCATE TABLE detected"),
    (r"\bDELETE\s+FROM\s+\w+\s*(?:;|$)", "DELETE without WHERE clause"),
    (
        r"\bUPDATE\s+\w+\s+SET\s+.*(?:WHERE\s+1\s*=\s*1|WHERE\s+TRUE)",
        "UPDATE with always-true WHERE",
    ),
]


class ExecuteService:
    """Service for executing SQL queries with safety controls."""

    def __init__(self, executor: BaseSqlExecutor | None = None) -> None:
        self._executor = executor
        self._thread_pool = ThreadPoolExecutor(max_workers=4)

    @property
    def executor(self) -> BaseSqlExecutor:
        if self._executor is None:
            self._executor = create_sql_executor()
        return self._executor

    def check_sql(self, sql: str) -> SqlCheckResult:
        """Analyze SQL for safety and classify statement type."""
        normalized = sql.strip().upper()
        warnings: list[str] = []

        is_mutation = any(re.search(p, normalized, re.IGNORECASE) for p in MUTATION_PATTERNS)

        for pattern, warning_msg in DANGEROUS_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                warnings.append(warning_msg)

        if normalized.startswith("SELECT"):
            statement_type = "SELECT"
        elif normalized.startswith("INSERT"):
            statement_type = "INSERT"
        elif normalized.startswith("UPDATE"):
            statement_type = "UPDATE"
        elif normalized.startswith("DELETE"):
            statement_type = "DELETE"
        elif normalized.startswith("CREATE"):
            statement_type = "CREATE"
        elif normalized.startswith("DROP"):
            statement_type = "DROP"
        elif normalized.startswith("ALTER"):
            statement_type = "ALTER"
        else:
            statement_type = "OTHER"

        safe = len(warnings) == 0

        return SqlCheckResult(
            safe=safe,
            is_mutation=is_mutation,
            statement_type=statement_type,
            warnings=warnings,
        )

    def _apply_limit(self, sql: str, limit: int) -> str:
        """Apply LIMIT clause if not already present (for SELECT queries)."""
        normalized = sql.strip().upper()
        if not normalized.startswith("SELECT"):
            return sql

        if re.search(r"\bLIMIT\s+\d+", normalized, re.IGNORECASE):
            return sql

        sql_stripped = sql.rstrip().rstrip(";")
        return f"{sql_stripped} LIMIT {limit}"

    def _execute_with_timeout(
        self, sql: str, db_name: str, timeout: int
    ) -> tuple[ExecutionResult, float]:
        """Execute SQL with timeout control. Returns (result, execution_time_ms)."""
        start_time = time.perf_counter()

        future = self._thread_pool.submit(self.executor.execute_sql, sql, db_name)

        try:
            result = future.result(timeout=timeout)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return result, elapsed_ms
        except FuturesTimeoutError:
            future.cancel()
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                success=False, error=f"Query timeout after {timeout}s"
            ), elapsed_ms

    def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        """Execute SQL query with all safety checks and controls."""
        settings = get_settings()
        db_config = settings.databases.get(request.db_name.lower())
        if not db_config:
            return ExecuteResponse(
                status=ExecuteStatus.FAILED,
                error=f"Database '{request.db_name}' not configured",
            )

        check_result = self.check_sql(request.sql)

        if check_result.is_mutation and not request.allow_mutation:
            return ExecuteResponse(
                status=ExecuteStatus.FORBIDDEN,
                error=f"Mutation statement ({check_result.statement_type}) not allowed. "
                "Set allow_mutation=true to enable.",
            )

        if check_result.warnings:
            logger.warning(f"SQL safety warnings for {request.db_name}: {check_result.warnings}")
            if not request.allow_mutation:
                return ExecuteResponse(
                    status=ExecuteStatus.FORBIDDEN,
                    error=f"Dangerous SQL detected: {', '.join(check_result.warnings)}",
                )

        sql_to_execute = request.sql
        if check_result.statement_type == "SELECT":
            sql_to_execute = self._apply_limit(request.sql, request.limit + 1)

        try:
            result, execution_time_ms = self._execute_with_timeout(
                sql_to_execute, request.db_name, request.timeout
            )
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return ExecuteResponse(
                status=ExecuteStatus.FAILED,
                error=str(e),
            )

        if not result.success:
            status = (
                ExecuteStatus.TIMEOUT
                if "timeout" in (result.error or "").lower()
                else ExecuteStatus.FAILED
            )
            return ExecuteResponse(
                status=status,
                error=result.error,
                execution_time_ms=execution_time_ms,
            )

        data = result.data or []
        truncated = len(data) > request.limit
        if truncated:
            data = data[: request.limit]

        return ExecuteResponse(
            status=ExecuteStatus.SUCCESS,
            data=data,
            columns=result.columns,
            row_count=len(data),
            affected_rows=result.row_count if check_result.is_mutation else None,
            execution_time_ms=round(execution_time_ms, 2),
            truncated=truncated,
        )


_default_service: ExecuteService | None = None


def get_execute_service() -> ExecuteService:
    global _default_service
    if _default_service is None:
        _default_service = ExecuteService()
    return _default_service
