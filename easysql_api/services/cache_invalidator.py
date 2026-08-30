"""Cache invalidation and optional warmup for runtime config updates."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable

from easysql.config import get_settings
from easysql.infrastructure import get_data_plane_engine_registry
from easysql.retrieval.runtime import (
    get_retrieval_runtime,
    reset_retrieval_runtime,
    warm_retrieval_runtime,
)
from easysql.utils.logger import get_logger
from easysql_api.services.chart_service import (
    reset_chart_service_callbacks,
    warm_chart_service_callbacks,
)
from easysql_api.services.query_service import (
    reset_query_service_callbacks,
    reset_query_service_graph,
    warm_query_service_callbacks,
    warm_query_service_graph,
)

logger = get_logger(__name__)

LANGFUSE_ENV_KEYS = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_HOST",
)

RETRIEVAL_CACHE_TAGS = {
    "retrieval_cache",
    "few_shot_cache",
    "code_context_cache",
}


def _warm_few_shot_reader() -> None:
    _ = get_retrieval_runtime().few_shot_reader


def _warm_code_retrieval() -> None:
    _ = get_retrieval_runtime().code_retrieval


class CacheInvalidator:
    """Invalidate caches touched by runtime config changes."""

    def invalidate(self, tags: Iterable[str]) -> None:
        tag_set = set(tags)
        get_settings.cache_clear()

        if "graph" in tag_set:
            reset_query_service_graph()

        if "callbacks" in tag_set:
            reset_query_service_callbacks()
            reset_chart_service_callbacks()

        if "langfuse_env" in tag_set:
            for key in LANGFUSE_ENV_KEYS:
                os.environ.pop(key, None)

        if tag_set & RETRIEVAL_CACHE_TAGS:
            reset_retrieval_runtime()

        if "data_plane_engines" in tag_set:
            get_data_plane_engine_registry().dispose_all()

    def warmup(self, tags: Iterable[str]) -> None:
        tag_set = set(tags)

        if "graph" in tag_set:
            self._safe_warm(warm_query_service_graph, "query graph")

        if "callbacks" in tag_set:
            self._safe_warm(warm_query_service_callbacks, "query callbacks")
            self._safe_warm(warm_chart_service_callbacks, "chart callbacks")

        if tag_set & RETRIEVAL_CACHE_TAGS:
            self._safe_warm(warm_retrieval_runtime, "retrieval runtime")

        if "few_shot_cache" in tag_set:
            self._safe_warm(_warm_few_shot_reader, "few-shot reader")

        if "code_context_cache" in tag_set:
            self._safe_warm(_warm_code_retrieval, "code retrieval service")

    @staticmethod
    def _safe_warm(func: Callable[[], None], name: str) -> None:
        try:
            func()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Cache warmup failed for {name}: {type(exc).__name__}: {exc}")
