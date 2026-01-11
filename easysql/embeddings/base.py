"""
Embedding Provider Base Classes.

Defines abstract interfaces for embedding providers, enabling pluggable
implementations for different backends (local models, API services, etc.).
"""

from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.

    All embedding implementations must inherit from this class and implement
    the required methods. This enables swapping between local inference
    (SentenceTransformer) and remote API services (OpenAI-compatible, TEI).

    Example:
        provider = SentenceTransformerProvider(model_name="BAAI/bge-large-zh-v1.5")
        vector = provider.encode("患者信息表")
        vectors = provider.encode_batch(["患者", "处方", "医嘱"])
    """

    @abstractmethod
    def encode(self, text: str) -> list[float]:
        """
        Encode a single text into a vector.

        Args:
            text: Text to encode.

        Returns:
            List of floats representing the embedding vector.
        """
        pass

    @abstractmethod
    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """
        Encode multiple texts into vectors.

        Args:
            texts: List of texts to encode.
            batch_size: Number of texts to process per batch.
            show_progress: Whether to show progress bar (if supported).

        Returns:
            List of embedding vectors, one per input text.
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """
        Get the embedding vector dimension.

        Returns:
            Integer dimension of the embedding vectors.
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        Get the model name/identifier.

        Returns:
            String identifier of the model being used.
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name}, dim={self.dimension})"
