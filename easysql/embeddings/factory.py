"""
Embedding Provider Factory.

Creates embedding providers based on configuration.
Supports: local (SentenceTransformer), openai_api, tei.
"""

from typing import TYPE_CHECKING, Literal

from easysql.utils.logger import get_logger

from .base import BaseEmbeddingProvider

if TYPE_CHECKING:
    from easysql.config import Settings

logger = get_logger(__name__)

ProviderType = Literal["local", "openai_api", "tei"]


class EmbeddingProviderFactory:
    """Factory for creating embedding providers based on configuration."""

    @staticmethod
    def create(
        provider_type: ProviderType = "local",
        model_name: str = "BAAI/bge-large-zh-v1.5",
        dimension: int | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        device: str | None = None,
        cache_dir: str | None = None,
        timeout: float = 60.0,
    ) -> BaseEmbeddingProvider:
        """
        Create an embedding provider.

        Args:
            provider_type: Provider type - "local", "openai_api", or "tei".
            model_name: Model name/identifier.
            dimension: Vector dimension (auto-detected if None for API providers).
            api_base: API base URL (required for openai_api and tei).
            api_key: API key (optional, for openai_api).
            device: Device for local inference ("cpu", "cuda", or None for auto).
            cache_dir: Cache directory for local models.
            timeout: Request timeout for API providers.

        Returns:
            Configured embedding provider instance.

        Raises:
            ValueError: If provider_type is unknown or required params missing.
        """
        if provider_type == "local":
            from .sentence_transformer_provider import SentenceTransformerProvider

            logger.info(f"Creating SentenceTransformerProvider with model: {model_name}")
            return SentenceTransformerProvider(
                model_name=model_name,
                device=device,
                cache_dir=cache_dir,
            )

        elif provider_type == "openai_api":
            if not api_base:
                raise ValueError("api_base is required for openai_api provider")

            from .openai_api_provider import OpenAIAPIProvider

            logger.info(f"Creating OpenAIAPIProvider: {api_base}, model: {model_name}")
            return OpenAIAPIProvider(
                base_url=api_base,
                model=model_name,
                api_key=api_key,
                dimension=dimension,
                timeout=timeout,
            )

        elif provider_type == "tei":
            if not api_base:
                raise ValueError("api_base is required for tei provider")

            from .tei_provider import TEIProvider

            logger.info(f"Creating TEIProvider: {api_base}")
            return TEIProvider(
                base_url=api_base,
                model=model_name,
                dimension=dimension,
                timeout=timeout,
            )

        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

    @classmethod
    def from_settings(cls, settings: "Settings") -> BaseEmbeddingProvider:
        """Create provider from application Settings."""
        from easysql.config import Settings

        if not isinstance(settings, Settings):
            raise TypeError("Expected Settings instance")

        return cls.create(
            provider_type=settings.embedding_provider,  # type: ignore[arg-type]
            model_name=settings.embedding_model,
            dimension=settings.embedding_dimension if settings.embedding_dimension else None,
            api_base=settings.embedding_api_base,
            api_key=settings.embedding_api_key,
            device=settings.embedding_device,
            cache_dir=settings.embedding_cache_dir,
            timeout=settings.embedding_timeout,
        )
