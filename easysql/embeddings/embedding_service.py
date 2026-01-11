"""
Embedding Service Facade.

Provides a unified interface for embedding operations,
delegating to the configured provider (local or API-based).
Maintains backward compatibility with the original EmbeddingService API.
"""

from typing import TYPE_CHECKING

from easysql.utils.logger import get_logger

from .base import BaseEmbeddingProvider
from .factory import EmbeddingProviderFactory

if TYPE_CHECKING:
    from easysql.config import Settings

logger = get_logger(__name__)


class EmbeddingService:
    """
    Unified embedding service facade.

    Wraps the underlying provider and exposes a consistent API.

    Usage:
        # From settings (recommended)
        service = EmbeddingService.from_settings()

        # Direct provider injection
        provider = SentenceTransformerProvider(model_name="BAAI/bge-large-zh-v1.5")
        service = EmbeddingService(provider)

        # Helper method for local
        service = EmbeddingService.create_local(model_name="BAAI/bge-large-zh-v1.5")
    """

    def __init__(self, provider: BaseEmbeddingProvider):
        """
        Initialize with a specific provider.

        Args:
            provider: Concrete implementation of BaseEmbeddingProvider
        """
        self._provider = provider

    @classmethod
    def from_settings(cls, settings: "Settings | None" = None) -> "EmbeddingService":
        if settings is None:
            from easysql.config import get_settings

            settings = get_settings()

        provider = EmbeddingProviderFactory.from_settings(settings)
        return cls(provider=provider)

    @classmethod
    def create_local(
        cls,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str | None = None,
        normalize: bool = True,
        cache_dir: str | None = None,
    ) -> "EmbeddingService":
        """
        Helper to create a local SentenceTransformer service.

        Useful for tests or scripts that don't use full configuration.
        """
        from .sentence_transformer_provider import SentenceTransformerProvider

        provider = SentenceTransformerProvider(
            model_name=model_name,
            device=device,
            normalize=normalize,
            cache_dir=cache_dir,
        )
        return cls(provider=provider)

    @property
    def provider(self) -> BaseEmbeddingProvider:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    @property
    def dimension(self) -> int:
        return self._provider.dimension

    def encode(self, text: str) -> list[float]:
        return self._provider.encode(text)

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        return self._provider.encode_batch(texts, batch_size, show_progress)

    def compute_similarity(self, text1: str, text2: str) -> float:
        """Compute cosine similarity between two texts."""
        import numpy as np

        vec1 = np.array(self.encode(text1))
        vec2 = np.array(self.encode(text2))

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def __repr__(self) -> str:
        return f"EmbeddingService(provider={self._provider})"
