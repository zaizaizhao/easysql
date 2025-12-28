"""
Embedding service for EasySql.

Provides text vectorization using sentence transformers.
Supports batch processing and caching for efficiency.
"""

from typing import List, Union
import numpy as np

from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """
    Text embedding service using sentence transformers.

    Encapsulates the embedding model and provides methods for
    single and batch text vectorization.

    Usage:
        service = EmbeddingService(model_name="BAAI/bge-large-zh-v1.5")
        vector = service.encode("患者信息表")
        vectors = service.encode_batch(["患者", "处方", "医嘱"])
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str | None = None,
        normalize: bool = True,
    ):
        """
        Initialize the embedding service.

        Args:
            model_name: Name of the sentence transformer model
            device: Device to use ('cpu', 'cuda', or None for auto)
            normalize: Whether to normalize embeddings to unit length
        """
        self.model_name = model_name
        self.device = device
        self.normalize = normalize
        self._model = None
        self._dimension: int | None = None

    @property
    def model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name, device=self.device)
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(
                    f"Model loaded: dimension={self._dimension}, device={self._model.device}"
                )
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise RuntimeError(f"Failed to load model {self.model_name}: {e}") from e
        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        if self._dimension is None:
            # Trigger model loading
            _ = self.model
        return self._dimension

    def encode(self, text: str) -> List[float]:
        """
        Encode a single text into a vector.

        Args:
            text: Text to encode

        Returns:
            List of floats representing the embedding
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.dimension

        embedding = self.model.encode(
            text,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Encode multiple texts into vectors.

        Args:
            texts: List of texts to encode
            batch_size: Batch size for processing
            show_progress: Whether to show progress bar

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Handle empty strings
        processed_texts = [t if t and t.strip() else " " for t in texts]

        embeddings = self.model.encode(
            processed_texts,
            batch_size=batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=show_progress,
        )

        return embeddings.tolist()

    def compute_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """
        Compute cosine similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Cosine similarity score (0-1)
        """
        vec1 = np.array(self.encode(text1))
        vec2 = np.array(self.encode(text2))

        # Cosine similarity (vectors are already normalized if normalize=True)
        if self.normalize:
            return float(np.dot(vec1, vec2))
        else:
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def __repr__(self) -> str:
        return f"EmbeddingService(model={self.model_name}, dim={self._dimension})"
