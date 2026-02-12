from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from easysql.config import Settings
from easysql_api.deps import get_config_service_dep, get_settings_dep
from easysql_api.services.config_service import ConfigService

router = APIRouter()


class LLMConfigResponse(BaseModel):
    query_mode: str
    provider: str
    model: str
    planning_model: str | None
    temperature: float
    max_sql_retries: int


class RetrievalConfigResponse(BaseModel):
    search_top_k: int
    expand_fk: bool
    expand_max_depth: int
    semantic_filter_enabled: bool
    semantic_filter_threshold: float
    semantic_filter_min_tables: int
    bridge_protection_enabled: bool
    bridge_max_hops: int
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
    milvus_collection_prefix: str


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
            bridge_max_hops=settings.bridge_max_hops,
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
            milvus_collection_prefix=settings.milvus_collection_prefix,
        ),
        code_context=CodeContextConfigResponse(
            enabled=settings.code_context_enabled,
            search_top_k=settings.code_context_search_top_k,
            score_threshold=settings.code_context_score_threshold,
            max_snippets=settings.code_context_max_snippets,
            supported_languages=settings.code_context_languages_list,
        ),
        log_level=settings.log_level,
    )


@router.get("/config/databases")
async def get_database_configs(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict:
    databases = {}
    for name, config in settings.databases.items():
        databases[name] = {
            "name": config.name,
            "type": config.db_type,
            "host": config.host,
            "port": config.port,
            "database": config.database,
            "schema": config.get_default_schema(),
            "system_type": config.system_type,
            "description": config.description,
        }

    return {"databases": databases}


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
