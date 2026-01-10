"""
Retrieval Module

Provides schema retrieval functionality for Text2SQL.
This module is the bridge between user questions and LLM SQL generation.

Main components:
- SchemaRetrievalService: Main service that orchestrates retrieval
- TableFilter: Base class for table filtering strategies
- SemanticFilter: Filter by semantic similarity score
- BridgeFilter: Protect bridge tables that connect relevant tables
- LLMFilter: Use LLM to intelligently select tables
"""

from .base import (
    FilterChain,
    FilterContext,
    FilterResult,
    NoOpFilter,
    TableFilter,
)
from .bridge_filter import BridgeFilter
from .llm_filter import LLMFilter
from .schema_retrieval import (
    RetrievalConfig,
    RetrievalResult,
    SchemaRetrievalService,
)
from .semantic_filter import DEFAULT_CORE_TABLES, SemanticFilter

__all__ = [
    # Base classes
    "TableFilter",
    "FilterContext",
    "FilterResult",
    "FilterChain",
    "NoOpFilter",
    # Filters
    "SemanticFilter",
    "BridgeFilter",
    "LLMFilter",
    "DEFAULT_CORE_TABLES",
    # Service
    "SchemaRetrievalService",
    "RetrievalConfig",
    "RetrievalResult",
]
