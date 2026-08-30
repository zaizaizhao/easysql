from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from easysql.embeddings.base import BaseEmbeddingProvider
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.retrieval import runtime as runtime_module
from easysql.retrieval.runtime import RetrievalRuntime


class FakeProvider(BaseEmbeddingProvider):
    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dimension(self) -> int:
        return 3

    def encode(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        return [self.encode(text) for text in texts]


class FakeMilvusRepository:
    def __init__(self) -> None:
        self.client = object()
        self.collection_prefix = "test"
        self.table_collection = "test_table_embeddings"
        self.column_collection = "test_column_embeddings"
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeNeo4jRepository:
    def __init__(self) -> None:
        self.driver = object()
        self.database = "neo4j"
        self.project_namespace = "test"
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def make_settings(*, code_context_enabled: bool = True) -> Any:
    return SimpleNamespace(
        retrieval_search_top_k=5,
        retrieval_expand_fk=True,
        retrieval_expand_max_depth=1,
        semantic_filter_enabled=True,
        semantic_filter_threshold=0.5,
        semantic_filter_min_tables=3,
        bridge_protection_enabled=True,
        core_tables_list=[],
        llm_filter_enabled=False,
        llm_filter_max_tables=8,
        llm_filter_model="fake",
        llm=SimpleNamespace(openai_api_key=None, openai_api_base=None),
        code_context_enabled=code_context_enabled,
        code_context_search_top_k=5,
        code_context_score_threshold=0.3,
        code_context_max_snippets=3,
        project_namespace="test",
    )


def make_runtime(*, code_context_enabled: bool = True) -> tuple[
    RetrievalRuntime,
    EmbeddingService,
    FakeMilvusRepository,
    FakeNeo4jRepository,
]:
    embedding = EmbeddingService(FakeProvider())
    milvus = FakeMilvusRepository()
    neo4j = FakeNeo4jRepository()
    runtime = RetrievalRuntime(
        settings=make_settings(code_context_enabled=code_context_enabled),
        embedding_service=embedding,
        milvus_repository=milvus,  # type: ignore[arg-type]
        neo4j_repository=neo4j,  # type: ignore[arg-type]
    )
    return runtime, embedding, milvus, neo4j


def test_all_retrievers_share_one_embedding_service() -> None:
    runtime, embedding, _, _ = make_runtime()

    assert runtime.embedding_service is embedding
    assert runtime.schema_retrieval._milvus is runtime.milvus_reader
    assert runtime.milvus_reader._embedding_service is embedding
    assert runtime.few_shot_reader._embedding_service is embedding

    code_retrieval = runtime.code_retrieval
    assert code_retrieval is not None
    assert code_retrieval._reader._embedding is embedding


def test_runtime_closes_shared_repositories_once() -> None:
    runtime, _, milvus, neo4j = make_runtime()

    runtime.close()
    runtime.close()

    assert milvus.close_calls == 1
    assert neo4j.close_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        _ = runtime.milvus_reader


def test_code_retrieval_stays_lazy_when_disabled() -> None:
    runtime, _, _, _ = make_runtime(code_context_enabled=False)

    assert runtime.code_retrieval is None


def test_process_runtime_is_created_once_and_reset_closes_it(monkeypatch) -> None:
    created: list[Any] = []

    class FakeRuntime:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    def create_runtime(cls: type[RetrievalRuntime], settings: Any) -> FakeRuntime:
        runtime = FakeRuntime()
        created.append(runtime)
        return runtime

    runtime_module._get_cached_runtime.cache_clear()
    monkeypatch.setattr(
        runtime_module.RetrievalRuntime,
        "from_settings",
        classmethod(create_runtime),
    )

    first = runtime_module.get_retrieval_runtime()
    second = runtime_module.get_retrieval_runtime()
    runtime_module.reset_retrieval_runtime()

    assert first is second
    assert len(created) == 1
    assert first.close_calls == 1

    third = runtime_module.get_retrieval_runtime()
    assert third is not first
    assert len(created) == 2

    runtime_module.reset_retrieval_runtime()
