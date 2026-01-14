"""
Context Builder for EasySql.

Provides modular context construction for LLM-based Text2SQL.
Converts schema retrieval results into structured prompts for LLM.
"""

from .models import ContextInput, ContextOutput, FewShotExample
from .base import ContextSection, SectionConfig, SectionContent
from .builder import ContextBuilder
from .templates import PromptTemplate
from .sections import SchemaSection, JoinPathSection, FewShotSection

__all__ = [
    # Core classes
    "ContextBuilder",
    "ContextSection",
    "SectionConfig",
    "SectionContent",
    "PromptTemplate",
    # Models
    "ContextInput",
    "ContextOutput",
    "FewShotExample",
    # Sections
    "SchemaSection",
    "JoinPathSection",
    "FewShotSection",
]
