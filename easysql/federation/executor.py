"""Execute single-database SQL and PostgreSQL dblink SQL through one interface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from easysql.config import get_settings
from easysql.federation.dblink import DblinkSessionManager
from easysql.federation.scope import DatabaseScope
from easysql.infrastructure import get_data_plane_engine_registry
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.config import Settings

logger = get_logger(__name__)

_DBLINK_CALL_PATTERN = re.compile(
    r"\bdblink\s*\(\s*'((?:''|[^'])*)'\s*,",
    re.IGNORECASE,
)
_ANY_DBLINK_PATTERN = re.compile(r"\bdblink\s*\(", re.IGNORECASE)
_FORBIDDEN_DBLINK_FUNCTIONS = re.compile(
    r"\bdblink_(?:connect|disconnect|exec|send_query|cancel_query|open|close)\s*\(",
    re.IGNORECASE,
)
_MUTATION_KEYWORDS = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|CALL|DO|COPY)\b",
    re.IGNORECASE,
)
_DOLLAR_TAG_PATTERN = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _mask_sql_literals_and_comments(sql: str) -> str:
    """Mask non-code text while keeping dollar-quoted remote SQL inspectable.

    PostgreSQL dblink SQL is commonly wrapped in ``$$...$$``. The delimiters
    themselves are masked, but their contents remain code so mutations inside a
    remote query are still rejected. Ordinary quoted values such as
    ``'%revoke%'`` are masked and cannot trigger keyword checks.
    """
    masked = list(sql)
    index = 0

    def mask(start: int, end: int) -> None:
        for position in range(start, end):
            if masked[position] not in {"\n", "\r"}:
                masked[position] = " "

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if char == "-" and next_char == "-":
            end = sql.find("\n", index + 2)
            end = len(sql) if end == -1 else end
            mask(index, end)
            index = end
            continue

        if char == "/" and next_char == "*":
            closing = sql.find("*/", index + 2)
            end = len(sql) if closing == -1 else closing + 2
            mask(index, end)
            index = end
            continue

        if char in {"'", '"'}:
            quote = char
            start = index
            index += 1
            while index < len(sql):
                if sql[index] == quote and index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 2
                    continue
                if sql[index] == quote:
                    index += 1
                    break
                index += 1
            mask(start, index)
            continue

        if char == "$":
            tag = _DOLLAR_TAG_PATTERN.match(sql, index)
            if tag:
                mask(index, tag.end())
                index = tag.end()
                continue

        index += 1

    return "".join(masked)


def _normal_semicolon_positions(sql: str) -> list[int]:
    """Find statement separators while ignoring SQL strings/comments/dollar quotes."""
    positions: list[int] = []
    index = 0
    state = "normal"
    dollar_tag = ""
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if state == "line_comment":
            if char == "\n":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and next_char == "/":
                state = "normal"
                index += 2
            else:
                index += 1
            continue
        if state == "single_quote":
            if char == "'" and next_char == "'":
                index += 2
            elif char == "'":
                state = "normal"
                index += 1
            else:
                index += 1
            continue
        if state == "double_quote":
            if char == '"' and next_char == '"':
                index += 2
            elif char == '"':
                state = "normal"
                index += 1
            else:
                index += 1
            continue
        if state == "dollar_quote":
            if sql.startswith(dollar_tag, index):
                state = "normal"
                index += len(dollar_tag)
            else:
                index += 1
            continue

        if char == "-" and next_char == "-":
            state = "line_comment"
            index += 2
        elif char == "/" and next_char == "*":
            state = "block_comment"
            index += 2
        elif char == "'":
            state = "single_quote"
            index += 1
        elif char == '"':
            state = "double_quote"
            index += 1
        elif char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if match:
                dollar_tag = match.group(0)
                state = "dollar_quote"
                index += len(dollar_tag)
            else:
                index += 1
        elif char == ";":
            positions.append(index)
            index += 1
        else:
            index += 1

    return positions


def _has_multiple_statements(sql: str) -> bool:
    separators = _normal_semicolon_positions(sql)
    if not separators:
        return False
    if len(separators) > 1:
        return True
    tail = sql[separators[0] + 1 :]
    tail = re.sub(r"--[^\n]*(?:\n|$)", "", tail)
    tail = re.sub(r"/\*.*?\*/", "", tail, flags=re.DOTALL)
    return bool(tail.strip())


@dataclass(frozen=True)
class FederatedSqlRequest:
    sql: str
    primary_db: str
    db_names: tuple[str, ...]
    timeout_seconds: int = 30


@dataclass
class FederatedExecutionResult:
    """Execution outcome intentionally independent of the legacy LLM tool package."""

    success: bool
    data: list[dict[str, Any]] | None = None
    columns: list[str] | None = None
    error: str | None = None
    row_count: int = 0


class FederatedSqlExecutor:
    """Hide scope validation, dblink lifecycle and engine selection from callers."""

    def __init__(
        self,
        settings: Settings | None = None,
        registry: Any | None = None,
        dblink_manager: DblinkSessionManager | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry or get_data_plane_engine_registry()
        self._dblink_manager = dblink_manager or DblinkSessionManager()

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    def execute(self, request: FederatedSqlRequest) -> FederatedExecutionResult:
        return self._run(request, explain=False)

    def validate(self, request: FederatedSqlRequest) -> FederatedExecutionResult:
        """Validate with plain EXPLAIN; never use EXPLAIN ANALYZE."""
        return self._run(request, explain=True)

    def _run(
        self,
        request: FederatedSqlRequest,
        *,
        explain: bool,
    ) -> FederatedExecutionResult:
        try:
            scope = DatabaseScope.resolve(
                self.settings,
                db_names=list(request.db_names),
            )
            primary = scope.require_primary(request.primary_db)
            referenced_connections = self._validate_sql(request.sql, scope, primary.name)
            engine = self._registry.get_engine(primary.config)

            with engine.connect() as connection:
                connected_names: set[str] = set()
                try:
                    if primary.config.db_type == "postgresql":
                        self._set_timeout(connection, request.timeout_seconds)
                    if scope.is_federated and referenced_connections:
                        for connection_name in sorted(referenced_connections):
                            target = scope.target_for_connection(connection_name)
                            if target is None or target.name == primary.name:
                                raise ValueError(
                                    f"No selected remote database maps to '{connection_name}'"
                                )
                            self._dblink_manager.connect(
                                connection,
                                source=primary,
                                target=target,
                                connection_name=connection_name,
                                statement_timeout_seconds=request.timeout_seconds,
                            )
                            connected_names.add(connection_name)

                    sql = f"EXPLAIN {request.sql}" if explain else request.sql
                    result = connection.execute(text(sql))
                    if result.returns_rows:
                        rows = [dict(row._mapping) for row in result]
                        return FederatedExecutionResult(
                            success=True,
                            data=rows,
                            columns=list(result.keys()),
                            row_count=len(rows),
                        )
                    return FederatedExecutionResult(success=True, row_count=result.rowcount)
                finally:
                    if connected_names:
                        self._dblink_manager.disconnect_many(connection, connected_names)
        except Exception as exc:  # noqa: BLE001 - normalized for agent/API consumers
            logger.error(
                "Federated SQL {} failed on {}: {}",
                "validation" if explain else "execution",
                request.primary_db,
                exc,
            )
            return FederatedExecutionResult(success=False, error=str(exc))

    @staticmethod
    def _set_timeout(connection: Any, timeout_seconds: int) -> None:
        timeout_ms = max(1, int(timeout_seconds)) * 1000
        connection.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": f"{timeout_ms}ms"},
        )

    @staticmethod
    def _validate_sql(
        sql: str,
        scope: DatabaseScope,
        primary_db: str,
    ) -> set[str]:
        normalized = sql.strip()
        if not normalized:
            raise ValueError("SQL must not be empty")

        if _has_multiple_statements(normalized):
            raise ValueError("Only one SQL statement may be executed")

        code_only = _mask_sql_literals_and_comments(normalized)

        if _FORBIDDEN_DBLINK_FUNCTIONS.search(code_only):
            raise ValueError("SQL may use dblink() only; connection management is executor-owned")

        raw_connections = {
            value.replace("''", "'") for value in _DBLINK_CALL_PATTERN.findall(normalized)
        }
        if _ANY_DBLINK_PATTERN.search(code_only) and not raw_connections:
            raise ValueError("Every dblink() call must use a configured literal connection name")

        if not scope.is_federated and raw_connections:
            raise ValueError("dblink is available only when multiple databases are selected")

        allowed = {
            target.dblink_connection_name for target in scope.targets if target.name != primary_db
        }
        unknown = sorted(raw_connections - allowed)
        if unknown:
            raise ValueError(
                "SQL references dblink connection(s) outside the selected remote databases: "
                + ", ".join(unknown)
            )

        if scope.is_federated:
            first_word = code_only.lstrip("(").split(None, 1)[0].upper()
            if first_word not in {"SELECT", "WITH", "EXPLAIN"}:
                raise ValueError("Multi-database dblink execution is read-only")
            if _MUTATION_KEYWORDS.search(code_only):
                raise ValueError("Multi-database dblink execution is read-only")

        return raw_connections
