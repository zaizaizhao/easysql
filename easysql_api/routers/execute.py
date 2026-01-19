"""
SQL Execution Router.

Standalone endpoint for executing SQL queries, decoupled from the agent workflow.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from easysql_api.deps import get_execute_service_dep
from easysql_api.models.execute import (
    ExecuteRequest,
    ExecuteResponse,
    SqlCheckResult,
)
from easysql_api.services.execute_service import ExecuteService

router = APIRouter()


@router.post("/execute", response_model=ExecuteResponse)
async def execute_sql(
    request: ExecuteRequest,
    service: Annotated[ExecuteService, Depends(get_execute_service_dep)],
) -> ExecuteResponse:
    return service.execute(request)


@router.post("/execute/check", response_model=SqlCheckResult)
async def check_sql(
    request: ExecuteRequest,
    service: Annotated[ExecuteService, Depends(get_execute_service_dep)],
) -> SqlCheckResult:
    return service.check_sql(request.sql)
