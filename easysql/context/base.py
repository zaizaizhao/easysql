"""
Context Section Base Classes.

Provides abstract base class for modular context sections.
Each section handles rendering a specific type of context content.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .models import ContextInput, SectionContent


@dataclass
class SectionConfig:
    """
    Configuration for a context section.
    
    Attributes:
        enabled: Whether the section is enabled.
        priority: Rendering priority (lower = rendered first).
        max_tokens: Optional token limit for this section.
    """
    enabled: bool = True
    priority: int = 0
    max_tokens: Optional[int] = None


class ContextSection(ABC):
    """
    Abstract base class for context sections.
    
    Each section is responsible for rendering a specific type of content
    (e.g., schema info, join paths, few-shot examples).
    
    Subclasses must implement:
        - name: Property returning the section name.
        - render(): Method to render the section content.
    
    Example:
        class SchemaSection(ContextSection):
            @property
            def name(self) -> str:
                return "schema"
            
            def render(self, context: ContextInput) -> SectionContent:
                # Build schema content
                content = self._render_tables(context.retrieval_result)
                return SectionContent(name=self.name, content=content)
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique name of this section."""
        pass
    
    @abstractmethod
    def render(self, context: ContextInput) -> SectionContent:
        """
        Render the section content.
        
        Args:
            context: Context input containing retrieval results and config.
            
        Returns:
            SectionContent with rendered content and metadata.
        """
        pass
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Uses simple approximation: ~4 characters per token for mixed content.
        For Chinese text, approximately 1.5 characters per token.
        
        Args:
            text: Text to estimate tokens for.
            
        Returns:
            Estimated token count.
        """
        # Count Chinese characters
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        # Chinese: ~1.5 chars per token, Other: ~4 chars per token
        return int(chinese_chars / 1.5 + other_chars / 4)
