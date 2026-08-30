from __future__ import annotations

from easysql.embeddings.base import BaseEmbeddingProvider
from easysql.embeddings.embedding_service import EmbeddingService


class CountingEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self) -> None:
        self.encode_calls: list[str] = []

    @property
    def model_name(self) -> str:
        return "counting"

    @property
    def dimension(self) -> int:
        return 2

    def encode(self, text: str) -> list[float]:
        self.encode_calls.append(text)
        return [float(len(text)), 1.0]

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        return [self.encode(text) for text in texts]


def test_same_text_is_encoded_once_and_returns_defensive_copies() -> None:
    provider = CountingEmbeddingProvider()
    service = EmbeddingService(provider, query_cache_size=8)

    first = service.encode("same question")
    first[0] = -1.0
    second = service.encode("same question")

    assert provider.encode_calls == ["same question"]
    assert second == [13.0, 1.0]


def test_query_cache_is_bounded_and_lru() -> None:
    provider = CountingEmbeddingProvider()
    service = EmbeddingService(provider, query_cache_size=2)

    service.encode("a")
    service.encode("b")
    service.encode("a")  # refresh a; b becomes least recently used
    service.encode("c")
    service.encode("b")

    assert provider.encode_calls == ["a", "b", "c", "b"]


def test_clear_query_cache_forces_reencode() -> None:
    provider = CountingEmbeddingProvider()
    service = EmbeddingService(provider)

    service.encode("q")
    service.clear_query_cache()
    service.encode("q")

    assert provider.encode_calls == ["q", "q"]
