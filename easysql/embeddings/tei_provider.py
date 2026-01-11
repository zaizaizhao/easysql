"""
HuggingFace Text Embeddings Inference (TEI) Provider.

High-performance embedding server with custom API format.
See: https://github.com/huggingface/text-embeddings-inference
"""

import httpx

from easysql.utils.logger import get_logger

from .base import BaseEmbeddingProvider

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 60.0
DEFAULT_BATCH_SIZE = 32


class TEIProvider(BaseEmbeddingProvider):
    """
    Embedding provider for HuggingFace Text Embeddings Inference.

    TEI uses a different API format from OpenAI:
    - Endpoint: POST /embed
    - Request: {"inputs": "text" | ["text1", "text2"]}
    - Response: [[float, ...], ...]
    """

    def __init__(
        self,
        base_url: str,
        model: str = "default",
        dimension: int | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.Client | None = None

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._base_url,
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            )
        return self._client

    def _call_embed_api(self, inputs: str | list[str]) -> list[list[float]]:
        client = self._get_client()

        payload = {"inputs": inputs}

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = client.post("/embed", json=payload)
                response.raise_for_status()
                result: list[list[float]] = response.json()
                return result

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"TEI API request failed (attempt {attempt + 1}): {e}")
                if e.response.status_code >= 500:
                    continue
                raise
            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"TEI request error (attempt {attempt + 1}): {e}")
                continue

        raise RuntimeError(f"Failed after {self._max_retries} retries: {last_error}")

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            logger.info("Auto-detecting embedding dimension from TEI...")
            result = self._call_embed_api("test")
            self._dimension = len(result[0])
            logger.info(f"Detected dimension: {self._dimension}")
        return self._dimension

    def encode(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * self.dimension

        results = self._call_embed_api(text)
        return results[0]

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
        show_progress: bool = False,
    ) -> list[list[float]]:
        if not texts:
            return []

        processed_texts = [t if t and t.strip() else " " for t in texts]

        all_results: list[list[float]] = []
        for i in range(0, len(processed_texts), batch_size):
            batch = processed_texts[i : i + batch_size]
            results = self._call_embed_api(batch)
            all_results.extend(results)

            if show_progress:
                logger.info(f"Encoded {min(i + batch_size, len(texts))}/{len(texts)}")

        return all_results

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "TEIProvider":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
