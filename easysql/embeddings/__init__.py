"""Embeddings package for EasySql."""

from easysql.embeddings.base import BaseEmbeddingProvider
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.embeddings.factory import EmbeddingProviderFactory
from easysql.embeddings.openai_api_provider import OpenAIAPIProvider
from easysql.embeddings.sentence_transformer_provider import SentenceTransformerProvider
from easysql.embeddings.tei_provider import TEIProvider

__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingService",
    "EmbeddingProviderFactory",
    "SentenceTransformerProvider",
    "OpenAIAPIProvider",
    "TEIProvider",
]
