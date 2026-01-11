"""
SentenceTransformer Embedding Provider.

Local inference using sentence-transformers library.
Supports batch processing and lazy model loading.
"""

import numpy as np

from easysql.utils.logger import get_logger

from .base import BaseEmbeddingProvider

logger = get_logger(__name__)


class SentenceTransformerProvider(BaseEmbeddingProvider):
    """
    Embedding provider using local SentenceTransformer models.

    Loads models from HuggingFace Hub or local paths.
    Supports GPU acceleration and batch processing.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str | None = None,
        normalize: bool = True,
        cache_dir: str | None = None,
    ):
        self._model_name = model_name
        self._device = device
        self._normalize = normalize
        self._cache_dir = cache_dir
        self._model = None
        self._dimension: int | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def _loaded_model(self):
        if self._model is None:
            logger.info(f"Loading embedding model: {self._model_name}")
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(
                    self._model_name,
                    device=self._device,
                    cache_folder=self._cache_dir,
                )
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(
                    f"Model loaded: dimension={self._dimension}, device={self._model.device}"
                )
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise RuntimeError(f"Failed to load model {self._model_name}: {e}") from e
        return self._model

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            _ = self._loaded_model
        assert self._dimension is not None, "Model loading failed to set dimension"
        return self._dimension

    def encode(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * self.dimension

        embedding = self._loaded_model.encode(
            text,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
        )
        result: list[float] = embedding.tolist()
        return result

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        if not texts:
            return []

        processed_texts = [t if t and t.strip() else " " for t in texts]

        embeddings = self._loaded_model.encode(
            processed_texts,
            batch_size=batch_size,
            normalize_embeddings=self._normalize,
            show_progress_bar=show_progress,
        )

        result: list[list[float]] = embeddings.tolist()
        return result

    def compute_similarity(self, text1: str, text2: str) -> float:
        """Compute cosine similarity between two texts."""
        vec1 = np.array(self.encode(text1))
        vec2 = np.array(self.encode(text2))

        if self._normalize:
            return float(np.dot(vec1, vec2))
        else:
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(np.dot(vec1, vec2) / (norm1 * norm2))
