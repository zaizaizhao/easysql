from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from easysql.config import Settings
from easysql_api.deps import get_config_service_dep, get_settings_dep
from easysql_api.models.database import (
    DatabaseConfigInput,
    DatabaseConfigListResponse,
    DatabaseConfigUpdateRequest,
    DatabaseConfigUpdateResponse,
    DatabaseConfigView,
    DatabaseConnectionTestResponse,
    DatabaseFederationStatusRequest,
    DatabaseFederationStatusResponse,
)
from easysql_api.services.config_service import ConfigService

router = APIRouter()

# Fixed in code since the config refactoring (no longer a Settings field).
CODE_CONTEXT_SUPPORTED_LANGUAGES = ["csharp", "python", "java", "javascript", "typescript"]


class LLMConfigResponse(BaseModel):
    query_mode: str
    provider: str
    model: str
    planning_model: str | None
    temperature: float
    use_agent_mode: bool
    agent_max_iterations: int
    agent_timeout_seconds: int
    query_timeout_seconds: int
    max_sql_retries: int


class RetrievalConfigResponse(BaseModel):
    search_top_k: int
    expand_fk: bool
    expand_max_depth: int
    semantic_filter_enabled: bool
    semantic_filter_threshold: float
    semantic_filter_min_tables: int
    bridge_protection_enabled: bool
    core_tables: list[str]
    llm_filter_enabled: bool
    llm_filter_max_tables: int


class EmbeddingConfigResponse(BaseModel):
    provider: str
    model: str
    dimension: int


class StorageConfigResponse(BaseModel):
    neo4j_uri: str
    neo4j_database: str
    milvus_uri: str
    project_namespace: str


class CodeContextConfigResponse(BaseModel):
    enabled: bool
    search_top_k: int
    score_threshold: float
    max_snippets: int
    supported_languages: list[str]


class ConfigResponse(BaseModel):
    llm: LLMConfigResponse
    retrieval: RetrievalConfigResponse
    embedding: EmbeddingConfigResponse
    storage: StorageConfigResponse
    code_context: CodeContextConfigResponse
    log_level: str


@router.get("/config", response_model=ConfigResponse)
async def get_config(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ConfigResponse:
    return ConfigResponse(
        llm=LLMConfigResponse(
            query_mode=settings.llm.query_mode,
            provider=settings.llm.get_provider(),
            model=settings.llm.get_model(),
            planning_model=settings.llm.model_planning,
            temperature=settings.llm.temperature,
            use_agent_mode=settings.llm.use_agent_mode,
            agent_max_iterations=settings.llm.agent_max_iterations,
            agent_timeout_seconds=settings.llm.agent_timeout_seconds,
            query_timeout_seconds=settings.llm.query_timeout_seconds,
            max_sql_retries=settings.llm.max_sql_retries,
        ),
        retrieval=RetrievalConfigResponse(
            search_top_k=settings.retrieval_search_top_k,
            expand_fk=settings.retrieval_expand_fk,
            expand_max_depth=settings.retrieval_expand_max_depth,
            semantic_filter_enabled=settings.semantic_filter_enabled,
            semantic_filter_threshold=settings.semantic_filter_threshold,
            semantic_filter_min_tables=settings.semantic_filter_min_tables,
            bridge_protection_enabled=settings.bridge_protection_enabled,
            core_tables=settings.core_tables_list,
            llm_filter_enabled=settings.llm_filter_enabled,
            llm_filter_max_tables=settings.llm_filter_max_tables,
        ),
        embedding=EmbeddingConfigResponse(
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        ),
        storage=StorageConfigResponse(
            neo4j_uri=settings.neo4j_uri,
            neo4j_database=settings.neo4j_database,
            milvus_uri=settings.milvus_uri,
            project_namespace=settings.project_namespace,
        ),
        code_context=CodeContextConfigResponse(
            enabled=settings.code_context_enabled,
            search_top_k=settings.code_context_search_top_k,
            score_threshold=settings.code_context_score_threshold,
            max_snippets=settings.code_context_max_snippets,
            supported_languages=CODE_CONTEXT_SUPPORTED_LANGUAGES,
        ),
        log_level=settings.log_level,
    )


@router.get("/config/databases", response_model=DatabaseConfigListResponse)
async def get_database_configs(
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
) -> DatabaseConfigListResponse:
    databases = await service.get_database_configs()
    return DatabaseConfigListResponse(
        databases=[DatabaseConfigView(**item) for item in databases],
        total=len(databases),
    )


@router.post(
    "/config/databases/federation-status",
    response_model=DatabaseFederationStatusResponse,
)
async def get_database_federation_status(
    request: DatabaseFederationStatusRequest,
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
) -> DatabaseFederationStatusResponse:
    try:
        result = await service.get_database_federation_status(request.db_names)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DatabaseFederationStatusResponse(**result)


@router.put("/config/databases", response_model=DatabaseConfigUpdateResponse)
async def replace_database_configs(
    request: DatabaseConfigUpdateRequest,
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
    warmup: bool = False,
) -> DatabaseConfigUpdateResponse:
    try:
        result = await service.replace_database_configs(
            [item.model_dump() for item in request.databases],
            warmup=warmup,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DatabaseConfigUpdateResponse(**result)


@router.delete("/config/databases/{name}", response_model=DatabaseConfigUpdateResponse)
async def delete_database_config(
    name: str,
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
    warmup: bool = False,
) -> DatabaseConfigUpdateResponse:
    try:
        result = await service.delete_database_config(name, warmup=warmup)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DatabaseConfigUpdateResponse(**result)


@router.post("/config/databases/test", response_model=DatabaseConnectionTestResponse)
async def test_database_config(
    request: DatabaseConfigInput,
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
) -> DatabaseConnectionTestResponse:
    try:
        message = await service.test_database_config(request.model_dump())
        return DatabaseConnectionTestResponse(success=True, message=message)
    except Exception as exc:  # noqa: BLE001 - connection errors are returned to the settings UI
        return DatabaseConnectionTestResponse(
            success=False,
            message=f"{type(exc).__name__}: {exc}",
        )


class ConfigUpdateResponse(BaseModel):
    category: str
    updated: list[str]
    invalidate_tags: list[str]


class ConfigDeleteResponse(BaseModel):
    category: str
    deleted: int
    message: str
    invalidate_tags: list[str]


@router.get("/config/editable")
async def get_editable_config(
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
) -> dict[str, dict[str, dict[str, Any]]]:
    return await service.get_editable_config()


@router.get("/config/overrides")
async def get_config_overrides(
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
) -> dict[str, dict[str, dict[str, Any]]]:
    return await service.get_overrides()


@router.api_route(
    "/config/{category}",
    methods=["PUT", "PATCH"],
    response_model=ConfigUpdateResponse,
)
async def update_config_category(
    category: str,
    updates: dict[str, Any],
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
    warmup: bool = True,
) -> ConfigUpdateResponse:
    try:
        result = await service.update_category(category, updates, warmup=warmup)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ConfigUpdateResponse(**result)


@router.delete("/config/{category}", response_model=ConfigDeleteResponse)
async def delete_config_category(
    category: str,
    service: Annotated[ConfigService, Depends(get_config_service_dep)],
    warmup: bool = True,
) -> ConfigDeleteResponse:
    try:
        result = await service.delete_category(category, warmup=warmup)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ConfigDeleteResponse(**result)
