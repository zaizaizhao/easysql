"""Cache invalidation and optional warmup for runtime config updates."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable

from easysql.config import get_settings
from easysql.llm.nodes.retrieve import (
    reset_retrieval_service_cache,
    warm_retrieval_service_cache,
)
from easysql.llm.nodes.retrieve_code import (
    reset_code_retrieval_service_cache,
    warm_code_retrieval_service_cache,
)
from easysql.llm.nodes.retrieve_few_shot import (
    reset_few_shot_reader_cache,
    warm_few_shot_reader_cache,
)
from easysql.llm.nodes.retrieve_hint import (
    reset_retrieve_hint_readers_cache,
    warm_retrieve_hint_readers_cache,
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

        if "retrieval_cache" in tag_set:
            reset_retrieval_service_cache()
            reset_retrieve_hint_readers_cache()

        if "few_shot_cache" in tag_set:
            reset_few_shot_reader_cache()

        if "code_context_cache" in tag_set:
            reset_code_retrieval_service_cache()

    def warmup(self, tags: Iterable[str]) -> None:
        tag_set = set(tags)

        if "graph" in tag_set:
            self._safe_warm(warm_query_service_graph, "query graph")

        if "callbacks" in tag_set:
            self._safe_warm(warm_query_service_callbacks, "query callbacks")
            self._safe_warm(warm_chart_service_callbacks, "chart callbacks")

        if "retrieval_cache" in tag_set:
            self._safe_warm(warm_retrieval_service_cache, "retrieval service")
            self._safe_warm(warm_retrieve_hint_readers_cache, "retrieve_hint readers")

        if "few_shot_cache" in tag_set:
            self._safe_warm(warm_few_shot_reader_cache, "few-shot reader")

        if "code_context_cache" in tag_set:
            self._safe_warm(warm_code_retrieval_service_cache, "code retrieval service")

    @staticmethod
    def _safe_warm(func: Callable[[], None], name: str) -> None:
        try:
            func()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Cache warmup failed for {name}: {type(exc).__name__}: {exc}")
