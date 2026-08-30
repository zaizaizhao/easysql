"""Read-only FastAPI adapter for external agentic schema retrieval."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from easysql.agent_tools import (
    DatabaseNotConfiguredError,
    SchemaToolService,
    get_schema_tool_service,
)
from easysql.utils.logger import get_logger
from easysql_api.models.agent_tools import (
    AgentToolErrorResponse,
    ColumnSearchRequest,
    ColumnSearchResponse,
    DatabaseScopeResponse,
    JoinPathRequest,
    JoinPathResponse,
    RelatedTableExpansionRequest,
    RelatedTableExpansionResponse,
    TableSchemaRequest,
    TableSchemaResponse,
    TableSearchRequest,
    TableSearchResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/agent-tools")

ServiceDependency = Annotated[SchemaToolService, Depends(get_schema_tool_service)]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": AgentToolErrorResponse, "description": "Logical database is not configured"},
    503: {"model": AgentToolErrorResponse, "description": "Retrieval backend is unavailable"},
}


def _run_tool(operation: str, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = call()
    except DatabaseNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DATABASE_NOT_CONFIGURED",
                "message": str(exc),
            },
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_AGENT_TOOL_INPUT",
                "message": str(exc),
            },
        ) from None
    except Exception:  # noqa: BLE001 - normalize backend errors for an external agent
        logger.exception("Agent schema tool failed: {}", operation)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "RETRIEVAL_BACKEND_UNAVAILABLE",
                "message": f"{operation} could not reach the schema retrieval backend",
            },
        ) from None

    result["elapsed_ms"] = round((time.perf_counter() - started) * 1_000, 2)
    return result


@router.get("/databases", response_model=DatabaseScopeResponse)
def describe_database_scope(service: ServiceDependency) -> dict[str, Any]:
    """List credential-free logical databases available to retrieval tools."""
    return service.describe_database_scope()


@router.post(
    "/search-tables",
    response_model=TableSearchResponse,
    responses=ERROR_RESPONSES,
)
def search_tables(request: TableSearchRequest, service: ServiceDependency) -> dict[str, Any]:
    """Run one database-scoped Milvus table search."""
    return _run_tool(
        "search_tables",
        lambda: service.search_tables(
            db_name=request.db_name,
            query=request.query,
            top_k=request.top_k,
            table_names=request.table_names,
        ),
    )


@router.post(
    "/search-columns",
    response_model=ColumnSearchResponse,
    responses=ERROR_RESPONSES,
)
def search_columns(request: ColumnSearchRequest, service: ServiceDependency) -> dict[str, Any]:
    """Run one database-scoped Milvus column search."""
    return _run_tool(
        "search_columns",
        lambda: service.search_columns(
            db_name=request.db_name,
            query=request.query,
            top_k=request.top_k,
            table_names=request.table_names,
        ),
    )


@router.post(
    "/table-schema",
    response_model=TableSchemaResponse,
    responses=ERROR_RESPONSES,
)
def get_table_schema(request: TableSchemaRequest, service: ServiceDependency) -> dict[str, Any]:
    """Read exact columns and key flags for a bounded set of Neo4j tables."""
    return _run_tool(
        "get_table_schema",
        lambda: service.get_table_schema(
            db_name=request.db_name,
            table_names=request.table_names,
        ),
    )


@router.post(
    "/expand-tables",
    response_model=RelatedTableExpansionResponse,
    responses=ERROR_RESPONSES,
)
def expand_related_tables(
    request: RelatedTableExpansionRequest,
    service: ServiceDependency,
) -> dict[str, Any]:
    """Expand selected seed tables by at most two Neo4j FK hops."""
    return _run_tool(
        "expand_related_tables",
        lambda: service.expand_related_tables(
            db_name=request.db_name,
            seed_tables=request.seed_tables,
            max_depth=request.max_depth,
        ),
    )


@router.post(
    "/join-paths",
    response_model=JoinPathResponse,
    responses=ERROR_RESPONSES,
)
def find_join_paths(request: JoinPathRequest, service: ServiceDependency) -> dict[str, Any]:
    """Return directional FK edges connecting a bounded set of Neo4j tables."""
    return _run_tool(
        "find_join_paths",
        lambda: service.find_join_paths(
            db_name=request.db_name,
            table_names=request.table_names,
            max_hops=request.max_hops,
        ),
    )
