"""
Context Builder.

Orchestrates multiple context sections to build LLM prompts.
"""

from typing import List, Optional, Dict, Any

from .base import ContextSection, SectionConfig
from .models import ContextInput, ContextOutput, SectionContent
from .templates import PromptTemplate
from .sections import SchemaSection, JoinPathSection


class ContextBuilder:
    """
    Context builder - orchestrates multiple sections to build LLM context.
    
    Usage:
        # Create with defaults
        builder = ContextBuilder.default()
        
        # Or customize
        builder = ContextBuilder()
        builder.add_section(SchemaSection(format="table"))
        builder.add_section(JoinPathSection())
        
        # Build context
        output = builder.build(context_input)
        
        # Use with LLM
        response = llm.chat(
            system=output.system_prompt,
            user=output.user_prompt,
        )
    """
    
    def __init__(
        self,
        template: Optional[PromptTemplate] = None,
        max_total_tokens: int = 32000,
    ):
        """
        Initialize context builder.
        
        Args:
            template: Prompt template to use (default: PromptTemplate.default()).
            max_total_tokens: Maximum total tokens for the context.
        """
        self._sections: List[tuple[ContextSection, SectionConfig]] = []
        self._template = template or PromptTemplate.default()
        self._max_tokens = max_total_tokens
    
    def add_section(
        self,
        section: ContextSection,
        config: Optional[SectionConfig] = None,
    ) -> "ContextBuilder":
        """
        Add a section to the builder.
        
        Args:
            section: Section instance to add.
            config: Optional section configuration.
            
        Returns:
            Self for chaining.
        """
        config = config or SectionConfig()
        self._sections.append((section, config))
        return self
    
    def remove_section(self, name: str) -> "ContextBuilder":
        """
        Remove a section by name.
        
        Args:
            name: Name of the section to remove.
            
        Returns:
            Self for chaining.
        """
        self._sections = [
            (s, c) for s, c in self._sections if s.name != name
        ]
        return self
    
    def get_section(self, name: str) -> Optional[ContextSection]:
        """
        Get a section by name.
        
        Args:
            name: Name of the section.
            
        Returns:
            Section instance or None if not found.
        """
        for section, _ in self._sections:
            if section.name == name:
                return section
        return None
    
    def build(self, context_input: ContextInput) -> ContextOutput:
        """
        Build the full context for LLM.
        
        Args:
            context_input: Context input with retrieval results.
            
        Returns:
            ContextOutput with system and user prompts.
        """
        # Sort sections by priority
        sorted_sections = sorted(
            self._sections,
            key=lambda x: x[1].priority
        )
        
        # Render each enabled section
        rendered_sections: List[SectionContent] = []
        total_tokens = 0
        
        for section, config in sorted_sections:
            if not config.enabled:
                continue
            
            content = section.render(context_input)
            
            # Apply token limit if specified
            if config.max_tokens and content.token_count > config.max_tokens:
                # Truncate content (simple approach)
                # In production, you might want smarter truncation
                content = self._truncate_section(content, config.max_tokens)
            
            rendered_sections.append(content)
            total_tokens += content.token_count
        
        # Render prompts
        system_prompt = self._template.render_system()
        user_prompt = self._template.render_user(
            sections=rendered_sections,
            question=context_input.question,
        )
        
        # Estimate total tokens
        total_tokens += self._estimate_tokens(system_prompt)
        total_tokens += self._estimate_tokens(user_prompt) - sum(
            s.token_count for s in rendered_sections
        )  # Avoid double counting
        
        return ContextOutput(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            sections=rendered_sections,
            total_tokens=total_tokens,
            metadata={
                "section_count": len(rendered_sections),
                "tables": context_input.retrieval_result.tables,
            }
        )
    
    def _truncate_section(
        self,
        content: SectionContent,
        max_tokens: int,
    ) -> SectionContent:
        """Truncate section content to fit token limit."""
        # Simple character-based truncation
        # Estimate chars per token (mixed content)
        chars_per_token = 3
        max_chars = max_tokens * chars_per_token
        
        if len(content.content) <= max_chars:
            return content
        
        truncated_content = content.content[:max_chars] + "\n... (已截断)"
        
        return SectionContent(
            name=content.name,
            content=truncated_content,
            token_count=max_tokens,
            metadata={**content.metadata, "truncated": True}
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
    
    @classmethod
    def default(cls) -> "ContextBuilder":
        """
        Create a builder with default sections.
        
        Includes:
        - SchemaSection (priority 0)
        - JoinPathSection (priority 10)
        
        Returns:
            Configured ContextBuilder instance.
        """
        builder = cls()
        builder.add_section(
            SchemaSection(),
            SectionConfig(priority=0)
        )
        builder.add_section(
            JoinPathSection(),
            SectionConfig(priority=10)
        )
        return builder
    
    @classmethod
    def minimal(cls) -> "ContextBuilder":
        """
        Create a minimal builder with compact schema.
        
        Uses list format and minimal options for token efficiency.
        
        Returns:
            Configured ContextBuilder instance.
        """
        builder = cls()
        builder.add_section(
            SchemaSection(
                format="list",
                include_descriptions=True,
                include_constraints=True,
                max_columns_per_table=20,
            ),
            SectionConfig(priority=0)
        )
        builder.add_section(
            JoinPathSection(include_instructions=False),
            SectionConfig(priority=10)
        )
        return builder
